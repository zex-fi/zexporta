from decimal import Decimal
from typing import Any, Callable, Coroutine

from clients import ChainAsyncClient, filter_blocks

from zexporta.custom_types import (
    Address,
    BlockNumber,
    Deposit,
    DepositStatus,
    Timestamp,
    Transfer,
    UserId,
)
from zexporta.db.token import get_decimals, insert_token


def get_block_batches(
    from_block: BlockNumber,
    to_block: BlockNumber,
    *,
    batch_size: int = 5,
) -> list[tuple[BlockNumber, ...]]:
    block_batches = [
        tuple(j for j in range(i, min(to_block + 1, i + batch_size)))
        for i in range(from_block, to_block + 1, batch_size)
    ]
    return block_batches


async def explorer(
    client: ChainAsyncClient,
    from_block: BlockNumber,
    to_block: BlockNumber,
    accepted_addresses: dict[Address, UserId],
    extract_block_logic: Callable[..., Coroutine[Any, Any, list[Transfer]]],
    *,
    batch_size=5,
    max_delay_per_block_batch: int | float = 10,
    **kwargs,
) -> list[Deposit[Transfer]]:
    result = []
    block_batches = get_block_batches(from_block, to_block, batch_size=batch_size)
    for blocks_number in block_batches:
        transfers = await filter_blocks(
            blocks_number,
            extract_block_logic,
            max_delay_per_block_batch=max_delay_per_block_batch,
            **kwargs,
        )
        accepted_deposits = await get_accepted_deposits(
            client,
            transfers,
            accepted_addresses=accepted_addresses,
        )
        result.extend(accepted_deposits)
    return result


async def get_token_decimals(client: ChainAsyncClient, token_address: Address) -> int:
    chain_symbol = client.chain.chain_symbol
    decimals = await get_decimals(chain_symbol, token_address)
    if decimals is None:
        decimals = await client.get_token_decimals(token_address)
        await insert_token(chain_symbol, token_address, decimals)
    return decimals


async def get_accepted_deposits(
    client: ChainAsyncClient,
    transfers: list[Transfer],
    accepted_addresses: dict[Address, UserId],
    *,
    sa_timestamp: Timestamp | None = None,
    deposit_status: DepositStatus = DepositStatus.PENDING,
) -> list[Deposit]:
    result = []
    for transfer in transfers:
        if (user_id := accepted_addresses.get(transfer.to)) is not None:
            decimals = await get_token_decimals(client, transfer.token)
            if await client.is_transaction_successful(transfer.tx_hash):
                deposit = Deposit(
                    user_id=user_id,
                    decimals=decimals,
                    transfer=client.chain.transfer_class.model_validate(transfer),
                    status=deposit_status,
                    sa_timestamp=sa_timestamp,
                )
                if (
                    transfer.token != "0x0000000000000000000000000000000000000000"
                    and Decimal(deposit.transfer.value) / 10**decimals > 300
                ):  # FIXME: this is just for test becareful and remove it
                    deposit.status = DepositStatus.REJECTED
                result.append(deposit)

    return result
