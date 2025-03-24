import asyncio
import json
import logging
import logging.config

import sentry_sdk
import web3.exceptions
from clients.evm import get_signed_data
from clients.evm.client import get_evm_async_client
from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress
from pyfrost.network.sa import SA
from web3 import AsyncWeb3, Web3

from zexporta.custom_types import (
    EVMConfig,
    EVMWithdrawRequest,
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

from .config import (
    CHAINS_CONFIG,
    DKG_JSON_PATH,
    DKG_NAME,
    EVM_WITHDRAWER_PRIVATE_KEY,
    LOGGER_PATH,
    SA_DELAY_SECOND,
    SA_SHIELD_PRIVATE_KEY,
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
    zex_withdraw: EVMWithdrawRequest,
    validator_hash: str,
):
    withdraw_hash = get_evm_withdraw_hash(zex_withdraw)
    if withdraw_hash != validator_hash:
        raise WithdrawDifferentHashError(f"validator_hash: {validator_hash}, withdraw_hash: {withdraw_hash}")


async def process_withdraw_sa(
    w3: AsyncWeb3,
    account: LocalAccount,
    chain: EVMConfig,
    withdraw_request: EVMWithdrawRequest,
    dkg_party,
    logger: ChainLoggerAdapter,
):
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
        await check_validator_data(zex_withdraw=withdraw_request, validator_hash=validator_hash)
        data = list(result["signature_data_from_node"].values())[0]
        await send_withdraw(
            w3,
            chain,
            account,
            result["signature"],
            withdraw_request,
            Web3.to_checksum_address(result["nonce"]),
            logger,
        )
    else:
        raise ValidatorResultError(result)


async def send_withdraw(
    w3: AsyncWeb3,
    chain: EVMConfig,
    account: LocalAccount,
    signature: str,
    withdraw_request: EVMWithdrawRequest,
    signature_nonce: ChecksumAddress,
    logger: logging.Logger | ChainLoggerAdapter = logger,
):
    vault = w3.eth.contract(address=Web3.to_checksum_address(chain.vault_address), abi=VAULT_ABI)
    nonce = await w3.eth.get_transaction_count(account.address)
    withdraw_hash = get_evm_withdraw_hash(withdraw_request)
    signed_data = get_signed_data(SA_SHIELD_PRIVATE_KEY, hexstr=withdraw_hash)
    logger.debug(f"Signed Withdraw data is: {signed_data}")
    tx = await vault.functions.withdraw(
        withdraw_request.token_address,
        withdraw_request.amount,
        withdraw_request.recipient,
        withdraw_request.nonce,
        signature,
        signature_nonce,
        signed_data,
    ).build_transaction({"from": account.address, "nonce": nonce})
    signed_tx = account.sign_transaction(tx)
    tx_hash = await w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    withdraw_request.tx_hash = tx_hash.hex()
    await w3.eth.wait_for_transaction_receipt(tx_hash)
    logger.info(f"Method called successfully. Transaction Hash: {tx_hash.hex()}")


async def withdraw(chain: EVMConfig):
    _logger = ChainLoggerAdapter(logger, chain.chain_symbol)

    while True:
        try:
            w3 = get_evm_async_client(chain, _logger).client
            account = w3.eth.account.from_key(EVM_WITHDRAWER_PRIVATE_KEY)

            dkg_party = dkg_key["party"]
            withdraws_requests = await find_withdraws_by_status(chain, WithdrawStatus.PENDING)

            if len(withdraws_requests) == 0:
                _logger.debug(f"No {WithdrawStatus.PENDING.value} has been found to process ...")
                continue
            for withdraw_request in withdraws_requests:
                if not isinstance(withdraw_request, EVMWithdrawRequest):
                    continue
                try:
                    await process_withdraw_sa(
                        w3=w3,
                        account=account,
                        chain=chain,
                        withdraw_request=withdraw_request,
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
