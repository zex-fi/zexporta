import asyncio
from functools import lru_cache
from typing import Iterable, overload

from clients import Transfer
from pymongo import ASCENDING, DESCENDING

from zexporta.custom_types import (
    Address,
    BlockNumber,
    BTCConfig,
    BTCTransfer,
    ChainConfig,
    Deposit,
    DepositStatus,
    EVMConfig,
    EVMTransfer,
    TxHash,
)

from .db import get_db_connection


@lru_cache()
def get_collection(chain: ChainConfig):
    match chain:
        case EVMConfig():
            collection = get_db_connection()["evm_deposit"]
            asyncio.run_coroutine_threadsafe(
                collection.create_index(("transfer.tx_hash", "transfer.chain_symbol"), unique=True),
                asyncio.get_event_loop(),
            )
        case BTCConfig():
            collection = get_db_connection()["btc_deposit"]
            asyncio.run_coroutine_threadsafe(
                collection.create_index(("transfer.tx_hash", "transfer.chain_symbol", "transfer.index"), unique=True),
                asyncio.get_event_loop(),
            )
        case _:
            raise NotImplementedError()
    return collection


async def insert_deposit_if_not_exists(chain: ChainConfig, deposit: Deposit):
    collection = get_collection(chain)
    query = {
        "transfer.chain_symbol": deposit.transfer.chain_symbol,
        "transfer.tx_hash": deposit.transfer.tx_hash,
    }
    record = await collection.find_one(query)
    if not record:
        await collection.insert_one(deposit.model_dump(mode="json"))


async def insert_deposits_if_not_exists(chain: ChainConfig, deposits: Iterable[Deposit]):
    await asyncio.gather(*[insert_deposit_if_not_exists(chain, deposit) for deposit in deposits])


@overload
async def find_deposit_by_status(
    chain: BTCConfig,
    status: DepositStatus,
    from_block: BlockNumber | None = None,
    to_block: BlockNumber | None = None,
    limit: int = 0,
    txs_hash: list[TxHash] | None = None,
) -> list[Deposit[BTCTransfer]]: ...


@overload
async def find_deposit_by_status(
    chain: EVMConfig,
    status: DepositStatus,
    from_block: BlockNumber | None = None,
    to_block: BlockNumber | None = None,
    limit: int = 0,
    txs_hash: list[TxHash] | None = None,
) -> list[Deposit[EVMTransfer]]: ...


@overload
async def find_deposit_by_status(
    chain: ChainConfig,
    status: DepositStatus,
    from_block: BlockNumber | None = None,
    to_block: BlockNumber | None = None,
    limit: int = 0,
    txs_hash: list[TxHash] | None = None,
) -> list[Deposit[Transfer]]: ...


async def find_deposit_by_status(
    chain: ChainConfig,
    status: DepositStatus,
    from_block: BlockNumber | None = None,
    to_block: BlockNumber | None = None,
    limit: int = 0,
    txs_hash: list[TxHash] | None = None,
) -> list[Deposit]:
    collection = get_collection(chain)
    res = []
    block_number_query = {"$gte": from_block or 0}
    if to_block:
        block_number_query["$lte"] = to_block

    query = {
        "status": status.value,
        "transfer.block_number": block_number_query,
        "transfer.chain_symbol": chain.chain_symbol,
    }
    if txs_hash:
        query["transfer.tx_hash"] = {"$in": txs_hash}

    async for record in collection.find(query, sort={"transfer.block_number": ASCENDING}).limit(limit):
        transfer = chain.transfer_class(**record["transfer"])
        del record["transfer"]
        res.append(Deposit(transfer=transfer, **record))
    return res


