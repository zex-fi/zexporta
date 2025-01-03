import asyncio
import logging

from eth_typing import HexStr
from pymongo import DESCENDING
from web3 import Web3

from zexporta.custom_types import ChecksumAddress, UserAddress, UserId
from zexporta.utils.web3 import compute_create2_address
from zexporta.utils.zex_api import (
    ZexAPIError,
    get_async_client,
    get_last_zex_user_id,
)

from .collections import db
from .config import (
    USER_DEPOSIT_BYTECODE_HASH,
    USER_DEPOSIT_FACTORY_ADDRESS,
)


async def __create_address_index():
    await _address_collection.create_index("user_id", unique=True)
    await _address_collection.create_index("address", unique=True)


_address_collection = db["user_addresses"]
asyncio.run(__create_address_index())


class UserNotExists(Exception):
    pass


logger = logging.getLogger(__name__)


async def get_active_address() -> dict[ChecksumAddress, UserId]:
    res = dict()
    async for address in _address_collection.find({"is_active": True}):
        res[Web3.to_checksum_address(address["address"])] = address["user_id"]
    return res


async def get_last_user_id() -> UserId:
    result = await _address_collection.find_one(
        {"is_active": True}, sort=[("user_id", DESCENDING)]
    )
    if result:
        return result["user_id"]
    raise UserNotExists()


async def insert_user_address(address: UserAddress):
    await _address_collection.insert_one(address.model_dump(mode="json"))


async def insert_many_user_address(users_address: list[UserAddress]):
    await _address_collection.insert_many(
        user_address.model_dump(mode="json") for user_address in users_address
    )


def get_users_address_to_insert(
    first_to_compute: UserId, last_to_compute: UserId
) -> list[UserAddress]:
    users_address_to_insert = []
    for user_id in range(first_to_compute, last_to_compute + 1):
        users_address_to_insert.append(
            UserAddress(
                user_id=user_id,
                address=compute_create2_address(
                    deployer_address=USER_DEPOSIT_FACTORY_ADDRESS,
                    salt=user_id,
                    bytecode_hash=HexStr(USER_DEPOSIT_BYTECODE_HASH),
                ),
            )
        )
    return users_address_to_insert


async def insert_new_address_to_db():
    async with get_async_client() as client:
        try:
            last_zex_user_id = await get_last_zex_user_id(client)
        except ZexAPIError as e:
            logger.error(f"Error in Zex API: {e}")
            return

    if last_zex_user_id is None:
        return
    try:
        first_id_to_compute = await get_last_user_id() + 1
    except UserNotExists:
        first_id_to_compute = 0
    users_address_to_insert = get_users_address_to_insert(
        first_id_to_compute, last_zex_user_id
    )
    if len(users_address_to_insert) == 0:
        return
    await insert_many_user_address(users_address=users_address_to_insert)
