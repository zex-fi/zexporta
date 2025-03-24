import asyncio
from logging import LoggerAdapter

import httpx
from clients import ChainConfig
from clients.evm.custom_types import EVMWithdrawRequest

from zexporta.custom_types import (
    BTCConfig,
    BTCWithdrawRequest,
    EVMConfig,
    WithdrawRequest,
)
from zexporta.utils.encoder import get_evm_withdraw_hash
from zexporta.utils.zex_api import get_zex_withdraws
from zexporta.withdraw.btc import get_simple_withdraw_tx

limit_tx = 1


async def get_withdraw_request(chain: ChainConfig, sa_withdraw_nonce: int, logger: LoggerAdapter) -> WithdrawRequest:
    async with httpx.AsyncClient() as client:
        withdraw = (await get_zex_withdraws(client, chain, offset=sa_withdraw_nonce, limit=sa_withdraw_nonce + 1))[0]

    return withdraw


def evm_withdraw(chain: EVMConfig, sa_withdraw_nonce: int, logger: LoggerAdapter):
    withdraw_request = asyncio.run(get_withdraw_request(chain, sa_withdraw_nonce, logger))
    zex_withdraw_hash = get_evm_withdraw_hash(EVMWithdrawRequest(**withdraw_request.model_dump(mode="json")))

    logger.info(f"hash for withdraw is: {zex_withdraw_hash}")
    return {
        "hash": zex_withdraw_hash,
        "data": withdraw_request.model_dump(mode="json"),
    }


async def btc_withdraw(chain: BTCConfig, sa_withdraw_nonce: int, logger: LoggerAdapter):
    # todo :: fix in distributed signing version

    withdraw_request = asyncio.run(get_withdraw_request(chain, sa_withdraw_nonce, logger))
    withdraw_request = BTCWithdrawRequest(**withdraw_request.model_dump(mode="json"))
    tx, _ = get_simple_withdraw_tx(withdraw_request, chain.vault_address, utxos=withdraw_request.utxos)
    zex_withdraw_hash = tx.to_hex()
    logger.info(f"hash for withdraw is: {zex_withdraw_hash}")

    return {
        "hash": zex_withdraw_hash,
        "data": withdraw_request.model_dump(mode="json"),
    }
