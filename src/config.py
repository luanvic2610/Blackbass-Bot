"""Carrega e valida as variaveis de ambiente do projeto.

Uso:
    from src.config import settings
    print(settings.EVOLUTION_API_URL)
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Le o .env da raiz do projeto (nao sobrescreve variaveis ja definidas no SO).
load_dotenv(override=False)


def _get(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


@dataclass(frozen=True)
class Settings:
    # Aplicacao
    APP_ENV: str = field(default_factory=lambda: _get("APP_ENV", "production"))
    PORT: int = field(default_factory=lambda: int(_get("PORT", "5000")))
    LOG_LEVEL: str = field(default_factory=lambda: _get("LOG_LEVEL", "INFO").upper())

    # Evolution API
    EVOLUTION_API_URL: str = field(
        default_factory=lambda: _get("EVOLUTION_API_URL", "http://localhost:8080").rstrip("/")
    )
    EVOLUTION_API_KEY: str = field(default_factory=lambda: _get("EVOLUTION_API_KEY"))
    EVOLUTION_INSTANCE: str = field(default_factory=lambda: _get("EVOLUTION_INSTANCE"))

    # Seguranca
    WEBHOOK_TOKEN: str = field(default_factory=lambda: _get("WEBHOOK_TOKEN"))

    # Negocio
    ACADEMIA_NOME: str = field(default_factory=lambda: _get("ACADEMIA_NOME", "Academia"))
    ACADEMIA_TELEFONE: str = field(default_factory=lambda: _get("ACADEMIA_TELEFONE"))
    ACADEMIA_ENDERECO: str = field(default_factory=lambda: _get("ACADEMIA_ENDERECO"))

    # Notificacoes por e-mail (ex: cliente pediu para falar com atendente)
    SMTP_HOST: str = field(default_factory=lambda: _get("SMTP_HOST", "smtp.gmail.com"))
    SMTP_PORT: int = field(default_factory=lambda: int(_get("SMTP_PORT", "587")))
    SMTP_USER: str = field(default_factory=lambda: _get("SMTP_USER"))
    SMTP_PASSWORD: str = field(default_factory=lambda: _get("SMTP_PASSWORD"))
    EMAIL_EQUIPE: str = field(default_factory=lambda: _get("EMAIL_EQUIPE"))

    @property
    def is_debug(self) -> bool:
        return self.APP_ENV.lower() in {"development", "dev", "debug"}

    def missing_required(self) -> list[str]:
        """Retorna a lista de variaveis obrigatorias que nao foram preenchidas."""
        required = ("EVOLUTION_API_URL", "EVOLUTION_API_KEY", "EVOLUTION_INSTANCE")
        return [name for name in required if not getattr(self, name)]


settings = Settings()
