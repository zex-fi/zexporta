import logging
import os
from functools import lru_cache
from typing import override

from bitcoinutils.keys import P2trAddress, PublicKey
from bitcoinutils.script import Script
from bitcoinutils.utils import (
    b_to_i,
    get_tag_hashed_merkle_root,
    tagged_hash,
    tweak_taproot_pubkey,
)

from clients.abstract import ChainAsyncClient
from clients.custom_types import BlockNumber, TxHash

from .custom_types import Address, BTCConfig, BTCTransfer
from .rpc.ankr import BTCAnkrAsyncClient, Transaction


class BTCAsyncClient(ChainAsyncClient[BTCConfig, BTCAnkrAsyncClient, BTCTransfer, Address]):
    @override
    def __init__(self, chain: BTCConfig, logger: logging.Logger | logging.LoggerAdapter):
        super().__init__(chain, logger)
        self.btc = None

    @property
    @override
    def client(self) -> BTCAnkrAsyncClient:
        if self.btc is not None:
            return self.btc
        self.btc = BTCAnkrAsyncClient(base_url=self.chain.private_rpc, indexer_url=self.chain.private_indexer_rpc)
        return self.btc

    @override
    async def get_transfer_by_tx_hash(self, tx_hash: TxHash) -> list[BTCTransfer]:
        tx = await self.client.get_tx_by_hash(tx_hash)
        return self._parse_transfer(tx)

    @override
    async def get_finalized_block_number(self) -> BlockNumber:
        finalize_block_count = self.chain.finalize_block_count or 0
        finalized_block_number = (await self.get_latest_block_number()) - finalize_block_count
        return finalized_block_number

    @override
    async def get_token_decimals(self, token_address: Address) -> int:
        return 8

    @override
    async def is_transaction_successful(self, tx_hash: TxHash) -> bool:
        if await self.client.get_tx_by_hash(tx_hash):
            return True
        return False

    @override
    async def get_block_tx_hash(self, block_number: BlockNumber, **kwargs) -> list[TxHash]:
        block = await self.client.get_block_by_identifier(block_number)
        return [tx.txid for tx in block.txs]  # type: ignore

    @override
    async def get_latest_block_number(self) -> BlockNumber:
        return await self.client.get_latest_block_number()

    @override
    async def extract_transfer_from_block(
        self,
        block_number: BlockNumber,
        **kwargs,
    ) -> list[BTCTransfer]:
        self.logger.debug(f"Observing block number {block_number} start")
        block = await self.client.get_block_by_identifier(block_number)
        result = []
        for tx in block.txs:  # type: ignore
            # TODO: The time complexity is O(n^2); we should improve it.
            # Be careful, as this function is CPU-bound.
            # so if concurrency is the answer, we should use multi-processing.
            transfer = self._parse_transfer(tx)
            if transfer:
                result.extend(transfer)
        self.logger.debug(f"Observing block number {block_number} end")
        return result

    def _parse_transfer(self, tx: Transaction) -> list[BTCTransfer]:
        transfers = []
        for output in tx.vout:
            if output.isAddress:
                transfers.append(
                    BTCTransfer(
                        tx_hash=tx.txid,
                        block_number=tx.blockHeight,
                        chain_symbol=self.chain.chain_symbol,
                        to=output.addresses[0],  # type: ignore
                        value=output.value,
                        token="0x0000000000000000000000000000000000000000",
                        index=output.n,
                    )
                )
        return transfers


@lru_cache
def get_btc_async_client(chain: BTCConfig, logger: logging.Logger | logging.LoggerAdapter) -> BTCAsyncClient:
    client = BTCAsyncClient(chain, logger)
    return client


def calculate_tweak(pubkey: PublicKey, scripts: None | Script | list[Script] | list[list[Script]] | bytes) -> int:
    key_x = pubkey.to_bytes()[:32]

    if not scripts:
        tweak = tagged_hash(key_x, "TapTweak")
    elif isinstance(scripts, bytes):
        tweak = tagged_hash(key_x + scripts, "TapTweak")
    else:
        merkle_root = get_tag_hashed_merkle_root(scripts)
        tweak = tagged_hash(key_x + merkle_root, "TapTweak")

    tweak_int = b_to_i(tweak)

    return tweak_int


def compute_btc_address(salt: int) -> Address:
    master_pub = PublicKey.from_hex(os.environ["BTC_GROUP_KEY_PUB"])  # hex str
    tweak_int = calculate_tweak(master_pub, salt.to_bytes(8, byteorder="big"))

    # keep x-only coordinate
    tweak_and_odd = tweak_taproot_pubkey(master_pub.key.to_string(), tweak_int)
    pubkey = tweak_and_odd[0][:32]
    is_odd = tweak_and_odd[1]

    pubkey_and_is_odd = pubkey.hex(), is_odd

    pubkey = pubkey_and_is_odd[0]
    is_odd = pubkey_and_is_odd[1]

    return P2trAddress(witness_program=pubkey, is_odd=is_odd).to_string()
