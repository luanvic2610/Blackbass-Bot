"""Ponto de entrada da aplicacao.

Desenvolvimento:
    python main.py

Producao (VPS / Docker):
    gunicorn --bind 0.0.0.0:5000 --workers 2 main:app
"""

from src import create_app
from src.config import settings

app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=settings.PORT, debug=settings.is_debug)
