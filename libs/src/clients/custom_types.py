from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Annotated, Any, Awaitable, Callable, Hashable

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

type TxHash = str
type BlockNumber = int
type URL = str
type Salt = int
type Address = Any


def convert_int_to_str(value: int) -> str:
    return str(value)


type Value = Annotated[int, PlainSerializer(convert_int_to_str, when_used="json")]


class Transfer[_AddressT](BaseModel, ABC):
    model_config = ConfigDict(from_attributes=True)
    tx_hash: TxHash
    value: Value
    chain_symbol: str
    token: _AddressT
    to: _AddressT
    block_number: BlockNumber

    @abstractmethod
    def __eq__(self, value: Any) -> bool: ...

    @abstractmethod
    def __gt__(self, value: Any) -> bool: ...


class WithdrawStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESSFUL = "successful"
    REJECTED = "rejected"


class WithdrawRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    amount: Value
    recipient: Address
    tx_hash: TxHash | None = None
    status: WithdrawStatus = WithdrawStatus.PENDING
    chain_symbol: str
    nonce: int
    user_id: int  # FIXME: this should move to another class that will be in zexporta


class ChainConfig[_TransferT: Transfer, _WithdrawT: WithdrawRequest](BaseModel, Hashable, ABC):
    model_config = ConfigDict(frozen=True)

    vault_address: Address
    private_rpc: URL
    chain_symbol: str
    finalize_block_count: int | None = Field(default=15)
    delay: int | float = Field(default=3)
    batch_block_size: int = Field(default=5)
    transfer_class: type[_TransferT]
    withdraw_request_type: type[_WithdrawT]
    deposit_finalizer_middleware: tuple[Callable[..., Awaitable[Any]], ...] | None = None  # Supports async functions
