import hashlib
import json
import logging
import logging.config
from decimal import Decimal
from typing import Optional

from bitcoinutils.constants import TAPROOT_SIGHASH_ALL
from bitcoinutils.keys import P2trAddress, PrivateKey
from bitcoinutils.schnorr import schnorr_sign
from bitcoinutils.script import Script
from bitcoinutils.transactions import Transaction, TxInput, TxOutput, TxWitnessInput
from bitcoinutils.utils import (
    b_to_h,
    to_satoshis,
    tweak_taproot_privkey,
)
from clients import get_async_client
from clients.btc.client import calculate_tweak
from clients.btc.custom_types import UTXOStatus

from zexporta.config import (
    BTC_WITHDRAWER_PRIVATE_KEY,
)
from zexporta.custom_types import (
    UTXO,
    BTCConfig,
    BTCWithdrawRequest,
    WithdrawStatus,
)
from zexporta.db.utxo import find_utxo_by_status, upsert_utxo
from zexporta.db.withdraw import upsert_withdraw
from zexporta.utils.logger import ChainLoggerAdapter


class NotEnoughInputs(Exception):
    pass


class UTXOAssignmentError(Exception):
    pass


def get_simple_withdraw_tx(
    withdraw_request: BTCWithdrawRequest,
    change_address: str,
    utxos: list[UTXO] | None = None,
):
    send_amount = int(to_satoshis(Decimal(withdraw_request.amount)))
    utxos = utxos or withdraw_request.utxos
    to_address = withdraw_request.recipient
    fee = calculate_fee(
        recipient=withdraw_request.recipient,
        change_address=change_address,
        amount=send_amount,
        sat_per_byte=withdraw_request.sat_per_byte,
        utxos=utxos,
    )
    assert utxos is not None

    amounts = []
    input_amount = 0
    utxos_script_pubkeys = []
    inputs = []
    for utxo in utxos:
        amounts.append(int(utxo.amount))  # should be satoshi
        input_amount += int(utxo.amount)
        utxos_script_pubkeys.append(P2trAddress(utxo.address).to_script_pub_key())
        inputs.append(TxInput(txid=utxo.tx_hash, txout_index=int(utxo.index)))

    # create transaction output
    txOut1 = TxOutput(send_amount, P2trAddress(to_address).to_script_pub_key())
    txOut2 = TxOutput(input_amount - send_amount - fee, P2trAddress(change_address).to_script_pub_key())

    # create transaction without change output - if at least a single input is
    # segwit we need to set has_segwit = True
    tx = Transaction(inputs, [txOut1, txOut2], has_segwit=True)
    tx_digests = []
    for i in range(0, len(utxos)):
        tx_digests.append(
            tx.get_transaction_taproot_digest(i, utxos_script_pubkeys, amounts, 0, sighash=TAPROOT_SIGHASH_ALL)
        )
    return tx, tx_digests


def calculate_fee(
    recipient: str,
    amount: int,
    change_address: str,
    utxos: list[UTXO],
    sat_per_byte: int,
) -> int:
    amounts = []
    input_amount = 0
    utxos_script_pubkeys = []
    inputs = []
    for utxo in utxos:
        amounts.append(utxo.amount)  # should be satoshi
        input_amount += int(utxo.amount)
        utxos_script_pubkeys.append(P2trAddress(utxo.address).to_script_pub_key())
        inputs.append(TxInput(txid=utxo.tx_hash, txout_index=int(utxo.index)))

    # create transaction output
    txOut1 = TxOutput(amount, P2trAddress(recipient).to_script_pub_key())
    txOut2 = TxOutput(input_amount - amount, P2trAddress(change_address).to_script_pub_key())

    # create transaction without change output - if at least a single input is
    # segwit we need to set has_segwit=True
    fee_calculator_tx = Transaction(inputs, [txOut1, txOut2], has_segwit=True)
    tx_size = fee_calculator_tx.get_size() + (30 * len(utxos))  # add signature size (ceil of size actual size is less)
    return tx_size * sat_per_byte


async def get_utxos_for_withdraw(withdraw_request: BTCWithdrawRequest, change_address: str) -> list[UTXO]:
    inputs = []
    amount = 0
    withdraw_amount = to_satoshis(withdraw_request.amount)
    utxos = await find_utxo_by_status(status=UTXOStatus.UNSPENT)
    for utxo in utxos:
        inputs.append(utxo)
        amount += utxo.amount
        fee = calculate_fee(
            recipient=withdraw_request.recipient,
            change_address=change_address,
            amount=withdraw_amount,
            sat_per_byte=withdraw_request.sat_per_byte,
            utxos=inputs,
        )
        if amount >= fee + withdraw_amount:
            return inputs
    else:
        raise NotEnoughInputs


