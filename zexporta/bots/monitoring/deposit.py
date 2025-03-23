import asyncio
from decimal import Decimal

import httpx
from clients import get_evm_async_client
from clients.evm import compute_create2_address

from zexporta.bots.monitoring.config import (
    MONITORING_TOKENS,
    TEST_USER_ID,
    WITHDRAWER_PRIVATE_KEY,
)
from zexporta.bots.utils.deposit import send_deposit, wait_for_transaction_receipt
from zexporta.custom_types import EVMConfig, UserId
from zexporta.utils.logger import ChainLoggerAdapter
from zexporta.utils.zex_api import get_user_asset


class DepositError(Exception):
    "raise when deposit was not successful"


async def get_user_balance(client: httpx.AsyncClient, user_id: UserId, symbol: str) -> Decimal:
    balance = [
        user_asset.free for user_asset in (await get_user_asset(client, user_id=user_id)) if user_asset.asset == symbol
    ]
    if len(balance) == 0:
        return Decimal(0)
    return Decimal(balance[0])


async def monitor_deposit(async_client: httpx.AsyncClient, chain: EVMConfig, logger: ChainLoggerAdapter):
    monitoring_token = [token for token in MONITORING_TOKENS if token.chain_symbol == chain.chain_symbol]
    if len(monitoring_token) == 0:
        raise DepositError("No token for monitoring found")
    monitoring_token = monitoring_token[0]
    test_user_address = compute_create2_address(
        TEST_USER_ID,
    )

    w3 = get_evm_async_client(chain, logger).client
    account = w3.eth.account.from_key(WITHDRAWER_PRIVATE_KEY)
    balance_before = await get_user_balance(async_client, TEST_USER_ID, monitoring_token.symbol)
    logger.info(f"Balance before deposit: {balance_before}")

    tx_hash = await send_deposit(
        w3,
        monitoring_token,
        account=account,
        user_address=test_user_address,
        logger=logger,
    )
    receipt = await wait_for_transaction_receipt(w3, tx_hash, logger)
    if receipt and receipt["status"] == 1:
        logger.info("Transaction successful.")
    else:
        raise DepositError("Transaction failed.")

    await asyncio.sleep(60)  # wait until deposit store in zex

    balance_after = await get_user_balance(async_client, TEST_USER_ID, monitoring_token.symbol)
    logger.info(f"Balance after deposit: {balance_after}")

    # Check if balance increased
    if balance_after == balance_before + Decimal(monitoring_token.amount) / Decimal(10**monitoring_token.decimal):
        logger.info("Balance has increased. Deposit successful.")
        return
    raise DepositError("Balance is not correct, something went wrong.")
