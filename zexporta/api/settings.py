from fastapi import FastAPI

from .v1 import v1 as v1_app


def create_app():
    app = FastAPI(name="Zexporta")
    app.mount("/api/v1", v1_app)
    return app
