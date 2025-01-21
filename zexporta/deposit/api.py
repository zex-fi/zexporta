from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from zexporta.custom_types import ChainSymbol, DepositStatus
from zexporta.db.deposit import find_deposit_by_status

app = FastAPI(name="ZexDeposit", version="1")

route = APIRouter(tags=["Deposits"], prefix="/deposits")


@route.get("/finalized/<chain_symbol:str>")
async def get_finalized_tx(
    chain_symbol: ChainSymbol,
    from_block: Annotated[int, Query(default=0)],
    status: Annotated[DepositStatus, Query(default=DepositStatus.FINALIZED)],
) -> JSONResponse:
    deposits = await find_deposit_by_status(
        status, chain_symbol=ChainSymbol(chain_symbol), from_block=from_block
    )
    return JSONResponse(
        content=[deposit.model_dump(mode="json") for deposit in deposits]
    )


app.include_router(route)
