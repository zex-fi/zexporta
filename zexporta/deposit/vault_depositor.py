import asyncio
import logging
import logging.config
from enum import StrEnum

import sentry_sdk
from clients.evm import get_evm_async_client
from eth_account.signers.local import LocalAccount
from hexbytes import HexBytes
from web3 import AsyncWeb3
from web3.types import Nonce, TxReceipt

from zexporta.custom_types import (
    ChecksumAddress,
    Deposit,
    DepositStatus,
    EVMConfig,
)
from zexporta.db.deposit import find_deposit_by_status, upsert_deposits
from zexporta.utils.abi import FACTORY_ABI, USER_DEPOSIT_ABI
from zexporta.utils.logger import ChainLoggerAdapter, get_logger_config

from .config import (
    CHAINS_CONFIG,
    EVM_NATIVE_TOKEN_ADDRESS,
    EVM_VAULT_DEPOSITOR_PRIVATE_KEY,
    LOGGER_PATH,
    SENTRY_DNS,
    USER_DEPOSIT_FACTORY_ADDRESS,
    WITHDRAW_BATCH_SIZE,
)

logging.config.dictConfig(get_logger_config(f"{LOGGER_PATH}/vault_depositor.log"))
logger = logging.getLogger(__name__)


class TxType(StrEnum):
    CONTRACT_DEPLOY = "contract_deploy"
    TOKEN_TRANSFER = "token_transfer"


async def deploy_contract(
    w3: AsyncWeb3,
    account: LocalAccount,
    factory_address: ChecksumAddress,
    salt: int,
    nonce: Nonce,
    logger: logging.Logger | ChainLoggerAdapter = logger,
) -> tuple[HexBytes, TxType]:
    factory_contract = w3.eth.contract(address=factory_address, abi=FACTORY_ABI)
    deploy_tx = await factory_contract.functions.deploy(salt).build_transaction(
        {"from": account.address, "nonce": nonce, "gas": 1_560_000}
    )

    signed_tx = account.sign_transaction(deploy_tx)
    tx_hash = await w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    logger.info(f"deploy contract tx broadcasts for salt: {salt} and with tx_hash: {tx_hash.hex()}")
    return tx_hash, TxType.CONTRACT_DEPLOY


async def transfer_token(
    w3: AsyncWeb3,
    account: LocalAccount,
    deposit: Deposit,
    nonce: Nonce,
    logger: logging.Logger | ChainLoggerAdapter = logger,
) -> tuple[HexBytes, TxType]:
    user_deposit = w3.eth.contract(address=deposit.transfer.to, abi=USER_DEPOSIT_ABI)  # type: ignore
    if deposit.transfer.token == EVM_NATIVE_TOKEN_ADDRESS:
        tx = await user_deposit.functions.transferNativeToken(deposit.transfer.value).build_transaction(
            {"from": account.address, "nonce": nonce, "gas": 55_000}
        )
    else:
        tx = await user_deposit.functions.transferERC20(
            deposit.transfer.token, deposit.transfer.value
        ).build_transaction({"from": account.address, "nonce": nonce, "gas": 65_000})
    signed_tx = account.sign_transaction(tx)
    tx_hash = await w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    logger.info(f"Transfer token for address: {deposit.transfer.to} and tx_hash: {tx_hash.hex()}")
    return tx_hash, TxType.TOKEN_TRANSFER


async def broadcast_transactions(
    w3: AsyncWeb3, account: LocalAccount, deposits: list[Deposit], nonce: Nonce, logger: ChainLoggerAdapter
) -> list[tuple[HexBytes, TxType]]:
    tasks = []
    for deposit in deposits:
        is_contract = (await w3.eth.get_code(deposit.transfer.to)) != b""  # type: ignore
        if not is_contract:
            logger.info(f"Contract: {deposit.transfer.to} not found! Deploying a new one ...")
            tasks.append(
                asyncio.create_task(
                    deploy_contract(
                        w3,
                        account,
                        w3.to_checksum_address(USER_DEPOSIT_FACTORY_ADDRESS),
                        deposit.user_id,
                        nonce=nonce,
                        logger=logger,
                    )
                )
            )
            nonce += 1  # type: ignore
        else:
            tasks.append(transfer_token(w3, account, deposit, nonce=nonce, logger=logger))
            nonce += 1  # type: ignore
    tx_hashes = await asyncio.gather(*tasks)
    return tx_hashes


async def check_transactions_receipt(
    w3: AsyncWeb3, txs_hash: list[tuple[HexBytes, TxType]]
) -> list[tuple[TxReceipt | BaseException, TxType]]:
    tasks = [asyncio.create_task(w3.eth.wait_for_transaction_receipt(tx_hash[0])) for tx_hash in txs_hash]
    _tx_receipts = await asyncio.gather(*tasks, return_exceptions=True)
    tx_receipts = list(zip(_tx_receipts, [tx_hash[1] for tx_hash in txs_hash]))
    return tx_receipts


async def withdraw(chain: EVMConfig):
    _logger = ChainLoggerAdapter(logger, chain.chain_symbol)

    while True:
        w3 = get_evm_async_client(chain, _logger).client
        account = w3.eth.account.from_key(EVM_VAULT_DEPOSITOR_PRIVATE_KEY)
        nonce = await w3.eth.get_transaction_count(account.address, "pending")
        try:
            deposits = await find_deposit_by_status(chain, status=DepositStatus.VERIFIED, limit=WITHDRAW_BATCH_SIZE)
            if len(deposits) == 0:
                _logger.debug("New deposit is not found.")
                await asyncio.sleep(10)
                continue
            logger.info(f"Deposit length is {len(deposits)}")
            txs_hash = await broadcast_transactions(w3, account, deposits, nonce, _logger)
            txs_receipt = await check_transactions_receipt(w3, txs_hash)
            for index, (tx_receipt, tx_type) in enumerate(txs_receipt):
                if isinstance(tx_receipt, BaseException):
                    _logger.error(f"Exception occurred, error: {tx_receipt}")
                    continue
                if tx_receipt["status"] != 1:
                    _logger.error(
                        f"Transaction for address {deposits[index].transfer.to} and \
                          TxHash {tx_receipt['transactionHash'].hex()} \
                          TxType {tx_type} is not successful."
                    )
                if tx_type == TxType.CONTRACT_DEPLOY:
                    continue
                deposits[index].status = DepositStatus.SUCCESSFUL
            await upsert_deposits(chain=chain, deposits=deposits)

        except Exception as e:
            _logger.error(f"Exception occurred, error: {e}")


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
