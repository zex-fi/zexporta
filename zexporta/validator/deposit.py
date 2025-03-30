import asyncio
import logging
from hashlib import sha256

from clients import get_async_client

from zexporta.custom_types import (
    BlockNumber,
    ChainConfig,
    DepositStatus,
    SaDepositSchema,
    Timestamp,
    TxHash,
)
from zexporta.db.address import get_active_address, insert_new_address_to_db
from zexporta.explorer import get_accepted_deposits
from zexporta.utils.encoder import DEPOSIT_OPERATION, encode_zex_deposit
from zexporta.utils.logger import ChainLoggerAdapter

from .config import MAX_WORKERS, ZEX_ENCODE_VERSION


class NoTxHashError(Exception):
    "Raise when a txs_hash list is empty"


class NotFinalizedBlockError(Exception):
    "Raise when a block number is bigger then current finalized block"


logger = logging.getLogger(__name__)


def deposit(chain: ChainConfig, data: SaDepositSchema, logger: ChainLoggerAdapter) -> dict:
    txs_hash = data.txs_hash
    if len(txs_hash) == 0:
        raise NoTxHashError()
    deposits = asyncio.run(
        get_deposits(
            chain=chain,
            txs_hash=txs_hash,
            sa_finalized_block_number=data.finalized_block_number,
            sa_timestamp=data.timestamp,
        )
    )
    encoded_data = encode_zex_deposit(
        version=ZEX_ENCODE_VERSION,
        operation_type=DEPOSIT_OPERATION,
        chain_symbol=chain.chain_symbol,
        deposits=deposits,
    )
    logger.info(f"encoded_data is: {encoded_data}")
    return {
        "hash": sha256(encoded_data).hexdigest(),
        "data": {
            "deposits": [deposit.model_dump(mode="json") for deposit in deposits],
        },
    }


async def get_deposits(
    chain: ChainConfig,
    txs_hash: list[TxHash],
    sa_finalized_block_number: BlockNumber,
    sa_timestamp: Timestamp,
):
    _logger = ChainLoggerAdapter(logger, chain.chain_symbol)
    client = get_async_client(chain=chain, logger=_logger)
    finalized_block_number = await client.get_finalized_block_number()
    if sa_finalized_block_number > finalized_block_number:
        raise NotFinalizedBlockError(
            f"sa_finalized_block_number: {sa_finalized_block_number} \
            is not finalized in validator , finalized_block: {finalized_block_number}"
        )
    await insert_new_address_to_db(chain, max_workers=MAX_WORKERS)
    accepted_addresses = await get_active_address(chain)
    transfers = await asyncio.gather(*[client.get_transfer_by_tx_hash(tx_hash) for tx_hash in txs_hash])
    flattened_transfers = []
    for item in transfers:
        if isinstance(item, list):
            flattened_transfers.extend(item)  # Add items of the list to the flat list
        else:
            flattened_transfers.append(item)
    transfers = flattened_transfers

    deposits = await get_accepted_deposits(
        client,
        [
            transfer
            for transfer in transfers
            if transfer is not None and transfer.block_number <= finalized_block_number
        ],
        accepted_addresses,
        deposit_status=DepositStatus.VERIFIED,
        sa_timestamp=sa_timestamp,
    )
    return sorted(deposits)
