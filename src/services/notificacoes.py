"""Notificacoes para a equipe da academia (hoje: e-mail)."""

import base64
import logging
import smtplib
from email.message import EmailMessage

from src.config import settings

logger = logging.getLogger(__name__)


class NotificacaoError(RuntimeError):
    """Erro ao enviar uma notificacao para a equipe."""


def enviar_email_equipe(destinatario: str, assunto: str, corpo: str) -> None:
    """Manda um e-mail avisando a equipe do cliente. Nao faz nada se o SMTP ou o
    destinatario nao estiverem configurados."""
    if not (settings.SMTP_USER and settings.SMTP_PASSWORD and destinatario):
        logger.warning("SMTP ou e-mail da equipe nao configurados; notificacao nao enviada.")
        return

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = settings.SMTP_USER
    msg["To"] = destinatario
    msg.set_content(corpo)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise NotificacaoError(f"Falha ao enviar e-mail: {exc}") from exc


def enviar_email_comprovante(
    destinatario: str,
    cliente_nome: str,
    nome_aluno: str,
    contato_nome: str,
    contato_numero: str,
    anexo_base64: str,
    anexo_mimetype: str,
    anexo_nome: str,
) -> None:
    """Encaminha o comprovante de pagamento (anexo) para o e-mail da equipe do
    cliente, junto com o nome do aluno. Nao faz nada se o SMTP ou o
    destinatario nao estiverem configurados."""
    if not (settings.SMTP_USER and settings.SMTP_PASSWORD and destinatario):
        logger.warning("SMTP ou e-mail da equipe nao configurados; comprovante nao enviado.")
        return

    try:
        binario = base64.b64decode(anexo_base64)
    except (ValueError, TypeError) as exc:
        raise NotificacaoError(f"Comprovante invalido (base64): {exc}") from exc

    maintype, _, subtype = (anexo_mimetype or "application/octet-stream").partition("/")

    msg = EmailMessage()
    msg["Subject"] = f"[WhatsApp] Comprovante de pagamento - {nome_aluno}"
    msg["From"] = settings.SMTP_USER
    msg["To"] = destinatario
    msg.set_content(
        f"Cliente: {cliente_nome}\n"
        f"Aluno(a): {nome_aluno}\n"
        f"Enviado por: {contato_nome or '(sem nome)'} ({contato_numero})\n\n"
        "Comprovante em anexo."
    )
    msg.add_attachment(binario, maintype=maintype or "application", subtype=subtype or "octet-stream", filename=anexo_nome)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise NotificacaoError(f"Falha ao enviar e-mail: {exc}") from exc
