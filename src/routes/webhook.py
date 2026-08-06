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


def _extrair_midia(mensagem: dict[str, Any]) -> dict[str, Any] | None:
    """Detecta se a mensagem e uma imagem/documento (usado no fluxo de comprovante
    de pagamento). Diferente de `_extrair_texto`, aqui a legenda pode estar vazia."""
    if not isinstance(mensagem, dict):
        return None
    imagem = mensagem.get("imageMessage")
    if isinstance(imagem, dict):
        return {"tipo": "image", "info": imagem}
    documento = mensagem.get("documentMessage")
    if isinstance(documento, dict):
        return {"tipo": "document", "info": documento}
    doc_legenda = (mensagem.get("documentWithCaptionMessage") or {}).get("message", {}).get("documentMessage")
    if isinstance(doc_legenda, dict):
        return {"tipo": "document", "info": doc_legenda}
    return None


def _receber_comprovante_pix(
    instancia: str,
    numero: str,
    nome_contato: str,
    cliente: Any,
    chave_mensagem: dict[str, Any],
    midia: dict[str, Any],
    nome_aluno: str,
) -> JSONResponse:
    """Baixa o comprovante recebido e encaminha por e-mail para a equipe do cliente."""
    if chave_mensagem.get("id"):
        try:
            evolution.marcar_como_lida(instancia, numero, chave_mensagem["id"])
        except evolution.EvolutionError as exc:
            logger.debug("Nao consegui marcar comprovante como lido: %s", exc)

    info = midia["info"]
    nome_arquivo = info.get("fileName") or ("comprovante.jpg" if midia["tipo"] == "image" else "comprovante.pdf")

    resultado = evolution.obter_midia_base64(instancia, chave_mensagem)
    base64_midia = resultado.get("base64")
    if not base64_midia:
        logger.error("Resposta da Evolution sem base64 para comprovante de %s.", numero)
        evolution.enviar_texto(
            instancia, numero,
            "Nao consegui processar o arquivo. Pode tentar enviar de novo?",
        )
        return JSONResponse({"status": "error", "detail": "sem_base64"}, status_code=200)

    mimetype = resultado.get("mimetype") or info.get("mimetype") or "application/octet-stream"

    try:
        notificacoes.enviar_email_comprovante(
            destinatario=cliente.email_equipe,
            cliente_nome=cliente.nome,
            nome_aluno=nome_aluno,
            contato_nome=nome_contato,
            contato_numero=numero,
            anexo_base64=base64_midia,
            anexo_mimetype=mimetype,
            anexo_nome=nome_arquivo,
        )
    except notificacoes.NotificacaoError as exc:
        logger.error("Falha ao encaminhar comprovante por e-mail (%s): %s", numero, exc)
        evolution.enviar_texto(
            instancia, numero,
            "Recebi o comprovante, mas tive um problema para encaminhar para a equipe. "
            "Vou avisar por outro canal.",
        )
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=200)

    bot_logic.limpar_estado(instancia, numero)
    evolution.enviar_texto(
        instancia, numero,
        f"Recebido! Encaminhei o comprovante de {nome_aluno} para a equipe.\n\n"
        "Digite *menu* para voltar.",
    )
    return JSONResponse({"status": "ok", "acao": "comprovante_encaminhado"}, status_code=200)


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

    if jid.endswith("@lid"):
        # WhatsApp manda um JID anonimo (@lid) em vez do numero em alguns
        # casos (comum em quem usa Android). Desde que a Evolution/Baileys
        # atualizou, o numero real vem em `remoteJidAlt` (ou `senderPn` em
        # versoes mais antigas). Sem isso nao tem como responder.
        jid_real = chave.get("remoteJidAlt") or chave.get("senderPn") or ""
        if not jid_real:
            logger.warning("JID @lid sem numero real (remoteJidAlt/senderPn); ignorando. jid=%s", jid)
            return JSONResponse({"status": "ignored", "reason": "lid_sem_numero_real"}, status_code=200)
        jid = jid_real

    numero = do_jid(jid)

    if chave.get("fromMe"):
        # A Evolution manda source="web" tanto pra mensagem que o bot envia
        # via API quanto pra mensagem que um humano manda pelo WhatsApp Web
        # de verdade - nao da pra diferenciar pelo `source`. Por isso
        # conferimos se foi a gente que mandou pelo id da mensagem; qualquer
        # outra (celular ou WhatsApp Web) foi a equipe respondendo manualmente.
        if numero and not evolution.foi_enviado_por_nos(chave.get("id")):
            bot_logic.ativar_silencio(instancia, numero)
            logger.info("Equipe respondeu manualmente para %s; bot em silencio.", numero)
        return JSONResponse({"status": "ignored", "reason": "fromMe"}, status_code=200)

    mensagem = dados.get("message") or {}
    texto = _extrair_texto(mensagem)
    midia = _extrair_midia(mensagem)
    nome = dados.get("pushName", "") or ""

    if not numero:
        return JSONResponse({"status": "ignored", "reason": "sem numero"}, status_code=200)

    nome_aluno_pix = midia and bot_logic.aguardando_comprovante_pix(instancia, numero)
    if midia and nome_aluno_pix:
        try:
            return _receber_comprovante_pix(instancia, numero, nome, cliente, chave, midia, nome_aluno_pix)
        except evolution.EvolutionError as exc:
            logger.error("Erro ao processar comprovante de %s: %s", numero, exc)
            return JSONResponse({"status": "error", "detail": str(exc)}, status_code=200)
        except Exception:  # noqa: BLE001
            logger.exception("Erro inesperado processando comprovante de %s.", numero)
            return JSONResponse({"status": "error"}, status_code=200)

    if not texto:
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
