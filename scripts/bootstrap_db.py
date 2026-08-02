#!/usr/bin/env python3
"""Cria o role 'bot_app' e faz dele o dono do schema 'bot'.

Roda UMA VEZ por ambiente (cada Postgres novo - local ou a VPS), usando o
role admin da Evolution (POSTGRES_PASSWORD) so pra esse bootstrap. Depois
disso, o app e o script de clientes usam DATABASE_URL com o role 'bot_app',
que nao enxerga as tabelas internas da Evolution (Baileys, sessoes etc.) -
so o schema 'bot'.

Seguro rodar de novo (idempotente): se o role ja existir, so atualiza a
senha; se o schema ja existir, so garante que o dono e o 'bot_app'.

    docker compose exec bot python scripts/bootstrap_db.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402


def _admin_url() -> str:
    senha = os.environ.get("POSTGRES_PASSWORD")
    if not senha:
        print("Erro: variavel POSTGRES_PASSWORD nao encontrada no ambiente.", file=sys.stderr)
        sys.exit(1)
    host = os.environ.get("POSTGRES_HOST", "postgres")
    return f"postgresql://evolution:{senha}@{host}:5432/evolution"


def main() -> None:
    senha_bot = os.environ.get("BOT_DB_PASSWORD")
    if not senha_bot:
        print("Erro: defina BOT_DB_PASSWORD no .env antes de rodar este script.", file=sys.stderr)
        sys.exit(1)

    with psycopg.connect(_admin_url(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'bot_app'")
            if cur.fetchone():
                cur.execute(
                    sql.SQL("ALTER ROLE bot_app WITH LOGIN PASSWORD {}").format(sql.Literal(senha_bot))
                )
                print("Role 'bot_app' ja existia; senha atualizada.")
            else:
                cur.execute(
                    sql.SQL("CREATE ROLE bot_app WITH LOGIN PASSWORD {}").format(sql.Literal(senha_bot))
                )
                print("Role 'bot_app' criado.")

            cur.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'bot'")
            if cur.fetchone():
                cur.execute("ALTER SCHEMA bot OWNER TO bot_app")
                print("Schema 'bot' ja existia; dono ajustado para 'bot_app'.")
            else:
                cur.execute("CREATE SCHEMA bot AUTHORIZATION bot_app")
                print("Schema 'bot' criado, de propriedade de 'bot_app'.")

    print(
        "\nPronto. Confira se DATABASE_URL no .env aponta para o role 'bot_app' "
        "(ver .env.example) e reinicie o bot: docker compose up -d --build bot"
    )


if __name__ == "__main__":
    main()
