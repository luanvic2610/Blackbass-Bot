"""DDL das tabelas do schema 'bot' (schema em si e criado pelo bootstrap).

Sem ferramenta de migracao (Alembic etc.) de proposito: sao poucas tabelas e
mudam raramente. Convencao para evoluir o schema no futuro:

    - Nunca editar as instrucoes `CREATE TABLE` ja existentes abaixo.
    - Novas colunas entram como `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...`,
      adicionadas ao final da lista `_INSTRUCOES`, cada uma com um comentario
      `-- vN: o que e quando`.
    - Tudo deve ser idempotente (`IF NOT EXISTS`): `ensure_schema()` roda em
      todo start da aplicacao e tambem no inicio do script de gerenciamento de
      clientes.

O schema 'bot' em si NAO e criado aqui: quem faz isso e
`scripts/bootstrap_db.py` (rodando com o role admin da Evolution), porque
criar um schema exige privilegio de CREATE no banco inteiro. O app roda com
o role `bot_app`, que so e dono do schema `bot` - suficiente para criar
tabelas/indices dentro dele, mas nao para criar o schema em si.
"""

import logging

import psycopg

logger = logging.getLogger(__name__)

_INSTRUCOES = (
    """
    CREATE TABLE IF NOT EXISTS bot.clientes (
        instancia                    TEXT PRIMARY KEY,
        nome                         TEXT NOT NULL,
        telefone                     TEXT NOT NULL DEFAULT '',
        endereco                     TEXT NOT NULL DEFAULT '',
        horario_funcionamento        TEXT NOT NULL DEFAULT '',
        google_maps_url              TEXT NOT NULL DEFAULT '',
        instagram_url                TEXT NOT NULL DEFAULT '',
        form_aula_experimental_url   TEXT NOT NULL DEFAULT '',
        email_equipe                 TEXT NOT NULL DEFAULT '',
        grade_horarios               JSONB NOT NULL DEFAULT '{}'::jsonb,
        ativo                        BOOLEAN NOT NULL DEFAULT true,
        criado_em                    TIMESTAMPTZ NOT NULL DEFAULT now(),
        atualizado_em                TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_bot_clientes_ativo ON bot.clientes (ativo);",
    # v1: chave PIX de cada cliente, usada no fluxo de pagamento de mensalidade do bot.
    "ALTER TABLE bot.clientes ADD COLUMN IF NOT EXISTS pix_chave TEXT NOT NULL DEFAULT '';",
)


def ensure_schema(conn: psycopg.Connection) -> None:
    """Cria as tabelas do schema 'bot' se ainda nao existirem. Seguro rodar toda vez."""
    with conn.cursor() as cur:
        for instrucao in _INSTRUCOES:
            cur.execute(instrucao)
    conn.commit()
    logger.debug("Tabelas do schema 'bot' verificadas/criadas com sucesso.")
