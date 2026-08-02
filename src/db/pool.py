"""Pool de conexoes com o Postgres, compartilhado pela aplicacao inteira.

Aberto no startup do FastAPI (ver `src/__init__.py`) e fechado no shutdown.
Como o app roda com 1 worker so (ver Dockerfile), um pool por processo e
suficiente - sem preocupacao de multiplos processos disputando conexoes.
"""

import logging

from psycopg_pool import ConnectionPool

from src.config import settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def open_pool() -> ConnectionPool:
    """Abre o pool (idempotente - chamadas repetidas devolvem o mesmo pool)."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.DATABASE_URL, min_size=1, max_size=5, open=True)
        logger.info("Pool de conexoes com o Postgres aberto.")
    return _pool


def get_pool() -> ConnectionPool:
    """Devolve o pool ja aberto. Levanta erro se `open_pool()` ainda nao rodou."""
    if _pool is None:
        raise RuntimeError("Pool de conexoes ainda nao foi aberto (open_pool() nao foi chamado).")
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
        logger.info("Pool de conexoes com o Postgres fechado.")
