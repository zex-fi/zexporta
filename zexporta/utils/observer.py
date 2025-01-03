import logging
from typing import Any, Callable, Coroutine

import web3.exceptions
from eth_typing import ChainId, HexStr
from pydantic import BaseModel, ConfigDict
from web3 import AsyncWeb3

from zexporta.custom_types import (
    BlockNumber,
    ChainConfig,
    ChecksumAddress,
    RawTransfer,
    UserId,
    UserTransfer,
)
from zexporta.db.token import get_decimals, insert_token
from zexporta.utils.logger import ChainLoggerAdapter

from .web3 import filter_blocks
from .web3 import get_token_decimals as w3_get_token_decimals

logger = logging.getLogger(__name__)


def get_block_batches(
    from_block: BlockNumber | int,
    to_block: BlockNumber | int,
    *,
    batch_size: int = 5,
) -> list[tuple[BlockNumber, ...]]:
    block_batches = [
        tuple(BlockNumber(j) for j in range(i, min(to_block + 1, i + batch_size)))
        for i in range(from_block, to_block + 1, batch_size)
    ]
    return block_batches


class Observer(BaseModel):
    model_config: ConfigDict = {"arbitrary_types_allowed": True}
    chain: ChainConfig
    w3: AsyncWeb3

    async def observe(
        self,
        from_block: BlockNumber | int,
        to_block: BlockNumber | int,
        accepted_addresses: dict[ChecksumAddress, UserId],
        extract_block_logic: Callable[..., Coroutine[Any, Any, list[RawTransfer]]],
        *,
        batch_size=5,
        max_delay_per_block_batch: int | float = 10,
        logger: logging.Logger | ChainLoggerAdapter = logger,
        **kwargs,
    ) -> list[UserTransfer]:
        result = []
        block_batches = get_block_batches(from_block, to_block, batch_size=batch_size)
        for blocks_number in block_batches:
            logger.info(f"batch_blocks: {blocks_number}")
            transfers = await filter_blocks(
                self.w3,
                blocks_number,
                extract_block_logic,
                chain_id=self.chain.chain_id,
                max_delay_per_block_batch=max_delay_per_block_batch,
                logger=logger,
                **kwargs,
            )
            accepted_transfers = await get_accepted_transfers(
                self.w3, self.chain, transfers, accepted_addresses
            )
            result.extend(accepted_transfers)
        return result


async def get_token_decimals(
    w3: AsyncWeb3, chain_id: ChainId, token_address: ChecksumAddress
) -> int:
    decimals = await get_decimals(chain_id, token_address)
    if decimals is None:
        decimals = await w3_get_token_decimals(w3, token_address)
        await insert_token(chain_id, token_address, decimals)
    return decimals


async def get_accepted_transfers(
    w3: AsyncWeb3,
    chain: ChainConfig,
    transfers: list[RawTransfer],
    accepted_addresses: dict[ChecksumAddress, UserId],
) -> list[UserTransfer]:
    result = []
    for transfer in transfers:
        if (user_id := accepted_addresses.get(transfer.to)) is not None:
            decimals = await get_token_decimals(w3, chain.chain_id, transfer.token)
            try:
                receipt = await w3.eth.get_transaction_receipt(HexStr(transfer.tx_hash))
                if receipt["status"] == 1:
                    result.append(
                        UserTransfer(
                            user_id=user_id,
                            decimals=decimals,
                            **transfer.model_dump(mode="json"),
                        )
                    )
            except web3.exceptions.TransactionNotFound as e:
                logger.error(f"TransactionNotFound: {e}")
    return result
