"""Factory da aplicacao Flask."""

import logging

from flask import Flask

from src.config import settings

__version__ = "0.1.0"


def _configurar_logs() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def create_app() -> Flask:
    """Cria e configura a instancia do Flask."""
    _configurar_logs()
    logger = logging.getLogger(__name__)

    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    from src.routes import webhook_bp
    app.register_blueprint(webhook_bp)

    pendentes = settings.missing_required()
    if pendentes:
        logger.warning(
            "Variaveis de ambiente nao configuradas: %s. "
            "Copie o .env.example para .env e preencha.",
            ", ".join(pendentes),
        )

    logger.info("App iniciado (env=%s, instancia=%s)", settings.FLASK_ENV, settings.EVOLUTION_INSTANCE)
    return app
