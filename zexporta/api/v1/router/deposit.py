from clients import get_compute_address_function
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from zexporta.config import CHAINS_CONFIG
from zexporta.custom_types import ChainSymbol, DepositStatus, UserId
from zexporta.db.deposit import find_address_deposits

deposit_router = APIRouter(tags=["Deposits"], prefix="/deposits")


@deposit_router.get("/{user_id}/{chain_symbol}")
async def get_finalized_tx(
    user_id: UserId,
    chain_symbol: ChainSymbol,
    status: DepositStatus | None = None,
) -> JSONResponse:
    chain = CHAINS_CONFIG[chain_symbol.value]
    address = get_compute_address_function(chain)(user_id)
    deposits = await find_address_deposits(chain, address, status)
    return JSONResponse(content=[deposit.model_dump(mode="json") for deposit in deposits])
