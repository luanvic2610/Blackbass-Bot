"""Integracao com a Evolution API: envio de mensagens, botoes, listas e arquivos."""

import logging
from typing import Any

import requests

from src.config import settings
from src.utils.formatters import dividir_texto, para_jid

logger = logging.getLogger(__name__)

TIMEOUT = 30


class EvolutionError(RuntimeError):
    """Erro retornado pela Evolution API."""


def _url(caminho: str) -> str:
    return f"{settings.EVOLUTION_API_URL}/{caminho.lstrip('/')}/{settings.EVOLUTION_INSTANCE}"


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "apikey": settings.EVOLUTION_API_KEY,
    }


def _post(caminho: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = _url(caminho)
    logger.debug("POST %s | payload=%s", url, payload)
    try:
        resp = requests.post(url, json=payload, headers=_headers(), timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise EvolutionError(f"Falha de rede ao chamar {url}: {exc}") from exc

    if resp.status_code >= 400:
        raise EvolutionError(f"Evolution respondeu {resp.status_code}: {resp.text[:500]}")

    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


# --------------------------------------------------------------------------
# Envio de mensagens
# --------------------------------------------------------------------------

def enviar_texto(numero: str, texto: str, delay: int = 1200) -> list[dict[str, Any]]:
    """Envia texto simples. Quebra automaticamente mensagens muito longas."""
    respostas = []
    for parte in dividir_texto(texto):
        respostas.append(
            _post("message/sendText", {
                "number": para_jid(numero),
                "text": parte,
                "delay": delay,
            })
        )
    return respostas


def enviar_botoes(
    numero: str,
    titulo: str,
    descricao: str,
    botoes: list[dict[str, str]],
    rodape: str = "",
) -> dict[str, Any]:
    """Envia mensagem com botoes.

    botoes: [{"id": "1", "titulo": "Horarios"}, ...]  (maximo de 3)
    """
    return _post("message/sendButtons", {
        "number": para_jid(numero),
        "title": titulo,
        "description": descricao,
        "footer": rodape,
        "buttons": [
            {
                "type": "reply",
                "displayText": b["titulo"],
                "id": str(b.get("id", i + 1)),
            }
            for i, b in enumerate(botoes[:3])
        ],
    })


def enviar_lista(
    numero: str,
    titulo: str,
    descricao: str,
    texto_botao: str,
    secoes: list[dict[str, Any]],
    rodape: str = "",
) -> dict[str, Any]:
    """Envia menu em formato de lista (mais de 3 opcoes).

    secoes: [{"title": "Planos", "rows": [{"title": "Mensal", "description": "...",
              "rowId": "plano_mensal"}]}]
    """
    return _post("message/sendList", {
        "number": para_jid(numero),
        "title": titulo,
        "description": descricao,
        "buttonText": texto_botao,
        "footerText": rodape,
        "sections": secoes,
    })


def enviar_arquivo(
    numero: str,
    url_ou_base64: str,
    nome_arquivo: str,
    legenda: str = "",
    tipo: str = "document",
) -> dict[str, Any]:
    """Envia midia. tipo: image | video | document | audio."""
    return _post("message/sendMedia", {
        "number": para_jid(numero),
        "mediatype": tipo,
        "media": url_ou_base64,
        "fileName": nome_arquivo,
        "caption": legenda,
    })


def enviar_localizacao(numero: str, nome: str, endereco: str, lat: float, lng: float) -> dict[str, Any]:
    """Envia a localizacao da academia."""
    return _post("message/sendLocation", {
        "number": para_jid(numero),
        "name": nome,
        "address": endereco,
        "latitude": lat,
        "longitude": lng,
    })


def marcar_como_lida(numero: str, message_id: str) -> dict[str, Any]:
    """Marca a mensagem recebida como lida."""
    return _post("chat/markMessageAsRead", {
        "readMessages": [{
            "remoteJid": para_jid(numero),
            "id": message_id,
            "fromMe": False,
        }]
    })


def enviar_digitando(numero: str, duracao_ms: int = 2000) -> dict[str, Any]:
    """Mostra 'digitando...' no chat do contato."""
    return _post("chat/sendPresence", {
        "number": para_jid(numero),
        "presence": "composing",
        "delay": duracao_ms,
    })
