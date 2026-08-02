"""Ponto de entrada da aplicacao.

Desenvolvimento:
    python main.py

Producao (VPS / Docker):
    gunicorn --bind 0.0.0.0:5000 --workers 1 -k uvicorn.workers.UvicornWorker main:app
"""

import uvicorn

from src import create_app
from src.config import settings

app = create_app()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=settings.is_debug)
