import asyncio
import logging
import logging.config

import sentry_sdk
import web3.exceptions
from eth_typing import ChecksumAddress

from zexporta.custom_types import ChainConfig, RawTransfer
from zexporta.db.address import get_active_address, insert_new_address_to_db
from zexporta.db.chain import (
    get_last_observed_block,
    upsert_chain_last_observed_block,
)
from zexporta.db.transfer import insert_transfers_if_not_exists
from zexporta.utils.logger import ChainLoggerAdapter, get_logger_config
from zexporta.utils.observer import Observer
from zexporta.utils.web3 import (
    async_web3_factory,
    extract_transfer_from_block,
)

from .config import CHAINS_CONFIG, LOGGER_PATH, SENTRY_DNS

logging.config.dictConfig(get_logger_config(logger_path=f"{LOGGER_PATH}/observer.log"))
logger = logging.getLogger(__name__)


async def filter_transfer(
    transfers: list[RawTransfer], accepted_addresses: set[ChecksumAddress]
) -> tuple[RawTransfer, ...]:
    return tuple(filter(lambda transfer: transfer.to in accepted_addresses, transfers))


async def observe_deposit(chain: ChainConfig):
    _logger = ChainLoggerAdapter(logger, chain.chain_id.name)
    last_observed_block = await get_last_observed_block(chain.chain_id)
    while True:
        w3 = await async_web3_factory(chain)
        observer = Observer(chain=chain, w3=w3)
        accepted_addresses = await get_active_address()
        latest_block = await w3.eth.get_block_number()
        if last_observed_block is not None and last_observed_block == latest_block:
            _logger.info(f"Block {last_observed_block} already observed continue")
            await asyncio.sleep(chain.delay)
            continue
        last_observed_block = last_observed_block or latest_block
        if last_observed_block >= latest_block:
            _logger.warning(
                f"last_observed_block: {last_observed_block} is bigger then latest_block {latest_block}"
            )
            continue
        await insert_new_address_to_db()
        try:
            accepted_transfers = await observer.observe(
                last_observed_block + 1,
                latest_block,
                accepted_addresses,
                extract_transfer_from_block,
                logger=_logger,
                batch_size=chain.batch_block_size,
                max_delay_per_block_batch=chain.delay,
            )
        except web3.exceptions.BlockNotFound as e:
            _logger.warning(f"Block not found: {latest_block}, error: {e}")
        if len(accepted_transfers) > 0:
            await insert_transfers_if_not_exists(accepted_transfers)
        await upsert_chain_last_observed_block(chain.chain_id, latest_block)
        last_observed_block = latest_block


async def main():
    loop = asyncio.get_running_loop()
    tasks = [
        loop.create_task(observe_deposit(chain)) for chain in CHAINS_CONFIG.values()
    ]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    sentry_sdk.init(
        dsn=SENTRY_DNS,
    )
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
