"""Servei d'enviament d'emails per SMTP (asíncron via aiosmtplib).

Usat per a notificacions manuals de visites previstes. La configuració SMTP
prové de variables d'entorn (settings.SMTP_*). Si SMTP_HOST no està
configurat, send_email retorna False sense fer res.
"""
from email.message import EmailMessage

import aiosmtplib

from app.config import settings


def smtp_configured() -> bool:
    return bool(settings.SMTP_HOST)


async def send_email(
    to: list[str],
    subject: str,
    body: str,
) -> tuple[bool, str]:
    """Envia un email pla. Retorna (ok, missatge).

    Pren la configuració de settings.SMTP_*. Si el port és 465 usa SMTPS
    (TLS implícit); altrament usa STARTTLS si el servidor el suporta. Si
    SMTP_USER està buit, no fa autenticació.
    """
    if not smtp_configured():
        return False, "SMTP no configurat"
    if not to:
        return False, "Cap destinatari"

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER or "noreply@localhost"
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)

    use_tls = settings.SMTP_PORT == 465
    start_tls = settings.SMTP_PORT in (587, 25) and not use_tls

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            use_tls=use_tls,
            start_tls=start_tls,
            timeout=15,
        )
    except Exception as exc:  # aiosmtplib llança subclasses de SMTPException
        return False, f"Error enviant email: {exc}"
    return True, "OK"
