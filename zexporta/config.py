import os

from bitcoinutils.setup import setup
from web3 import Web3

from .custom_types import (
    BTCConfig,
    BTCWithdrawRequest,
    ChainConfig,
    ChainId,
    ChainSymbol,
    EnvEnum,
    EVMConfig,
    EVMWithdrawRequest,
)
from .db.utxo import populate_deposits_utxos

ENVIRONMENT = EnvEnum(os.environ["ENV"])

if ENVIRONMENT == EnvEnum.PROD:
    ZEX_BASE_URL = "https://api.zex.finance/v1"

    CHAINS_CONFIG: dict[str, ChainConfig] = {
        ChainSymbol.HOL.value: EVMConfig(
            private_rpc=os.environ["HOL_RPC"],
            native_decimal=18,
            chain_symbol=ChainSymbol.HOL.value,
            finalize_block_count=1,
            delay=1,
            batch_block_size=20,
            vault_address=Web3.to_checksum_address("0x72E46E170342E4879b0Ea8126389111D4275173D"),
            chain_id=ChainId(17000),
        ),
        ChainSymbol.SEP.value: EVMConfig(
            private_rpc=os.environ["SEP_RPC"],
            native_decimal=18,
            chain_symbol=ChainSymbol.SEP.value,
            finalize_block_count=1,
            delay=1,
            batch_block_size=20,
            vault_address=Web3.to_checksum_address("0x72E46E170342E4879b0Ea8126389111D4275173D"),
            chain_id=ChainId(11155111),
        ),
        # ChainSymbol.BST.value: EVMConfig(
        #     private_rpc=os.environ["BST_RPC"],
        #     native_decimal=18,
        #     chain_symbol=ChainSymbol.BST.value,
        #     finalize_block_count=1,
        #     poa=True,
        #     delay=1,
        #     batch_block_size=30,
        #     vault_address=Web3.to_checksum_address("0x72E46E170342E4879b0Ea8126389111D4275173D"),
        #     chain_id=ChainId(97),
        # ),
        ChainSymbol.BTC.value: BTCConfig(
            private_rpc=os.environ["BTC_RPC"],
            private_indexer_rpc=os.environ["BTC_INDEXER"],
            chain_symbol=ChainSymbol.BTC.value,
            finalize_block_count=1,
            delay=10,
            batch_block_size=5,
            vault_address="",
            deposit_finalizer_middleware=(populate_deposits_utxos,),
        ),
    }
    setup("testnet")


else:
    ZEX_BASE_URL = "https://api-dev.zex.finance/v1"

    CHAINS_CONFIG: dict[str, ChainConfig] = {
        ChainSymbol.HOL.value: EVMConfig(
            private_rpc=os.environ["HOL_RPC"],
            native_decimal=18,
            chain_symbol=ChainSymbol.HOL.value,
            finalize_block_count=1,
            delay=1,
            batch_block_size=20,
            vault_address=Web3.to_checksum_address("0x17a8bC4724666738387Ef5Fc59F7EF835AF60979"),
            chain_id=ChainId(17000),
        ),
        ChainSymbol.SEP.value: EVMConfig(
            private_rpc=os.environ["SEP_RPC"],
            native_decimal=18,
            chain_symbol=ChainSymbol.SEP.value,
            finalize_block_count=1,
            delay=1,
            batch_block_size=20,
            vault_address=Web3.to_checksum_address("0x17a8bC4724666738387Ef5Fc59F7EF835AF60979"),
            chain_id=ChainId(11155111),
        ),
        # ChainSymbol.BST.value: EVMConfig(
        #     private_rpc=os.environ["BST_RPC"],
        #     native_decimal=18,
        #     chain_symbol=ChainSymbol.BST.value,
        #     finalize_block_count=1,
        #     poa=True,
        #     delay=1,
        #     batch_block_size=30,
        #     vault_address=Web3.to_checksum_address("0x17a8bC4724666738387Ef5Fc59F7EF835AF60979"),
        #     chain_id=ChainId(97),
        # ),
        # ChainSymbol.BTC.value: BTCConfig(
        #     private_rpc=os.environ["BTC_RPC"],
        #     private_indexer_rpc=os.environ["BTC_INDEXER"],
        #     chain_symbol=ChainSymbol.BTC.value,
        #     finalize_block_count=1,
        #     delay=60,
        #     batch_block_size=5,
        #     vault_address="",
        #     deposit_finalizer_middleware=(populate_deposits_utxos,),
        # ),
    }
    # setup("testnet")


EVM_NATIVE_TOKEN_ADDRESS = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")

ZEX_ENCODE_VERSION = 1

BTC_GROUP_KEY_PUB = os.getenv("BTC_GROUP_KEY_PUB")

USER_DEPOSIT_FACTORY_ADDRESS = os.environ["USER_DEPOSIT_FACTORY_ADDRESS"]
USER_DEPOSIT_BYTECODE_HASH = os.environ["USER_DEPOSIT_BYTECODE_HASH"]

SA_SHIELD_PRIVATE_KEY = os.environ["SA_SHIELD_PRIVATE_KEY"]

DKG_JSON_PATH = os.getenv("DKG_JSON_PATH", "./zexporta/dkgs/dkgs.json")
DKG_NAME = os.getenv("DKG_NAME", "ethereum")

EVM_WITHDRAWER_PRIVATE_KEY = os.environ["EVM_WITHDRAWER_PRIVATE_KEY"]
EVM_VAULT_DEPOSITOR_PRIVATE_KEY = os.environ["EVM_VAULT_DEPOSITOR_PRIVATE_KEY"]

SENTRY_DNS = os.getenv("SENTRY_DNS")

MONGO_HOST = os.getenv("MONGO_HOST")
MONGO_PORT = os.getenv("MONGO_PORT")
MONGO_DBNAME = os.environ.get("MONGO_DBNAME", "transaction_database")
