from fastapi import FastAPI

from .router import router

v1 = FastAPI(name="Zexporta", version="1")
v1.include_router(router=router)
