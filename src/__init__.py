"""Factory da aplicacao FastAPI."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import settings

__version__ = "0.1.0"


def _configurar_logs() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from src.db.pool import close_pool, open_pool
    from src.db.schema import ensure_schema

    pool = open_pool()
    with pool.connection() as conn:
        ensure_schema(conn)

    yield

    close_pool()


def create_app() -> FastAPI:
    """Cria e configura a instancia do FastAPI."""
    _configurar_logs()
    logger = logging.getLogger(__name__)

    app = FastAPI(title="Blackbass Bot", version=__version__, lifespan=_lifespan)

    from src.routes import webhook_router
    app.include_router(webhook_router)

    pendentes = settings.missing_required()
    if pendentes:
        logger.warning(
            "Variaveis de ambiente nao configuradas: %s. "
            "Copie o .env.example para .env e preencha.",
            ", ".join(pendentes),
        )

    logger.info("App iniciado (env=%s)", settings.APP_ENV)
    return app
