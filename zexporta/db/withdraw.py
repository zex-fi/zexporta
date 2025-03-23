import asyncio
from typing import Iterable

from pymongo import ASCENDING, DESCENDING

from zexporta.custom_types import (
    ChainConfig,
    UserId,
    WithdrawRequest,
    WithdrawStatus,
)

from .db import get_db_connection


async def __create_withdraw_index(collection):
    await collection.create_index(("nonce", "chain_symbol"), unique=True)


def get_collection():
    collection = get_db_connection()["withdraw"]
    asyncio.run_coroutine_threadsafe(
        __create_withdraw_index(collection),
        asyncio.get_event_loop(),
    )
    return collection


async def insert_withdraw_if_not_exists(withdraw: WithdrawRequest):
    query = {
        "chain_symbol": withdraw.chain_symbol,
        "nonce": withdraw.nonce,
    }
    record = await get_collection().find_one(query)
    if not record:
        await get_collection().insert_one(withdraw.model_dump(mode="json"))


async def insert_withdraws_if_not_exists(withdraws: Iterable[WithdrawRequest]):
    await asyncio.gather(*[insert_withdraw_if_not_exists(withdraw) for withdraw in withdraws])


async def upsert_withdraw(withdraw: WithdrawRequest):
    update = {
        "$set": withdraw.model_dump(mode="json"),
    }
    filter_ = {
        "nonce": withdraw.nonce,
        "chain_symbol": withdraw.chain_symbol,
    }
    await get_collection().update_one(filter=filter_, update=update, upsert=True)


async def upsert_withdraws(withdraws: list[WithdrawRequest]):
    await asyncio.gather(*[upsert_withdraw(withdraw) for withdraw in withdraws])


async def find_withdraws_by_status(
    chain: ChainConfig,
    status: WithdrawStatus,
    nonce: int = 0,
) -> list[WithdrawRequest]:
    res = []
    query = {
        "status": status.value,
        "chain_symbol": chain.chain_symbol,
        "nonce": {"$gte": nonce},
    }

    async for record in get_collection().find(query, sort={"nonce": ASCENDING}):
        res.append(chain.withdraw_request_type(**record))
    return res


async def find_user_withdraws(
    chain: ChainConfig,
    user_id: UserId,
    status: WithdrawStatus | None,
) -> list[WithdrawRequest]:
    res = []
    query = {
        "chain_symbol": chain.chain_symbol,
        "user_id": user_id,
    }
    if status is not None:
        query["status"] = status

    async for record in get_collection().find(query, sort={"nonce": DESCENDING}):
        res.append(chain.withdraw_request_type(**record))
    return res


async def find_withdraw_by_nonce(
    chain: ChainConfig,
    nonce,
) -> WithdrawRequest | None:
    query = {
        "chain_symbol": chain.chain_symbol,
        "nonce": nonce,
    }
    record = await get_collection().find_one(query)

    if record is not None:
        return chain.withdraw_request_type(**record)
    return None
