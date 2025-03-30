import asyncio
import logging
import logging.config

from clients.evm.client import compute_create2_address, get_evm_async_client
from eth_account.signers.local import LocalAccount
from hexbytes import HexBytes
from web3 import AsyncWeb3
from web3.types import Nonce, TxReceipt

from zexporta.bots.custom_types import BotToken
from zexporta.bots.transfer_test_token.config import (
    HOLDER_PRIVATE_KEY,
    LOGGER_PATH,
    TEST_TOKENS,
)
from zexporta.bots.transfer_test_token.database import (
    get_last_transferred_id,
    upsert_last_transferred_id,
)
from zexporta.bots.utils.deposit import send_deposit
from zexporta.config import (
    CHAINS_CONFIG,
)
from zexporta.custom_types import ChecksumAddress, EVMConfig, UserId
from zexporta.utils.logger import ChainLoggerAdapter, get_logger_config
from zexporta.utils.zex_api import ZexAPIError, get_async_client, get_last_zex_user_id

logging.config.dictConfig(get_logger_config(logger_path=f"{LOGGER_PATH}/transfer_test_token_bot.log"))
logger = logging.getLogger(__name__)


async def _get_last_user_id() -> UserId | None:
    async with get_async_client() as client:
        try:
            last_zex_user_id = await get_last_zex_user_id(client)
        except ZexAPIError as e:
            logger.error(f"Error in Zex API: {e}")
            return None
    return last_zex_user_id


async def _send_deposits(
    w3: AsyncWeb3,
    test_token: BotToken,
    account: LocalAccount,
    user_address: ChecksumAddress,
    logger: logging.Logger | ChainLoggerAdapter,
    nonce: Nonce,
) -> HexBytes:
    return await send_deposit(w3, test_token, account, user_address, logger, nonce, False)


async def _send_token_to_user_id(
    w3: AsyncWeb3,
    test_token: BotToken,
    user_id: UserId,
    account: LocalAccount,
    logger: ChainLoggerAdapter,
    nonce: Nonce,
) -> HexBytes:
    logger.info(f"Initiate transferring to user with id: {user_id}")

    user_address = compute_create2_address(
        salt=user_id,
    )

    logger.info(f"Deposit address for user with id: {user_id} is {user_address}")

    tx_hash = await _send_deposits(
        w3, test_token, account=account, user_address=user_address, logger=logger, nonce=nonce
    )
    logger.info(f"Transferring to user with id: {user_id} is completed")
    return tx_hash


async def check_transactions_receipt(w3: AsyncWeb3, txs_hash: list[HexBytes]) -> list[TxReceipt | BaseException]:
    tasks = [asyncio.create_task(w3.eth.wait_for_transaction_receipt(tx_hash)) for tx_hash in txs_hash]
    tx_receipts = await asyncio.gather(*tasks, return_exceptions=True)
    return tx_receipts


async def transfer_test_tokens(chain: EVMConfig):
    _logger = ChainLoggerAdapter(logger, chain.chain_symbol)
    w3 = get_evm_async_client(chain, _logger).client
    account = w3.eth.account.from_key(HOLDER_PRIVATE_KEY)
    test_tokens = [token for token in TEST_TOKENS if token.chain_symbol == chain.chain_symbol]
    if len(test_tokens) == 0:
        _logger.warning("No token for transfer found")
        return
    while True:
        nonce = await w3.eth.get_transaction_count(account.address, "pending")
        last_transferred_user_id = await get_last_transferred_id(chain.chain_symbol) or 0

        last_user_id = await _get_last_user_id() or 0

        if last_transferred_user_id == last_user_id:
            _logger.info("There is no new user to transfer to")
            await asyncio.sleep(60)
            continue

        broadcast_tasks = []
        for id_ in range(last_transferred_user_id + 1, min(last_transferred_user_id + 15, last_user_id + 1)):
            broadcast_tasks.append(
                asyncio.create_task(
                    _send_token_to_user_id(
                        w3, test_tokens[0], user_id=id_, account=account, logger=_logger, nonce=Nonce(nonce)
                    )
                )
            )
            nonce += 1
        txs_hash = await asyncio.gather(*broadcast_tasks)
        _ = await check_transactions_receipt(w3, txs_hash)
        await upsert_last_transferred_id(chain.chain_symbol, len(txs_hash) + last_transferred_user_id)


async def main():
    loop = asyncio.get_running_loop()
    tasks = [
        loop.create_task(transfer_test_tokens(chain))
        for chain in CHAINS_CONFIG.values()
        if isinstance(chain, EVMConfig)
    ]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
