from fastapi import APIRouter
from fastapi.responses import JSONResponse

from zexporta.config import CHAINS_CONFIG
from zexporta.custom_types import ChainSymbol, UserId, WithdrawStatus
from zexporta.db.withdraw import find_user_withdraws

withdraw_router = APIRouter(tags=["Withdraws"], prefix="/withdraws")


@withdraw_router.get("/{user_id}/{chain_symbol}")
async def get_user_withdraws(
    user_id: UserId,
    chain_symbol: ChainSymbol,
    status: WithdrawStatus | None = None,
) -> JSONResponse:
    chain = CHAINS_CONFIG[chain_symbol.value]
    withdraws = await find_user_withdraws(chain, user_id, status)
    return JSONResponse(content=[withdraw.model_dump(mode="json") for withdraw in withdraws])
