import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from clients.abstract import ChainAsyncClient
from pymongo import AsyncMongoClient
from testcontainers.mongodb import MongoDbContainer

from zexporta.utils.logger import ChainLoggerAdapter

from .mock import MockChainConfig


@pytest.fixture(autouse=True, scope="session")
def setup_mongo():
    mongo_port = int(os.getenv("MONGO_PORT", "27017"))
    with MongoDbContainer("mongo:7.0.15", port=mongo_port) as mongo_container:
        with patch("pymongo.AsyncMongoClient") as client:
            client.return_value = AsyncMongoClient(mongo_container.get_connection_url())
            yield client


@pytest.fixture(autouse=True, scope="function")
async def drop_mongo(setup_mongo):
    db_connection = setup_mongo()
    try:
        yield
    finally:
        await db_connection.drop_database(os.getenv("MONGO_DBNAME", "transaction_database"))


@pytest.fixture(autouse=True, scope="session")
def disable_asyncio_sleep():
    with patch("asyncio.sleep", new=AsyncMock(spec=asyncio.sleep)):
        yield


@pytest.fixture
def mock_chain_config():
    yield MockChainConfig(private_rpc="http://example.com", chain_symbol="ETH", vault_address="")


@pytest.fixture
def mock_client(mock_chain_config):
    client = AsyncMock(spec=ChainAsyncClient)
    client.chain = mock_chain_config
    yield client


@pytest.fixture
def mock_logger():
    yield MagicMock(spec=ChainLoggerAdapter)
