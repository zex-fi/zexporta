# In future we should organize this instance creation
from fastapi import APIRouter
from health_check import HealthCheck, HealthController

health_check_router = APIRouter(tags=["HealthCheck"])
health_check_svc = HealthCheck()
health_check_ctrl = HealthController(health_check_svc, health_check_router)
health_check_router = health_check_ctrl.register_handlers()
