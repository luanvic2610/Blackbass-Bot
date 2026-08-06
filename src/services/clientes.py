"""Configuracao de cada cliente (academia) cadastrado no banco.

Cada cliente = uma instancia da Evolution API (um numero de WhatsApp). O
webhook resolve "qual cliente e esse?" a partir do campo `instance` que a
Evolution manda em todo evento, e usa esse modulo pra buscar a configuracao
correspondente (nome, endereco, grade de horarios etc.).

Cache em processo com TTL curto: como sao poucas linhas (~10 clientes) e o
app roda em 1 worker so, um cache simples aqui evita bater no banco a cada
mensagem sem precisar de Redis ou de invalidacao entre processos.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any

from psycopg.rows import dict_row

from src.db.pool import get_pool

logger = logging.getLogger(__name__)

_CACHE_TTL_SEGUNDOS = 30
_cache: dict[str, tuple[Any, float]] = {}


@dataclass(frozen=True)
class ClienteConfig:
    instancia: str
    nome: str
    telefone: str
    endereco: str
    horario_funcionamento: str
    google_maps_url: str
    instagram_url: str
    form_aula_experimental_url: str
    email_equipe: str
    pix_chave: str
    loja_url: str
    loja_cupom: str
    grade_horarios: dict[str, list[str]]
    ativo: bool


def _linha_para_cliente(linha: dict[str, Any]) -> ClienteConfig:
    return ClienteConfig(
        instancia=linha["instancia"],
        nome=linha["nome"],
        telefone=linha["telefone"],
        endereco=linha["endereco"],
        horario_funcionamento=linha["horario_funcionamento"],
        google_maps_url=linha["google_maps_url"],
        instagram_url=linha["instagram_url"],
        form_aula_experimental_url=linha["form_aula_experimental_url"],
        email_equipe=linha["email_equipe"],
        pix_chave=linha["pix_chave"],
        loja_url=linha["loja_url"],
        loja_cupom=linha["loja_cupom"],
        grade_horarios=linha["grade_horarios"] or {},
        ativo=linha["ativo"],
    )


def _carregar_do_banco(instancia: str) -> ClienteConfig | None:
    with get_pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM bot.clientes WHERE instancia = %s", (instancia,))
            linha = cur.fetchone()
    return _linha_para_cliente(linha) if linha else None


def buscar_cliente(instancia: str) -> ClienteConfig | None:
    """Busca a configuracao do cliente pelo nome da instancia, com cache de 30s."""
    if not instancia:
        return None

    agora = time.monotonic()
    em_cache = _cache.get(instancia)
    if em_cache and agora - em_cache[1] < _CACHE_TTL_SEGUNDOS:
        return em_cache[0]

    cliente = _carregar_do_banco(instancia)
    _cache[instancia] = (cliente, agora)
    return cliente


def invalidar_cache(instancia: str | None = None) -> None:
    """Forca a proxima busca a ir no banco. Sem endpoint publico - uso interno."""
    if instancia is None:
        _cache.clear()
    else:
        _cache.pop(instancia, None)


def contar_ativos() -> int:
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM bot.clientes WHERE ativo")
            (total,) = cur.fetchone()
    return total
