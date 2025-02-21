from typing import Dict, List

from fastapi import APIRouter, HTTPException, status

from .abstract import Checkable

__all__ = [
    "HealthController",
    "HealthCheck",
]


class HealthCheck:
    def __init__(self, *modules: Checkable):
        self.modules: List[Checkable] = list(modules)

    async def check_healthiness(self) -> bool:
        for module in self.modules:
            is_healthy = await module.is_healthy()
            if not is_healthy:
                return False
        return True


class HealthController:
    def __init__(self, svc: HealthCheck, router: APIRouter):
        self.svc = svc
        self.router = router

    def register_handlers(self) -> None:
        self.router.add_api_route("/_health", self.check_health, methods=["GET"])

    async def check_health(self) -> Dict[str, str]:
        is_healthy = await self.svc.check_healthiness()
        if not is_healthy:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"status": "failed"})
        return {"status": "ok"}
