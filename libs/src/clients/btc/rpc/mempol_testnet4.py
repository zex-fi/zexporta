from typing import Any

import httpx

from clients.btc.exceptions import (
    BTCClientError,
    BTCConnectionError,
    BTCRequestError,
    BTCResponseError,
    BTCTimeoutError,
)
from clients.btc.rpc.data_models import (
    AddressDetails,
    Block,
    Transaction,
    Vin,
    Vout,
)
from clients.custom_types import BlockNumber


class BTCMempoolAsyncClient:
    def __init__(self, base_url: str = "https://mempool.space/testnet4/api", timeout: int = 15):
        self.base_url = base_url
        self._client = httpx.AsyncClient()
        self.time_out = timeout

    @property
    def client(self):
        if self._client.is_closed:
            self._client = httpx.AsyncClient()
        return self._client

    async def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        data: Any = None,
    ) -> dict[str, Any] | str:
        try:
            response = await self.client.request(method, url, params=params, json=data, timeout=self.time_out)
            response.raise_for_status()
            if response.headers.get("content-type") == "application/json":
                data = response.json()
            else:
                data = response.text
            return data
        except httpx.HTTPStatusError as http_err:
            raise BTCRequestError(
                f"HTTP error occurred: {http_err.response.status_code} {http_err.response.reason_phrase}"
            ) from http_err
        except httpx.ConnectError as conn_err:
            raise BTCConnectionError(f"Connection error occurred: {conn_err}") from conn_err
        except httpx.TimeoutException as timeout_err:
            raise BTCTimeoutError(f"Request timed out: {timeout_err}") from timeout_err
        except httpx.RequestError as req_err:
            raise BTCClientError(f"An error occurred while requesting {req_err.request.url!r}.") from req_err
        except ValueError as json_err:
            raise BTCResponseError(f"Failed to parse JSON response: {json_err}") from json_err

    async def get_tx_by_hash(self, txid: str) -> Transaction:
        url = f"{self.base_url}/tx/{txid}"
        data = await self._request("GET", url)
        return self.populate_transaction(data)  # type: ignore

    async def get_block_by_id(self, block_id: str) -> Block:
        url = f"{self.base_url}/block/{block_id}"
        block: dict = await self._request("GET", url)  # type: ignore
        txs = []
        slice = 25
        for i in range(0, int(block["tx_count"] // slice) + 1):
            url = f"{self.base_url}/block/{block_id}/txs/{i * slice}"
            data = await self._request("GET", url)
            txs.append(data)
        block["txs"] = txs
        return self.populate_block(block)

    async def get_block_by_number(self, number: int) -> Block:
        url = f"{self.base_url}/block-height/{number}"
        block_hash = await self._request("GET", url)
        return await self.get_block_by_id(block_hash)  # type: ignore

    async def get_block_by_identifier(self, identifier: str | int) -> Block:
        if str(identifier).isdigit():
            data = await self.get_block_by_number(int(identifier))
        else:
            data = await self.get_block_by_id(str(identifier))
        return data

    async def get_latest_block_number(self) -> BlockNumber | None:
        url = f"{self.base_url}/blocks/tip/height"
        data = await self._request("GET", url)
        return data and int(data)  # type: ignore

    async def get_latest_block_hash(self) -> str:
        url = f"{self.base_url}/blocks/tip/hash"
        block_hash = await self._request("GET", url)
        return block_hash  # type: ignore

    async def get_latest_block(self) -> Block:
        block_hash = await self.get_latest_block_hash()
        return await self.get_block_by_id(block_hash)

    async def get_address_details(self, address: str) -> AddressDetails:
        url = f"{self.base_url}/address/{address}"
        data = await self._request("GET", url)
        return self.populate_address(data)  # type: ignore

    async def send_tx(self, raw_tx: str) -> str:
        url = f"{self.base_url}/tx"
        data = await self._request("POST", url, data=raw_tx)
        return data  # type: ignore

    async def get_fee_estimates(self) -> int | None:
        url = f"{self.base_url}/v1/fees/recommended"
        data = await self._request("GET", url)
        return data and isinstance(data, dict) and data.get("fastestFee")  # type: ignore

    async def close(self):
        await self.client.aclose()

    def populate_address(self, data: dict) -> AddressDetails:
        totalReceived = data.get("chain_stats", {}).get("funded_txo_sum", 0)
        totalSent = data.get("chain_stats", {}).get("spent_txo_sum", 0)
        return AddressDetails(
            address=data["address"],
            balance=totalReceived - totalSent,
            totalReceived=totalReceived,
            totalSent=totalSent,
        )

    def populate_transaction(self, tx: dict) -> Transaction:
        vin_list = [
            Vin(
                sequence=vin["sequence"],
                n=i,
                coinbase=vin.get("is_coinbase", False),
                value=vin.get("vout", 0),
            )
            for i, vin in enumerate(tx["vin"])
        ]
        vout_list: list[Vout] = [
            Vout(
                value=vout.get("value", 0),
                n=i,
                addresses=[vout.get("scriptpubkey_address", "")],
                isAddress=True if vout.get("scriptpubkey_address", False) else False,
            )
            for i, vout in enumerate(tx["vout"])
        ]

        value = sum(v.value for v in vout_list)
        valueIn = sum(v.value for v in vin_list)  # type: ignore

        return Transaction(
            txid=tx["txid"],
            vin=vin_list,
            vout=vout_list,
            blockHash=tx["status"].get("block_hash"),
            blockHeight=tx["status"].get("block_height"),
            confirmations=0,  # todo
            blockTime=tx["status"].get("block_time"),
            value=value,
            valueIn=valueIn,
            fees=tx.get("fee", 0),
        )

    def populate_block(self, data: dict) -> Block:
        txs = []
        for tx in data["txs"][0]:
            txs.append(self.populate_transaction(tx))

        return Block(
            hash=data["id"],
            previousBlockHash=data["previousblockhash"],
            height=data["height"],
            confirmations=0,  # todo
            size=data["size"],
            time=data["timestamp"],
            version=data["version"],
            merkleRoot=data["merkle_root"],
            nonce=str(data["nonce"]),
            difficulty=str(data["difficulty"]),
            bits=str(data["bits"]),
            txCount=data["tx_count"],
            txs=txs,
        )
