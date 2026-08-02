"""Notificacoes para a equipe da academia (hoje: e-mail)."""

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
