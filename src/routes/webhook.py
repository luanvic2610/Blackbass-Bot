"""Rota que recebe os eventos da Evolution API."""

import logging
from typing import Any

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse

from src.config import settings
from src.services import bot_logic, clientes, evolution, notificacoes
from src.utils.formatters import do_jid

logger = logging.getLogger(__name__)

webhook_router = APIRouter()


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


def _token_valido(x_webhook_token: str | None, token: str | None) -> bool:
    if not settings.WEBHOOK_TOKEN:
        return True  # validacao desativada
    enviado = x_webhook_token or token
    return enviado == settings.WEBHOOK_TOKEN


@webhook_router.post("/webhook")
@webhook_router.post("/webhook/messages-upsert")
def receber(
    corpo: dict[str, Any] = Body(default={}),
    x_webhook_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
):
    """Endpoint configurado na Evolution API (evento MESSAGES_UPSERT).

    Uma unica URL de webhook atende todos os clientes: a Evolution manda o
    nome da instancia no campo `instance` de todo payload, e esse campo e
    usado para descobrir de qual cliente (academia) e essa mensagem.
    """
    if not _token_valido(x_webhook_token, token):
        logger.warning("Webhook recebido com token invalido.")
        return JSONResponse({"status": "unauthorized"}, status_code=401)

    instancia = corpo.get("instance", "") or ""
    evento = corpo.get("event", "")
    dados = corpo.get("data") or {}

    # A Evolution pode mandar uma lista de mensagens.
    if isinstance(dados, list):
        dados = dados[0] if dados else {}

    if evento and "messages.upsert" not in evento.replace("_", ".").lower():
        logger.debug("Evento ignorado: %s", evento)
        return JSONResponse({"status": "ignored", "event": evento}, status_code=200)

    if not instancia:
        logger.warning("Webhook sem campo 'instance'; nao da pra saber de qual cliente e.")
        return JSONResponse({"status": "ignored", "reason": "instancia_ausente"}, status_code=200)

    cliente = clientes.buscar_cliente(instancia)
    if cliente is None:
        logger.warning("Instancia desconhecida: %s", instancia)
        return JSONResponse({"status": "ignored", "reason": "tenant_desconhecido"}, status_code=200)

    if not cliente.ativo:
        logger.info("Instancia %s esta desativada; ignorando.", instancia)
        return JSONResponse({"status": "ignored", "reason": "tenant_inativo"}, status_code=200)

    chave = dados.get("key") or {}
    jid = chave.get("remoteJid", "")

    if jid.endswith("@g.us"):
        return JSONResponse({"status": "ignored", "reason": "grupo"}, status_code=200)

    numero = do_jid(jid)

    if chave.get("fromMe"):
        # Mensagens que o bot manda pela API chegam com source="web". Se vier
        # de outro source (ios/android), foi a equipe digitando manualmente
        # no celular conectado: bot fica em silencio pra esse numero.
        if numero and dados.get("source") != "web":
            bot_logic.ativar_silencio(instancia, numero)
            logger.info("Equipe respondeu manualmente para %s; bot em silencio.", numero)
        return JSONResponse({"status": "ignored", "reason": "fromMe"}, status_code=200)

    texto = _extrair_texto(dados.get("message") or {})
    nome = dados.get("pushName", "") or ""

    if not numero or not texto:
        return JSONResponse({"status": "ignored", "reason": "sem texto"}, status_code=200)

    logger.info("Mensagem de %s (%s) para %s: %s", nome, numero, instancia, texto)

    try:
        resposta = bot_logic.processar_mensagem(instancia, numero, texto, cliente, nome)

        if resposta.get("tipo") == "ignorar":
            return JSONResponse({"status": "ok", "acao": "nenhuma"}, status_code=200)

        if chave.get("id"):
            try:
                evolution.marcar_como_lida(instancia, numero, chave["id"])
            except evolution.EvolutionError as exc:
                logger.debug("Nao consegui marcar como lida: %s", exc)

        evolution.enviar_digitando(instancia, numero, 1500)
        evolution.enviar_texto(instancia, numero, resposta["texto"])

        if resposta.get("tipo") == "encaminhar":
            logger.info("Contato %s precisa de atendimento humano (%s).", numero, instancia)
            try:
                notificacoes.enviar_email_equipe(
                    destinatario=cliente.email_equipe,
                    assunto=f"[WhatsApp] {nome or numero} quer falar com atendente",
                    corpo=(
                        f"Cliente: {cliente.nome} ({instancia})\n"
                        f"Contato: {nome or '(sem nome)'}\n"
                        f"Numero: {numero}\n"
                        f"Mensagem: {texto}\n"
                    ),
                )
            except notificacoes.NotificacaoError as exc:
                logger.error("Falha ao notificar equipe por e-mail: %s", exc)

    except evolution.EvolutionError as exc:
        logger.error("Erro ao responder %s: %s", numero, exc)
        # 200 evita reenvio infinito pela Evolution.
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=200)
    except Exception:  # noqa: BLE001
        logger.exception("Erro inesperado processando webhook.")
        return JSONResponse({"status": "error"}, status_code=200)

    return JSONResponse({"status": "ok"}, status_code=200)


@webhook_router.get("/health")
def health():
    """Healthcheck usado pelo Docker e por monitoramento."""
    return {
        "status": "ok",
        "clientes_ativos": clientes.contar_ativos(),
        "config_pendente": settings.missing_required(),
    }
