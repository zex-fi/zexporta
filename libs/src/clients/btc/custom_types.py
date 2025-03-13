# Model for Address Details
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel

from clients.custom_types import URL, ChainConfig, Salt, Transfer, TxHash, Value, WithdrawRequest

type Address = str


class BTCTransfer(Transfer):
    to: Address
    index: int

    def __eq__(self, value: Any) -> bool:
        if isinstance(value, BTCTransfer):
            return self.tx_hash == value.tx_hash and self.index == value.index
        return NotImplemented

    def __gt__(self, value: Any) -> bool:
        if isinstance(value, BTCTransfer):
            return self.tx_hash > value.tx_hash or (self.tx_hash == value.tx_hash and self.index > value.index)
        return NotImplemented


class UTXOStatus(StrEnum):
    UNSPENT = "unspent"
    SPEND = "spend"


class UTXO(BaseModel):
    status: UTXOStatus = UTXOStatus.UNSPENT
    tx_hash: TxHash
    amount: Value
    index: Value
    address: Address
    salt: Salt


class BTCWithdrawRequest(WithdrawRequest):
    utxos: list[UTXO]
    zellular_index: str
    sat_per_byte: int


class BTCConfig(ChainConfig):
    private_indexer_rpc: URL
    transfer_class: ClassVar[type[BTCTransfer]] = BTCTransfer
    withdraw_request_type: ClassVar[type[BTCWithdrawRequest]] = BTCWithdrawRequest


__all__ = ["BTCWithdrawRequest", "UTXO", "UTXOStatus", "BTCConfig", "BTCTransfer"]
