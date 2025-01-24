import os
from decimal import Decimal

from web3 import Web3

from zexporta.config import (
    CHAINS_CONFIG,
    USER_DEPOSIT_BYTECODE_HASH,
    USER_DEPOSIT_FACTORY_ADDRESS,
    ChainSymbol,
)

from .custom_types import MonitoringToken

LOGGER_PATH = "/var/log/monitoring_bot/"

TEST_USER_ID = int(os.environ["MONITORING_BOT_ZEX_USER_ID"])

WITHDRAWER_PRIVATE_KEY = os.environ["MONITORING_BOT_WITHDRAWER_PRIVATE_KEY"]

MONITORING_TOKENS = [
    MonitoringToken(
        symbol="zUSDT",
        chain_symbol=ChainSymbol.SEP,
        amount=10_000,
        address=Web3.to_checksum_address("0x325CCd77e71Ac296892ed5C63bA428700ec0f868"),
        decimal=6,
    ),
    MonitoringToken(
        symbol="zUSDT",
        chain_symbol=ChainSymbol.BST,
        amount=10_000,
        address=Web3.to_checksum_address("0x325CCd77e71Ac296892ed5C63bA428700ec0f868"),
        decimal=6,
    ),
    MonitoringToken(
        symbol="zUSDT",
        chain_symbol=ChainSymbol.HOL,
        amount=10_000,
        address=Web3.to_checksum_address("0x325CCd77e71Ac296892ed5C63bA428700ec0f868"),
        decimal=6,
    ),
]

DELAY = 60 * 60

TELEGRAM_BASE_URL = "https://api.telegram.org"
TELEGRAM_BOT_INFO = os.environ["TELEGRAM_BOT_INFO"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TELEGRAM_THREAD_ID = os.environ["TELEGRAM_THREAD_ID"]
