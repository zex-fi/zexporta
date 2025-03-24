from contextlib import asynccontextmanager
from enum import StrEnum
from json import JSONDecodeError

import httpx
from clients import BTCConfig

from zexporta.config import ZEX_BASE_URL
from zexporta.custom_types import (
    BlockNumber,
    ChainConfig,
    EVMConfig,
    UserId,
    WithdrawRequest,
    WithdrawStatus,
    ZexUserAsset,
)


class ZexPath(StrEnum):
    LAST_USER_ID = "/users/latest-id"
    DEPOSIT = "/deposit"
    LATEST_BLOCK = "/block/latest"
    WITHDRAWS = "/withdraws"
    LAST_WITHDRAW_NONCE = "/withdraw/nonce/last"
    EXCHANGE_INFO = "/exchangeInfo"
    USER_ASSET = "/asset/getUserAsset"
    USER_WITHDRAW_NONCE = "/user/withdraws/nonce"
    WITHDRAW = "/withdraw"


class ZexAPIError(Exception):
    pass


@asynccontextmanager
async def get_async_client():
    async with httpx.AsyncClient() as client:
        yield client


async def get_last_zex_user_id(async_client: httpx.AsyncClient) -> UserId | None:
    try:
        res = await async_client.get(f"{ZEX_BASE_URL}{ZexPath.LAST_USER_ID.value}")
        res.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        raise ZexAPIError(e)  # noqa: B904 FIXME
    else:
        return res.json().get("id")


async def send_deposits(async_client: httpx.AsyncClient, deposits: list):
    try:
        res = await async_client.post(
            url=f"{ZEX_BASE_URL}{ZexPath.DEPOSIT.value}",
            json=deposits,
        )
        res.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        raise ZexAPIError(e)  # noqa: B904 FIXME
    return res.json()


async def get_zex_latest_block(async_client: httpx.AsyncClient, chain: EVMConfig) -> BlockNumber | None:
    try:
        res = await async_client.get(
            url=f"{ZEX_BASE_URL}{ZexPath.LATEST_BLOCK.value}",
            params={"chain": chain.chain_symbol},
        )
        res.raise_for_status()
        return res.json().get("block")
    except (
        httpx.RequestError,
        httpx.HTTPStatusError,
        JSONDecodeError,
        AttributeError,
    ) as e:
        raise ZexAPIError(e)  # noqa: B904 FIXME


async def get_zex_last_withdraw_nonce(async_client: httpx.AsyncClient, chain: ChainConfig) -> int:
    try:
        res = await async_client.get(
            url=f"{ZEX_BASE_URL}{ZexPath.LAST_WITHDRAW_NONCE.value}",
            params={"chain": chain.chain_symbol},
        )
        if res.status_code == httpx.codes.NOT_FOUND:
            return -1
        res.raise_for_status()
        return res.json().get("nonce")
    except (
        httpx.RequestError,
        httpx.HTTPStatusError,
        JSONDecodeError,
        AttributeError,
    ) as e:
        raise ZexAPIError(e)  # noqa: B904 FIXME


async def get_zex_withdraws(
    async_client: httpx.AsyncClient,
    chain: ChainConfig,
    offset: int,
    limit: int | None = None,
) -> list[WithdrawRequest]:
    from web3 import Web3

    params = dict()
    if limit is not None:
        params["limit"] = limit
    try:
        res = await async_client.get(
            url=f"{ZEX_BASE_URL}{ZexPath.WITHDRAWS.value}",
            params={"chain": chain.chain_symbol, "offset": offset, **params},
            headers={"accept": "application/json"},
        )
        res.raise_for_status()
        withdraws = res.json()
        if not len(withdraws):
            raise ZexAPIError("Active withdraw not been found.")

        result = []
        for withdraw in withdraws:
            match chain:
                case BTCConfig():
                    address_type = str
                    base_conf = {}
                case EVMConfig():
                    address_type = Web3.to_checksum_address
                    base_conf = {
                        "chain_id": chain.chain_id,
                        "token_address": address_type(withdraw.get("tokenContract")),
                    }
                case _:
                    raise NotImplementedError

            result.append(
                chain.withdraw_request_type(
                    amount=withdraw.get("amount"),
                    nonce=withdraw.get("nonce"),
                    recipient=address_type(withdraw.get("destination")),
                    chain_symbol=chain.chain_symbol,
                    status=WithdrawStatus.PENDING,
                    user_id=withdraw.get("user_id"),
                    **base_conf,
                )
            )
        return result
    except (httpx.RequestError, httpx.HTTPStatusError, JSONDecodeError) as e:
        raise ZexAPIError(e)  # noqa: B904 FIXME


async def get_exchange_info(async_client: httpx.AsyncClient) -> dict:
    try:
        res = await async_client.get(
            f"{ZEX_BASE_URL}{ZexPath.EXCHANGE_INFO}",
            headers={"accept": "application/json"},
        )
        res.raise_for_status()
        return res.json()
    except (httpx.RequestError, httpx.HTTPStatusError, JSONDecodeError) as e:
        raise ZexAPIError(e)  # noqa: B904 FIXME


async def get_user_asset(
    async_client: httpx.AsyncClient,
    user_id: UserId,
) -> list[ZexUserAsset]:
    try:
        res = await async_client.get(
            f"{ZEX_BASE_URL}{ZexPath.USER_ASSET}",
            headers={"accept": "application/json"},
            params={"id": user_id},
        )
        res.raise_for_status()
        return [ZexUserAsset(**user_asset) for user_asset in res.json()]
    except (httpx.RequestError, httpx.HTTPStatusError, JSONDecodeError) as e:
        raise ZexAPIError(e)  # noqa: B904 FIXME


async def get_user_withdraw_nonce(async_client: httpx.AsyncClient, chain: EVMConfig, user_id: UserId) -> int:
    try:
        res = await async_client.get(
            f"{ZEX_BASE_URL}{ZexPath.USER_WITHDRAW_NONCE}",
            headers={"accept": "application/json"},
            params={"id": user_id, "chain": chain.chain_symbol},
        )
        res.raise_for_status()
        data = res.json()
        return data["nonce"]
    except (httpx.RequestError, httpx.HTTPStatusError, JSONDecodeError) as e:
        raise ZexAPIError(e)  # noqa: B904 FIXME


async def send_withdraw_request(async_client: httpx.AsyncClient, withdraws: list[str]):
    try:
        res = await async_client.post(
            url=f"{ZEX_BASE_URL}{ZexPath.WITHDRAW.value}",
            json=withdraws,
        )
        res.raise_for_status()
        return res.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        raise ZexAPIError(e)  # noqa: B904 FIXME
