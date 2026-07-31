"""Rota que recebe os eventos da Evolution API."""

import logging
from typing import Any

from flask import Blueprint, jsonify, request

from src.config import settings
from src.services import bot_logic, evolution
from src.utils.formatters import do_jid

logger = logging.getLogger(__name__)

webhook_bp = Blueprint("webhook", __name__)


def _extrair_texto(mensagem: dict[str, Any]) -> str:
    """A Evolution entrega o texto em campos diferentes conforme o tipo."""
    if not isinstance(mensagem, dict):
        return ""
    return (
        mensagem.get("conversation")
        or mensagem.get("extendedTextMessage", {}).get("text")
        or mensagem.get("imageMessage", {}).get("caption")
        or mensagem.get("videoMessage", {}).get("caption")
        or mensagem.get("buttonsResponseMessage", {}).get("selectedButtonId")
        or mensagem.get("listResponseMessage", {})
             .get("singleSelectReply", {}).get("selectedRowId")
        or mensagem.get("templateButtonReplyMessage", {}).get("selectedId")
        or ""
    ).strip()


def _token_valido() -> bool:
    if not settings.WEBHOOK_TOKEN:
        return True  # validacao desativada
    enviado = request.headers.get("X-Webhook-Token") or request.args.get("token")
    return enviado == settings.WEBHOOK_TOKEN


@webhook_bp.post("/webhook")
@webhook_bp.post("/webhook/messages-upsert")
def receber():
    """Endpoint configurado na Evolution API (evento MESSAGES_UPSERT)."""
    if not _token_valido():
        logger.warning("Webhook recebido com token invalido.")
        return jsonify({"status": "unauthorized"}), 401

    corpo = request.get_json(silent=True) or {}
    evento = corpo.get("event", "")
    dados = corpo.get("data") or {}

    # A Evolution pode mandar uma lista de mensagens.
    if isinstance(dados, list):
        dados = dados[0] if dados else {}

    if evento and "messages.upsert" not in evento.replace("_", ".").lower():
        logger.debug("Evento ignorado: %s", evento)
        return jsonify({"status": "ignored", "event": evento}), 200

    chave = dados.get("key") or {}

    # Ignora o que o proprio bot enviou e mensagens de grupo.
    if chave.get("fromMe"):
        return jsonify({"status": "ignored", "reason": "fromMe"}), 200

    jid = chave.get("remoteJid", "")
    if jid.endswith("@g.us"):
        return jsonify({"status": "ignored", "reason": "grupo"}), 200

    numero = do_jid(jid)
    texto = _extrair_texto(dados.get("message") or {})
    nome = dados.get("pushName", "") or ""

    if not numero or not texto:
        return jsonify({"status": "ignored", "reason": "sem texto"}), 200

    logger.info("Mensagem de %s (%s): %s", nome, numero, texto)

    try:
        resposta = bot_logic.processar_mensagem(numero, texto, nome)

        if resposta.get("tipo") == "ignorar":
            return jsonify({"status": "ok", "acao": "nenhuma"}), 200

        if chave.get("id"):
            try:
                evolution.marcar_como_lida(numero, chave["id"])
            except evolution.EvolutionError as exc:
                logger.debug("Nao consegui marcar como lida: %s", exc)

        evolution.enviar_digitando(numero, 1500)
        evolution.enviar_texto(numero, resposta["texto"])

        if resposta.get("tipo") == "encaminhar":
            # TODO: notificar a equipe (grupo interno, e-mail, CRM...).
            logger.info("Contato %s precisa de atendimento humano.", numero)

    except evolution.EvolutionError as exc:
        logger.error("Erro ao responder %s: %s", numero, exc)
        # 200 evita reenvio infinito pela Evolution.
        return jsonify({"status": "error", "detail": str(exc)}), 200
    except Exception:  # noqa: BLE001
        logger.exception("Erro inesperado processando webhook.")
        return jsonify({"status": "error"}), 200

    return jsonify({"status": "ok"}), 200


@webhook_bp.get("/health")
def health():
    """Healthcheck usado pelo Docker e por monitoramento."""
    return jsonify({
        "status": "ok",
        "instancia": settings.EVOLUTION_INSTANCE,
        "config_pendente": settings.missing_required(),
    }), 200
