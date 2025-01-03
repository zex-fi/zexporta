import asyncio
from typing import Iterable

from eth_typing import ChainId
from pymongo import ASCENDING

from zexporta.custom_types import BlockNumber, TransferStatus, UserTransfer

from .collections import db


async def __create_transfer_index():
    await _transfer_collection.create_index(("tx_hash", "chain_id"), unique=True)


_transfer_collection = db["transfer"]
asyncio.run(__create_transfer_index())


async def insert_transfer_if_not_exists(transfer: UserTransfer):
    query = {
        "chain_id": transfer.chain_id,
        "tx_hash": transfer.tx_hash,
    }
    record = await _transfer_collection.find_one(query)
    if not record:
        await _transfer_collection.insert_one(transfer.model_dump(mode="json"))


async def insert_transfers_if_not_exists(transfers: Iterable[UserTransfer]):
    await asyncio.gather(
        *[insert_transfer_if_not_exists(transfer) for transfer in transfers]
    )


async def find_transactions_by_status(
    status: TransferStatus,
    chain_id: ChainId,
    from_block: BlockNumber | int | None = None,
) -> list[UserTransfer]:
    res = []
    query = {
        "status": status.value,
        "chain_id": chain_id.value,
        "block_number": {"$gte": from_block or 0},
    }
    async for record in _transfer_collection.find(
        query, sort={"block_number": ASCENDING}
    ):
        res.append(UserTransfer(**record))
    return res


async def update_transaction_status(tx_hash, new_status):
    await _transfer_collection.update_one(
        {"tx_hash": tx_hash}, {"$set": {"status": new_status}}
    )


async def delete_transaction(tx_hash):
    await _transfer_collection.delete_one({"tx_hash": tx_hash})


async def to_finalized(
    chain_id: ChainId,
    finalized_block_number: BlockNumber,
    tx_hashes: list[str],
):
    query = {
        "block_number": {"$lte": finalized_block_number},
        "status": TransferStatus.PENDING.value,
        "tx_hash": {"$in": tx_hashes},
        "chain_id": chain_id.value,
    }

    update = {"$set": {"status": TransferStatus.FINALIZED.value}}

    await _transfer_collection.update_many(query, update)


async def to_reorg(
    chain_id: ChainId,
    from_block: BlockNumber | int,
    to_block: BlockNumber | int,
    status: TransferStatus = TransferStatus.PENDING,
):
    query = {
        "block_number": {"$lte": to_block, "$gte": from_block},
        "status": status.value,
        "chain_id": chain_id.value,
    }
    update = {"$set": {"status": TransferStatus.REORG.value}}
    await _transfer_collection.update_many(query, update)


async def get_pending_transfers_block_number(
    chain_id: ChainId, finalized_block_number: BlockNumber
) -> list[BlockNumber]:
    query = {
        "chain_id": chain_id.value,
        "status": TransferStatus.PENDING.value,
        "block_number": {"$lte": finalized_block_number},
    }
    block_numbers = set()
    async for record in _transfer_collection.find(
        query,
        sort=[("block_number", ASCENDING)],
    ):
        block_numbers.add(BlockNumber(record["block_number"]))
    return list(block_numbers)


async def get_block_numbers_by_status(
    chain_id: ChainId, status: TransferStatus
) -> list[BlockNumber]:
    query = {"chain_id": chain_id.value, "status": status.value}
    block_numbers = set()
    async for record in _transfer_collection.find(
        query,
        sort=[("block_number", ASCENDING)],
    ):
        block_numbers.add(BlockNumber(record["block_number"]))
    return list(block_numbers)


async def upsert_transfer(transfer: UserTransfer):
    update = {
        "$set": transfer.model_dump(mode="json"),
    }
    filter_ = {
        "tx_hash": transfer.tx_hash,
        "chain_id": transfer.chain_id,
    }
    await _transfer_collection.update_one(filter=filter_, update=update, upsert=True)


async def upsert_transfers(transfers: list[UserTransfer]):
    await asyncio.gather(*[upsert_transfer(transfer) for transfer in transfers])
