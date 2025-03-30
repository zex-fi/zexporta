import asyncio
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from typing import Iterable

from clients import get_compute_address_function
from pymongo import DESCENDING
from web3 import Web3

from zexporta.custom_types import (
    Address,
    BTCConfig,
    ChainConfig,
    EVMConfig,
    UserAddress,
    UserId,
)
from zexporta.utils.zex_api import (
    ZexAPIError,
    get_async_client,
    get_last_zex_user_id,
)

from .db import get_db_connection


async def __create_address_index(collection):
    await collection.create_index("user_id", unique=True)
    await collection.create_index("address", unique=True)


@lru_cache()
def get_collection(chain: ChainConfig):
    match chain:
        case EVMConfig():
            collection = get_db_connection()["evm_address"]
        case BTCConfig():
            collection = get_db_connection()["btc_address"]
        case _:
            raise NotImplementedError()
    asyncio.run_coroutine_threadsafe(__create_address_index(collection), asyncio.get_event_loop())
    return collection


class UserNotExists(Exception):
    pass


logger = logging.getLogger(__name__)
evm_lock = asyncio.Lock()
btc_lock = asyncio.Lock()


async def get_active_address(
    chain: ChainConfig,
) -> dict[Address, UserId]:
    res = dict()
    collection = get_collection(chain=chain)
    async for address in collection.find({"is_active": True}):
        match chain:
            case EVMConfig():
                key = Web3.to_checksum_address(address["address"])
            case BTCConfig():
                key = address["address"]
            case _:
                raise NotImplementedError("")
        res[key] = address["user_id"]
    return res


async def get_last_user_id(chain: ChainConfig) -> UserId:
    collection = get_collection(chain=chain)
    result = await collection.find_one({"is_active": True}, sort=[("user_id", DESCENDING)])
    if result:
        return result["user_id"]
    raise UserNotExists()


async def insert_user_address(chain: ChainConfig, address: UserAddress):
    collection = get_collection(chain=chain)
    await collection.insert_one(address.model_dump(mode="json"))


async def insert_many_user_address(chain: ChainConfig, users_address: Iterable[UserAddress]):
    collection = get_collection(chain=chain)
    await collection.insert_many(user_address.model_dump(mode="json") for user_address in users_address)


def _create_user_address_for_worker(chain: ChainConfig, user_id: UserId):
    address_function = get_compute_address_function(chain)
    return UserAddress(user_id=user_id, address=address_function(user_id))


async def get_users_address_to_insert(
    chain: ChainConfig, first_to_compute: UserId, last_to_compute: UserId, *, max_workers: int | None = None
) -> list[UserAddress]:
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor(max_workers=max_workers or os.cpu_count()) as executor:
        tasks = [
            loop.run_in_executor(executor, _create_user_address_for_worker, chain, user_id)
            for user_id in range(first_to_compute, last_to_compute + 1)
        ]

        result = await asyncio.gather(*tasks)
    return result


async def insert_new_address_to_db(chain: ChainConfig, *, max_workers: int | None = None):
    async with get_async_client() as client:
        try:
            last_zex_user_id = await get_last_zex_user_id(client)
        except ZexAPIError as e:
            logger.error(f"Error in Zex API: {e}")
            return

    if last_zex_user_id is None:
        return
    match chain:
        case EVMConfig():
            await evm_lock.acquire()
        case BTCConfig():
            await btc_lock.acquire()
    try:
        try:
            first_id_to_compute = await get_last_user_id(chain=chain) + 1
        except UserNotExists:
            first_id_to_compute = 0
        users_address_to_insert = await get_users_address_to_insert(
            chain, first_id_to_compute, last_zex_user_id, max_workers=max_workers
        )
        if len(users_address_to_insert) == 0:
            return
        await insert_many_user_address(chain, users_address=users_address_to_insert)
    finally:
        match chain:
            case EVMConfig():
                evm_lock.release()
            case BTCConfig():
                btc_lock.release()
