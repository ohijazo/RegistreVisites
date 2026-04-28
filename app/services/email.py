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


def text_to_html(text: str) -> str:
    """Converteix text pla a HTML bàsic preservant els salts de línia.

    - Escapa caràcters HTML especials.
    - Línies en blanc dobles → paràgrafs separats.
    - Línies simples → <br>.
    """
    import html
    if not text:
        return ""
    escaped = html.escape(text)
    paragraphs = escaped.split("\n\n")
    parts = []
    for p in paragraphs:
        p = p.strip("\n")
        if p:
            parts.append("<p style=\"margin:0 0 12px 0;\">" + p.replace("\n", "<br>") + "</p>")
    return "\n".join(parts)


async def send_email(
    to: list[str],
    subject: str,
    body: str,
    html_body: str | None = None,
    qr_png: bytes | None = None,
) -> tuple[bool, str]:
    """Punt d'entrada únic. Retorna (ok, missatge).

    Paràmetres:
        to:        llista de destinataris.
        subject:   assumpte.
        body:      cos en text pla (sempre obligatori; serveix de fallback
                   per a clients que no renderitzen HTML).
        html_body: cos en HTML opcional. Si no es proporciona, es genera
                   automàticament a partir del text pla.
    """
    if not to:
        return False, "Cap destinatari"

    # Override per a proves: redirigir-ho tot a una adreça única i
    # afegir al cos els destinataris reals per traçabilitat.
    if settings.EMAIL_OVERRIDE_RECIPIENT:
        original_to = ", ".join(to)
        prefix_text = f"[PROVA — destinatari original: {original_to}]\n\n"
        body = prefix_text + body
        if html_body:
            html_body = (
                f"<div style=\"background:#fef3c7;border:1px solid #f59e0b;"
                f"padding:10px 14px;border-radius:6px;margin-bottom:16px;"
                f"font-size:13px;color:#92400e;\">"
                f"⚠ <strong>Mode prova</strong> — destinatari original: "
                f"<code>{original_to}</code></div>" + html_body
            )
        to = [settings.EMAIL_OVERRIDE_RECIPIENT]
        subject = f"[PROVA] {subject}"

    # Si no s'ha proporcionat HTML, generar-lo a partir del text pla
    # (sobretot perquè el flux de Power Automate té 'Es HTML?' actiu i
    # altrament el text pla es renderitzaria sense salts de línia).
    if html_body is None:
        html_body = text_to_html(body)

    backend = settings.EMAIL_BACKEND
    if backend == "graph_ms":
        return await _send_via_graph(to, subject, body, html_body, qr_png)
    if backend == "power_automate":
        return await _send_via_power_automate(to, subject, body, html_body, qr_png)
    return await _send_via_smtp(to, subject, body, html_body, qr_png)


# ─── Backend SMTP ───────────────────────────────────────────────────

async def _send_via_smtp(
    to: list[str], subject: str, body: str,
    html_body: str | None = None, qr_png: bytes | None = None,
) -> tuple[bool, str]:
    if not settings.SMTP_HOST:
        return False, "SMTP no configurat"

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER or "noreply@localhost"
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
        # Inline QR per <img src="cid:qr.png">
        if qr_png:
            msg.get_payload()[1].add_related(
                qr_png, maintype="image", subtype="png", cid="<qr.png>"
            )

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
    to: list[str], subject: str, body: str,
    html_body: str | None = None, qr_png: bytes | None = None,
) -> tuple[bool, str]:
    import base64 as _b64
    import httpx

    if not settings.POWER_AUTOMATE_WEBHOOK_URL:
        return False, "POWER_AUTOMATE_WEBHOOK_URL no configurat"

    # El flux té 'Es HTML?' activat, per tant enviem el cos en HTML.
    # Si l'usuari ha cridat send_email() sense html_body, ja s'haurà
    # convertit a HTML al punt d'entrada.
    payload = {
        "to": to,
        "subject": subject,
        "body": html_body or body,
        # Adjunt inline opcional. El flux ha de mapar-lo a un attachment
        # de Outlook V2 amb name="qr.png"; quan el cos HTML referencia
        # <img src="cid:qr.png">, Outlook l'enllaça automàticament.
        "qr_attachment_base64": _b64.b64encode(qr_png).decode() if qr_png else "",
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


async def _send_via_graph(
    to: list[str], subject: str, body: str,
    html_body: str | None = None, qr_png: bytes | None = None,
) -> tuple[bool, str]:
    import base64 as _b64
    import httpx

    if not settings.MS_SENDER_EMAIL:
        return False, "MS_SENDER_EMAIL no configurat"

    token, info = await _get_graph_token()
    if not token:
        return False, info

    if html_body:
        body_part = {"contentType": "HTML", "content": html_body}
    else:
        body_part = {"contentType": "Text", "content": body}

    message: dict = {
        "subject": subject,
        "body": body_part,
        "toRecipients": [
            {"emailAddress": {"address": addr}} for addr in to
        ],
    }
    if qr_png:
        message["attachments"] = [{
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": "qr.png",
            "contentType": "image/png",
            "contentId": "qr.png",
            "isInline": True,
            "contentBytes": _b64.b64encode(qr_png).decode(),
        }]

    payload = {
        "message": message,
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
