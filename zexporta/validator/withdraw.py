import asyncio
from logging import LoggerAdapter

import httpx

from zexporta.custom_types import ChainConfig, WithdrawRequest
from zexporta.utils.encoder import get_withdraw_hash
from zexporta.utils.zex_api import get_zex_withdraws

limit_tx = 1


async def get_withdraw_request(
    chain: ChainConfig, sa_withdraw_nonce: int, logger: LoggerAdapter
) -> WithdrawRequest:
    async with httpx.AsyncClient() as client:
        withdraw = (
            await get_zex_withdraws(
                client, chain, offset=sa_withdraw_nonce, limit=sa_withdraw_nonce + 1
            )
        )[0]

    return withdraw


def withdraw(chain: ChainConfig, sa_withdraw_nonce: int, logger: LoggerAdapter):
    withdraw_request = asyncio.run(
        get_withdraw_request(chain, sa_withdraw_nonce, logger)
    )
    zex_withdraw_hash = get_withdraw_hash(withdraw_request)

    logger.info(f"hash for withdraw is: {zex_withdraw_hash}")
    return {
        "hash": zex_withdraw_hash,
        "data": withdraw_request.model_dump(mode="json"),
    }
