"""Composition root for the API: wires settings and adapters into the use cases.

uvicorn --factory rarest_blue.entrypoints.http.app:create_app
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ...application.gameplay import GameService
from ...application.ports import Clock, UnitOfWorkFactory
from ...config import Settings
from ...domain import days
from ...infrastructure import postgres
from .routes import dev_router, router


def create_app(
    settings: Settings | None = None, uow: UnitOfWorkFactory | None = None, clock: Clock = days.today
) -> FastAPI:
    settings = settings or Settings.from_env()
    pools = []  # filled at startup; requests borrow warm connections instead of reconnecting

    def pooled_uow():
        return postgres.PostgresUnitOfWork(pool=pools[0])

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        postgres.init_schema(settings.database_url)
        if uow is None:
            pools.append(postgres.open_pool(settings.database_url))
        try:
            yield
        finally:
            for pool in pools:
                pool.close()
            pools.clear()

    app = FastAPI(title="UofT Krillion", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.game = GameService(uow or pooled_uow, clock)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router)
    if settings.dev_reset:
        app.include_router(dev_router)
    return app
