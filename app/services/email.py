"""Servei d'enviament d'emails amb tres backends pluggables.

Selecció via `settings.EMAIL_BACKEND`:
  - 'smtp'           → SMTP clàssic (aiosmtplib)
  - 'graph_ms'       → Microsoft Graph API (msal + httpx)
  - 'power_automate' → webhook a un flux de Power Automate (httpx)

Power Automate és la opció més senzilla per a M365 quan l'admin del
tenant no vol concedir admin consent a una app de Graph: el flux corre
amb les credencials de l'usuari que el crea, sense necessitat de cap
permís d'aplicació.

Graph és el recomanat per a integracions de llarga durada (sobreviu
millor a canvis del propietari del flux i té auditoria centralitzada).

API pública (sense canvis):
    smtp_configured() -> bool
    send_email(to, subject, body) -> tuple[bool, str]
"""
import asyncio
import time
from email.message import EmailMessage

import aiosmtplib

from app.config import settings


# ─── Token cache compartit per als enviaments via Graph ────────────
# In-process (per worker uvicorn). Es regenera automàticament quan
# falten <60s per caducar. Token de Graph dura típicament 3600s.
_graph_token_cache: dict = {"token": None, "expires_at": 0.0}


def smtp_configured() -> bool:
    """True si el backend actiu té tota la configuració necessària."""
    backend = settings.EMAIL_BACKEND
    if backend == "graph_ms":
        return bool(
            settings.MS_TENANT_ID
            and settings.MS_CLIENT_ID
            and settings.MS_CLIENT_SECRET
            and settings.MS_SENDER_EMAIL
        )
    if backend == "power_automate":
        return bool(settings.POWER_AUTOMATE_WEBHOOK_URL)
    return bool(settings.SMTP_HOST)


async def send_email(
    to: list[str],
    subject: str,
    body: str,
) -> tuple[bool, str]:
    """Punt d'entrada únic. Retorna (ok, missatge)."""
    if not to:
        return False, "Cap destinatari"

    # Override per a proves: redirigir-ho tot a una adreça única i
    # afegir al cos els destinataris reals per traçabilitat.
    if settings.EMAIL_OVERRIDE_RECIPIENT:
        original_to = ", ".join(to)
        body = (
            f"[PROVA — destinatari original: {original_to}]\n\n"
            f"{body}"
        )
        to = [settings.EMAIL_OVERRIDE_RECIPIENT]
        subject = f"[PROVA] {subject}"

    backend = settings.EMAIL_BACKEND
    if backend == "graph_ms":
        return await _send_via_graph(to, subject, body)
    if backend == "power_automate":
        return await _send_via_power_automate(to, subject, body)
    return await _send_via_smtp(to, subject, body)


# ─── Backend SMTP ───────────────────────────────────────────────────

async def _send_via_smtp(to: list[str], subject: str, body: str) -> tuple[bool, str]:
    if not settings.SMTP_HOST:
        return False, "SMTP no configurat"

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
    except Exception as exc:
        return False, f"Error enviant email: {exc}"
    return True, "OK"


# ─── Backend Microsoft Graph ────────────────────────────────────────

def _acquire_graph_token_sync() -> tuple[str | None, str]:
    """Obté un access token via client credentials flow. Síncron (msal
    bloca el thread); s'invoca des d'un thread separat."""
    import msal
    authority = f"https://login.microsoftonline.com/{settings.MS_TENANT_ID}"
    app = msal.ConfidentialClientApplication(
        client_id=settings.MS_CLIENT_ID,
        client_credential=settings.MS_CLIENT_SECRET,
        authority=authority,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        err = result.get("error_description") or result.get("error") or "unknown"
        return None, str(err)[:300]
    return result["access_token"], str(result.get("expires_in", 3600))


async def _get_graph_token() -> tuple[str | None, str]:
    """Retorna (token, message). El token és None si hi ha error."""
    if not all([settings.MS_TENANT_ID, settings.MS_CLIENT_ID, settings.MS_CLIENT_SECRET]):
        return None, "Configuració M365 incompleta"

    cached = _graph_token_cache.get("token")
    expires = _graph_token_cache.get("expires_at", 0.0)
    if cached and expires > time.time() + 60:
        return cached, "cached"

    # msal és síncron — l'envoltem amb to_thread per no bloquejar l'event loop
    token, info = await asyncio.to_thread(_acquire_graph_token_sync)
    if not token:
        return None, f"No s'ha pogut obtenir token: {info}"
    try:
        ttl = int(info)
    except (TypeError, ValueError):
        ttl = 3600
    _graph_token_cache["token"] = token
    _graph_token_cache["expires_at"] = time.time() + ttl
    return token, "fresh"


# ─── Backend Power Automate (webhook) ──────────────────────────────

async def _send_via_power_automate(
    to: list[str], subject: str, body: str
) -> tuple[bool, str]:
    import httpx

    if not settings.POWER_AUTOMATE_WEBHOOK_URL:
        return False, "POWER_AUTOMATE_WEBHOOK_URL no configurat"

    payload = {
        "to": to,
        "subject": subject,
        "body": body,
    }
    headers = {"Content-Type": "application/json"}
    if settings.POWER_AUTOMATE_SECRET:
        # El flux pot validar aquest header al primer pas. Si no el valida,
        # el header simplement s'ignora (cap problema).
        headers["X-Webhook-Secret"] = settings.POWER_AUTOMATE_SECRET

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                settings.POWER_AUTOMATE_WEBHOOK_URL,
                json=payload,
                headers=headers,
            )
            # 200/202: acceptat directament (millor cas, configuració
            # asíncrona del flux).
            if resp.status_code in (200, 202):
                return True, "OK"
            # 502 NoResponse: el flux està funcionant en background però
            # el gateway de Power Automate ha excedit el seu timeout
            # síncron. L'execució s'ha encolat correctament — el flux
            # acabarà i enviarà l'email igualment. Considerem-ho èxit
            # amb avís perquè altrament la creació de la prevista
            # quedaria marcada com a fallida sense ser cert.
            # Solució definitiva: activar 'Respuesta asíncrona' al
            # trigger del flux.
            if resp.status_code == 502 and "NoResponse" in resp.text:
                return True, "queued (Power Automate gateway timeout — flux OK)"
            return False, f"Power Automate {resp.status_code}: {resp.text[:300]}"
    except Exception as exc:
        return False, f"Error Power Automate: {exc}"


async def _send_via_graph(to: list[str], subject: str, body: str) -> tuple[bool, str]:
    import httpx

    if not settings.MS_SENDER_EMAIL:
        return False, "MS_SENDER_EMAIL no configurat"

    token, info = await _get_graph_token()
    if not token:
        return False, info

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [
                {"emailAddress": {"address": addr}} for addr in to
            ],
        },
        "saveToSentItems": "true",
    }

    url = (
        "https://graph.microsoft.com/v1.0/users/"
        f"{settings.MS_SENDER_EMAIL}/sendMail"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 202):
                return True, "OK"
            # Errors típics: 401 token caducat, 403 permisos no concedits,
            # 404 bústia inexistent, 503 servei no disponible.
            return False, f"Graph {resp.status_code}: {resp.text[:300]}"
    except Exception as exc:
        return False, f"Error Graph: {exc}"