async def find_address_deposits(
    chain: ChainConfig, address: Address, status: DepositStatus | None = None
) -> list[Deposit]:
    collection = get_collection(chain)
    res = []
    query = {
        "transfer.chain_symbol": chain.chain_symbol,
        "transfer.to": address,
    }
    if status is not None:
        query["status"] = status.value

    async for record in collection.find(query, sort={"transfer.block_number": DESCENDING}):
        transfer = chain.transfer_class(**record["transfer"])
        del record["transfer"]
        res.append(Deposit(transfer=transfer, **record))
    return res


async def update_deposit_status(chain: ChainConfig, tx_hash: TxHash, new_status: DepositStatus):
    collection = get_collection(chain)
    await collection.update_one({"transfer.tx_hash": tx_hash}, {"$set": {"status": new_status}})


async def delete_deposit(chain: ChainConfig, tx_hash: TxHash):
    collection = get_collection(chain)
    await collection.delete_one({"transfer.tx_hash": tx_hash})


async def to_finalized(
    chain: ChainConfig,
    finalized_block_number: BlockNumber,
    txs_hash: list[TxHash],
):
    collection = get_collection(chain)
    query = {
        "status": DepositStatus.PENDING.value,
        "transfer.block_number": {"$lte": finalized_block_number},
        "transfer.tx_hash": {"$in": txs_hash},
        "transfer.chain_symbol": chain.chain_symbol,
    }

    update = {"$set": {"status": DepositStatus.FINALIZED.value}}

    await collection.update_many(query, update)


async def to_reorg_block_number(
    chain: ChainConfig,
    from_block: BlockNumber,
    to_block: BlockNumber,
    status: DepositStatus = DepositStatus.PENDING,
):
    collection = get_collection(chain)
    query = {
        "status": status.value,
        "transfer.block_number": {"$lte": to_block, "$gte": from_block},
        "transfer.chain_symbol": chain.chain_symbol,
    }
    update = {"$set": {"status": DepositStatus.REORG.value}}
    await collection.update_many(query, update)


async def to_reorg_with_tx_hash(
    chain: ChainConfig,
    txs_hash: list[TxHash],
    status: DepositStatus = DepositStatus.PENDING,
):
    collection = get_collection(chain)
    query = {
        "status": status.value,
        "transfer.chain_symbol": chain.chain_symbol,
        "transfer.tx_hash": {"$in": txs_hash},
    }
    update = {"$set": {"status": DepositStatus.REORG.value}}
    await collection.update_many(query, update)


async def get_pending_deposits_block_number(
    chain: ChainConfig, finalized_block_number: BlockNumber
) -> list[BlockNumber]:
    collection = get_collection(chain)
    query = {
        "status": DepositStatus.PENDING.value,
        "transfer.chain_symbol": chain.chain_symbol,
        "transfer.block_number": {"$lte": finalized_block_number},
    }
    block_numbers = set()
    async for record in collection.find(
        query,
        sort=[("transfer.block_number", ASCENDING)],
    ):
        block_numbers.add(record["transfer"]["block_number"])
    return list(block_numbers)


async def get_block_numbers_by_status(chain: ChainConfig, status: DepositStatus) -> list[BlockNumber]:
    collection = get_collection(chain)
    query = {"transfer.chain_symbol": chain.chain_symbol, "status": status.value}
    block_numbers = set()
    async for record in collection.find(
        query,
        sort=[("transfer.block_number", ASCENDING)],
    ):
        block_numbers.add(record["transfer"]["block_number"])
    return list(block_numbers)


async def upsert_deposit(chain: ChainConfig, deposit: Deposit):
    collection = get_collection(chain)
    update = {
        "$set": deposit.model_dump(mode="json"),
    }
    filter_ = {
        "transfer.tx_hash": deposit.transfer.tx_hash,
        "transfer.chain_symbol": deposit.transfer.chain_symbol,
    }
    await collection.update_one(filter=filter_, update=update, upsert=True)


async def upsert_deposits(chain: ChainConfig, deposits: list[Deposit]):
    await asyncio.gather(*[upsert_deposit(chain, deposit) for deposit in deposits])