def _sign(
    private_key: PrivateKey,
    tx: Transaction,
    txin_index: int,
    utxo_scripts: list[Script],
    amounts: list[int],
    scripts: Optional[Script | list[Script] | list[list[Script]]] | bytes = None,
    sighash: int = TAPROOT_SIGHASH_ALL,
):
    tx_digest = tx.get_transaction_taproot_digest(txin_index, utxo_scripts, amounts, 0, sighash=sighash)

    tweak_int = calculate_tweak(private_key.get_public_key(), scripts)
    byte_key = tweak_taproot_privkey(private_key.key.to_string(), tweak_int)

    rand_aux = hashlib.sha256(tx_digest + byte_key).digest()

    sig = schnorr_sign(tx_digest, byte_key, rand_aux)

    return b_to_h(sig)


def sign_transaction(withdraw_request: BTCWithdrawRequest, tx: Transaction) -> Transaction:
    utxos_script_pubkeys = [P2trAddress(utxo.address).to_script_pub_key() for utxo in withdraw_request.utxos]
    amounts = [int(utxo.amount) for utxo in withdraw_request.utxos]

    private_key = PrivateKey.from_wif(BTC_WITHDRAWER_PRIVATE_KEY)

    for i, utxo in enumerate(withdraw_request.utxos):
        signature = _sign(
            private_key=private_key,
            tx=tx,
            txin_index=i,
            utxo_scripts=utxos_script_pubkeys,
            amounts=amounts,
            scripts=utxo.salt.to_bytes(8, byteorder="big"),
        )
        tx.witnesses.append(TxWitnessInput([signature]))
    return tx


def add_fee_to_tx(withdraw_request: BTCWithdrawRequest, tx: Transaction, change_address: str):
    signed_tx = sign_transaction(withdraw_request, tx)
    fee_amount = signed_tx.get_vsize() * withdraw_request.sat_per_byte
    tx.witnesses = []
    new_outputs = []
    change_address_script = P2trAddress(change_address).to_script_pub_key()

    for output in tx.outputs:
        if output.script_pubkey == change_address_script:
            output.amount = output.amount - fee_amount
        new_outputs.append(output)

    tx.outputs = new_outputs

    utxos_script_pubkeys = [P2trAddress(utxo.address).to_script_pub_key() for utxo in withdraw_request.utxos]
    amounts = [utxo.amount for utxo in withdraw_request.utxos]
    tx_digests = tx.get_transaction_taproot_digest(0, utxos_script_pubkeys, amounts, 0, sighash=TAPROOT_SIGHASH_ALL)
    return tx, tx_digests


async def preprocess_btc_withdraw(
    chain: BTCConfig,
    withdraw_request: BTCWithdrawRequest,
    logger: logging.Logger | ChainLoggerAdapter,
):
    btc = get_async_client(chain, logger).client

    if withdraw_request.status == WithdrawStatus.PROCESSING:
        if withdraw_request.utxos is None:
            withdraw_request.sat_per_byte = btc.get_fee_per_byte()
            utxos = await get_utxos_for_withdraw(withdraw_request, change_address=chain.vault_address)
            for utxo in utxos:
                utxo.status = UTXOStatus.SPEND
                await upsert_utxo(utxo)
            withdraw_request.utxos = utxos
            await upsert_withdraw(withdraw_request)
        else:
            raise UTXOAssignmentError("WithdrawRequest with PROCESSING status has utxo !!!")
    return withdraw_request


async def send_btc_withdraw(
    chain: BTCConfig,
    withdraw_request: BTCWithdrawRequest,
    result: dict,
    logger: logging.Logger | ChainLoggerAdapter,
):
    withdraw_request = await preprocess_btc_withdraw(chain=chain, withdraw_request=withdraw_request, logger=logger)

    btc = get_async_client(chain, logger).client

    to_address = withdraw_request.recipient
    amount = withdraw_request.amount
    logging.info(f"Sending: {amount}, to:{to_address}")

    tx, _ = get_simple_withdraw_tx(
        withdraw_request,
        chain.vault_address,
    )

    signed_tx = sign_transaction(withdraw_request, tx)

    raw_tx = signed_tx.serialize()
    logging.info(f"Raw tx: {raw_tx}")

    resp = await btc.send_tx(raw_tx)
    logger.info(f"Transaction Info: {json.dumps({'raw_tx': raw_tx, 'tx_hash': resp.text}, indent=4)}")
