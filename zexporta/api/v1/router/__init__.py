from fastapi import APIRouter

from .deposit import deposit_router
from .healthcheck import health_check_router
from .withdraw import withdraw_router

router = APIRouter()
router.include_router(router=deposit_router)
router.include_router(router=withdraw_router)
router.include_router(router=health_check_router)
