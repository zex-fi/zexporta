import asyncio
import json
import logging.config
from typing import cast

import sentry_sdk
import web3.exceptions
from clients import BTCConfig, ChainConfig, WithdrawRequest
from clients.btc.custom_types import BTCWithdrawRequest
from clients.evm.custom_types import EVMWithdrawRequest
from pyfrost.network.sa import SA

from zexporta.custom_types import (
    EVMConfig,
    WithdrawStatus,
)
from zexporta.db.withdraw import find_withdraws_by_status, upsert_withdraw
from zexporta.utils.abi import VAULT_ABI
from zexporta.utils.decode_error import decode_custom_error_data
from zexporta.utils.dkg import parse_dkg_json
from zexporta.utils.encoder import get_evm_withdraw_hash
from zexporta.utils.logger import ChainLoggerAdapter, get_logger_config
from zexporta.utils.node_info import NodesInfo
from zexporta.utils.zex_api import (
    ZexAPIError,
)
from zexporta.withdraw.btc import send_btc_withdraw
from zexporta.withdraw.evm import send_evm_withdraw

from .config import (
    CHAINS_CONFIG,
    DKG_JSON_PATH,
    DKG_NAME,
    LOGGER_PATH,
    SA_DELAY_SECOND,
    SA_TIMEOUT,
    SENTRY_DNS,
)


class WithdrawDifferentHashError(Exception):
    """Raise when validator hash is different from sa hash"""


class ValidatorResultError(Exception):
    """Raise when validator result is not successful"""


logging.config.dictConfig(get_logger_config(f"{LOGGER_PATH}/sa.log"))
logger = logging.getLogger(__name__)

nodes_info = NodesInfo()
sa = SA(nodes_info, default_timeout=SA_TIMEOUT)
dkg_key = parse_dkg_json(DKG_JSON_PATH, DKG_NAME)


async def check_validator_data(
    chain: ChainConfig,
    zex_withdraw: WithdrawRequest,
    validator_hash: str,
):
    match chain:
        case EVMConfig():
            withdraw_hash = get_evm_withdraw_hash(zex_withdraw)  # type: ignore
        case BTCConfig():
            # todo :: fix in distributed signing version
            withdraw_hash = validator_hash
        case _:
            raise NotImplementedError

    if withdraw_hash != validator_hash:
        raise WithdrawDifferentHashError(f"validator_hash: {validator_hash}, withdraw_hash: {withdraw_hash}")


async def process_withdraw_sa(
    chain: ChainConfig,
    withdraw_request: WithdrawRequest,
    dkg_party,
    logger: ChainLoggerAdapter,
):
    # todo :: fix in distributed signing version
    match chain:
        case EVMConfig():
            nonces_response = await sa.request_nonces(dkg_party, number_of_nonces=1)
            nonces_for_sig = {}
            for id, nonce in nonces_response.items():
                nonces_for_sig[id] = nonce["data"][0]

            data = {
                "method": "withdraw",
                "data": {
                    "chain_symbol": chain.chain_symbol,
                    "sa_withdraw_nonce": withdraw_request.nonce,
                },
            }
            logger.debug(f"Zex withdraw request is: {withdraw_request}")
            result = await sa.request_signature(dkg_key, nonces_for_sig, data, dkg_party)
            logger.debug(f"Validator results is: {result}")

            if result.get("result") == "SUCCESSFUL":
                validator_hash = result["message_hash"]
                await check_validator_data(chain=chain, zex_withdraw=withdraw_request, validator_hash=validator_hash)
                await send_evm_withdraw(
                    cast(EVMConfig, chain),
                    cast(EVMWithdrawRequest, withdraw_request),
                    result,
                    logger,
                )
            else:
                raise ValidatorResultError(result)

        case BTCConfig():
            await send_btc_withdraw(
                cast(BTCConfig, chain),
                cast(BTCWithdrawRequest, withdraw_request),
                {},
                logger,
            )
        case _:
            raise NotImplementedError


async def withdraw(chain: ChainConfig):
    _logger = ChainLoggerAdapter(logger, chain.chain_symbol)

    while True:
        try:
            dkg_party = dkg_key["party"]
            withdraws_requests = await find_withdraws_by_status(WithdrawStatus.PENDING, chain)
            if len(withdraws_requests) == 0:
                _logger.debug(f"No {WithdrawStatus.PENDING.value} has been found to process ...")
                continue
            for withdraw_request in withdraws_requests:
                try:
                    await process_withdraw_sa(
                        chain=chain,
                        withdraw_request=chain.withdraw_request_type(**withdraw_request.model_dump(mode="json")),
                        dkg_party=dkg_party,
                        logger=_logger,
                    )
                except ZexAPIError as e:
                    _logger.error(f"Error at sending deposit to Zex: {e}")
                    continue
                except (web3.exceptions.ContractCustomError,) as e:  # noqa: B013 TODO: fix this
                    _logger.error(
                        f"Contract Error, error: {e.message} , decoded_error: {decode_custom_error_data(e.message, VAULT_ABI)}"  # noqa: E501 TODO: fix this
                    )
                    withdraw_request.status = WithdrawStatus.REJECTED
                    await upsert_withdraw(withdraw_request)

                except web3.exceptions.Web3Exception as e:
                    _logger.error(f"Web3Error: {e}")
                    await asyncio.sleep(60)
                except AssertionError as e:
                    _logger.error(f"Validator error, error: {e}")
                    continue
                except (KeyError, json.JSONDecodeError, TypeError) as e:
                    _logger.exception(f"Error occurred in pyfrost, {e}")
                    continue
                except asyncio.TimeoutError as e:
                    _logger.error(f"Timeout occurred continue after 1 min, error {e}")
                    await asyncio.sleep(60)
                    continue
                except ValidatorResultError as e:
                    _logger.error(f"Validator result is not successful, error {e}")
                except WithdrawDifferentHashError as e:
                    _logger.error(f"data that process in zex is different from validators: {e}")
                    withdraw_request.status = WithdrawStatus.REJECTED
                    await upsert_withdraw(withdraw_request)
                else:
                    withdraw_request.status = WithdrawStatus.SUCCESSFUL
                    await upsert_withdraw(withdraw_request)
        finally:
            await asyncio.sleep(SA_DELAY_SECOND)


async def main():
    loop = asyncio.get_running_loop()
    tasks = [loop.create_task(withdraw(chain)) for chain in CHAINS_CONFIG.values() if isinstance(chain, EVMConfig)]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    sentry_sdk.init(
        dsn=SENTRY_DNS,
    )
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
