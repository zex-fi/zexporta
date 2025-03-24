import logging.config

from clients import get_async_client
from clients.evm import get_signed_data
from web3 import Web3

from zexporta.custom_types import (
    EVMConfig,
    EVMWithdrawRequest,
)
from zexporta.utils.abi import VAULT_ABI
from zexporta.utils.encoder import get_evm_withdraw_hash
from zexporta.utils.logger import ChainLoggerAdapter

from .config import (
    EVM_WITHDRAWER_PRIVATE_KEY,
    SA_SHIELD_PRIVATE_KEY,
)


async def send_evm_withdraw(
    chain: EVMConfig,
    withdraw_request: EVMWithdrawRequest,
    result: dict,
    logger: logging.Logger | ChainLoggerAdapter,
):
    signature = result["signature"]
    signature_nonce = (Web3.to_checksum_address(result["nonce"]),)
    w3 = get_async_client(chain, logger).client
    account = w3.eth.account.from_key(EVM_WITHDRAWER_PRIVATE_KEY)

    vault = w3.eth.contract(address=Web3.to_checksum_address(chain.vault_address), abi=VAULT_ABI)
    nonce = await w3.eth.get_transaction_count(account.address)
    withdraw_hash = get_evm_withdraw_hash(withdraw_request)
    signed_data = get_signed_data(SA_SHIELD_PRIVATE_KEY, hexstr=withdraw_hash)
    logger.debug(f"Signed Withdraw data is: {signed_data}")
    tx = await vault.functions.withdraw(
        withdraw_request.token_address,
        withdraw_request.amount,
        withdraw_request.recipient,
        withdraw_request.nonce,
        signature,
        signature_nonce,
        signed_data,
    ).build_transaction({"from": account.address, "nonce": nonce})
    signed_tx = account.sign_transaction(tx)
    tx_hash = await w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    withdraw_request.tx_hash = tx_hash.hex()
    await w3.eth.wait_for_transaction_receipt(tx_hash)
    logger.info(f"Method called successfully. Transaction Hash: {tx_hash.hex()}")
