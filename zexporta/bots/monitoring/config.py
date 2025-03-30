import os

from web3 import Web3

from zexporta.bots.custom_types import BotToken
from zexporta.config import (
    CHAINS_CONFIG,
    USER_DEPOSIT_BYTECODE_HASH,
    USER_DEPOSIT_FACTORY_ADDRESS,
    ChainSymbol,
)

LOGGER_PATH = "/var/log/bot_monitoring/"

TEST_USER_ID = int(os.environ["MONITORING_BOT_ZEX_USER_ID"])

WITHDRAWER_PRIVATE_KEY = os.environ["MONITORING_BOT_WITHDRAWER_PRIVATE_KEY"]

MONITORING_TOKENS = [
    BotToken(
        symbol="zUSDT",
        chain_symbol=ChainSymbol.SEP,
        amount=10_000,
        address=Web3.to_checksum_address("0x6f8cbCf0b342f6a997874F8bf1430ADE5138e15a"),
        decimal=6,
    ),
    BotToken(
        symbol="zUSDT",
        chain_symbol=ChainSymbol.HOL,
        amount=10_000,
        address=Web3.to_checksum_address("0x6f8cbCf0b342f6a997874F8bf1430ADE5138e15a"),
        decimal=6,
    ),
]

DELAY = int(os.environ["BOT_DELAY_IN_HOUR"]) * 60 * 60

TELEGRAM_BASE_URL = "https://api.telegram.org"
TELEGRAM_BOT_INFO = os.environ["TELEGRAM_BOT_INFO"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TELEGRAM_THREAD_ID = os.environ["TELEGRAM_THREAD_ID"]
