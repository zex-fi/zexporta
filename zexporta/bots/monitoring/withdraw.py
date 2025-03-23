import asyncio
import struct
import time
from decimal import Decimal

import httpx
from clients.evm import (
    get_ERC20_balance,
    get_evm_async_client,
    get_signed_data,
)

from zexporta.bots.custom_types import BotToken
from zexporta.custom_types import ChecksumAddress, EVMConfig
from zexporta.utils.logger import ChainLoggerAdapter
from zexporta.utils.zex_api import get_user_withdraw_nonce, send_withdraw_request

from .config import (
    MONITORING_TOKENS,
    TEST_USER_ID,
    WITHDRAWER_PRIVATE_KEY,
)

WITHDRAW_OPERATION = "w"


class WithdrawError(Exception):
    "raise when WithdrawError occurred"


def withdraw_msg(tx: bytes, logger: ChainLoggerAdapter) -> bytes:
    version, token_len = struct.unpack(">B x B", tx[:3])
    withdraw_format = f">3s {token_len}s d 20s I I 33s"
    unpacked = struct.unpack(withdraw_format, tx[3 : 3 + struct.calcsize(withdraw_format)])
    token_chain, token_name, amount, destination, t, nonce, public = unpacked
    token_chain = token_chain.decode("ascii")
    token_name = token_name.decode("ascii")
    msg = f"v: {version}\n"
    msg += "name: withdraw\n"
    msg += f"token chain: {token_chain}\n"
    msg += f"token name: {token_name}\n"
    msg += f"amount: {amount}\n"
    msg += f"to: {'0x' + destination.hex()}\n"
    msg += f"t: {t}\n"
    msg += f"nonce: {nonce}\n"
    msg += f"public: {public.hex()}\n"
    logger.debug("withdraw message: %s", msg)
    return msg.encode()


def create_tx(
    chain: EVMConfig,
    monitoring_token: BotToken,
    public_key: str,
    destination_address: ChecksumAddress,
    nonce: int,
) -> bytes:
    # Prepare withdrawal data
    version = 1

    token_chain = chain.chain_symbol.encode()
    token_name = monitoring_token.symbol.encode()
    destination = bytes.fromhex(destination_address[2:])
    t = int(time.time())
    public = bytes.fromhex(public_key)
    amount = float(Decimal(monitoring_token.amount / 10**monitoring_token.decimal))
    token_len = len(token_name)
    pack_format = f"> B 1s B 3s {token_len}s d 20s I I 33s"
    return struct.pack(
        pack_format,
        version,
        WITHDRAW_OPERATION.encode(),
        token_len,
        token_chain,
        token_name,
        amount,
        destination,
        t,
        nonce,
        public,
    )


async def monitor_withdraw(async_client: httpx.AsyncClient, chain: EVMConfig, logger: ChainLoggerAdapter):
    monitoring_token = [token for token in MONITORING_TOKENS if token.chain_symbol == chain.chain_symbol]
    if len(monitoring_token) == 0:
        raise WithdrawError("No token for monitoring found.")

    monitoring_token = monitoring_token[0]
    w3 = get_evm_async_client(chain, logger).client
    withdrawer_account = w3.eth.account.from_key(WITHDRAWER_PRIVATE_KEY)
    destination_address = withdrawer_account.address
    public_key = withdrawer_account._key_obj.public_key.to_compressed_bytes().hex()
    balance_before = await get_ERC20_balance(
        w3,
        contract_address=monitoring_token.address,
        wallet_address=w3.to_checksum_address(destination_address),
    )
    user_withdraw_nonce = await get_user_withdraw_nonce(async_client, chain, TEST_USER_ID)
    tx = create_tx(chain, monitoring_token, public_key, destination_address, user_withdraw_nonce)
    msg = withdraw_msg(tx, logger)
    signed_data = bytes.fromhex(get_signed_data(WITHDRAWER_PRIVATE_KEY, primitive=msg)[2:])[:-1]
    logger.debug(tx + signed_data)
    send_data = (tx + signed_data).decode("latin-1")
    await send_withdraw_request(async_client, [send_data])
    await asyncio.sleep(240)
    balance_after = await get_ERC20_balance(
        w3,
        contract_address=monitoring_token.address,
        wallet_address=w3.to_checksum_address(destination_address),
    )
    if balance_after == balance_before + monitoring_token.amount:
        return
    raise WithdrawError("User balance did not increase.")
