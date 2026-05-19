"""Identitat de dispositius de quiosc.

Un dispositiu pot ser identificat com a quiosc per qualsevol d'aquests
mètodes (OR):

  1. Cookie de matriculació (`KIOSK_COOKIE_NAME`). Recomanat: independent
     de la xarxa i fàcil de revocar dispositiu a dispositiu.
  2. IP del client a `KIOSK_IP_ALLOWLIST` (admet rangs CIDR).
  3. Header `X-Kiosk-Secret` igual a `KIOSK_SHARED_SECRET` (clients
     programàtics; un navegador normal no envia headers personalitzats).

Si cap mecanisme està configurat, en producció es retorna False; en
desenvolupament es retorna True per facilitar el treball local.
"""
import hashlib
import ipaddress
import secrets as _secrets
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings


# Cookie de matriculació: durada llarga, HttpOnly, SameSite=Strict.
KIOSK_COOKIE_NAME = "visites_kiosk"
KIOSK_COOKIE_MAX_AGE = 5 * 365 * 24 * 3600  # 5 anys


# ── Allowlist d'IPs (suport CIDR) ────────────────────────────────────────

@lru_cache(maxsize=1)
def _parse_allowlist(raw: str) -> tuple[
    frozenset[ipaddress.IPv4Address | ipaddress.IPv6Address],
    tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
]:
    """Separa l'allowlist en IPs exactes i xarxes CIDR.
    Entrades invàlides es descarten silenciosament (no bloquegen l'arrencada
    per evitar caigudes catastròfiques per un typo al .env)."""
    exact: list = []
    cidr: list = []
    for entry in (e.strip() for e in raw.split(",")):
        if not entry:
            continue
        try:
            if "/" in entry:
                cidr.append(ipaddress.ip_network(entry, strict=False))
            else:
                exact.append(ipaddress.ip_address(entry))
        except ValueError:
            continue
    return frozenset(exact), tuple(cidr)


def is_kiosk_ip(client_ip: str) -> bool:
    """True si client_ip està dins de KIOSK_IP_ALLOWLIST (IP exacta o CIDR)."""
    raw = settings.KIOSK_IP_ALLOWLIST or ""
    if not raw.strip():
        return False
    if not client_ip:
        return False
    try:
        ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    exact, networks = _parse_allowlist(raw)
    if ip in exact:
        return True
    return any(ip in net for net in networks)


# ── Cookie de matriculació ──────────────────────────────────────────────

def hash_token(token: str) -> str:
    """SHA-256 hex del token. No usem bcrypt perquè el token ja és
    aleatori d'alta entropia (32+ bytes); un hash criptogràfic és
    suficient i ràpid."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    """Token URL-safe de ~43 caràcters (256 bits d'entropia)."""
    return _secrets.token_urlsafe(32)


async def find_active_device_by_token(
    token: str, db: AsyncSession
):
    """Retorna el KioskDevice actiu amb aquest token, o None."""
    from app.db.models import KioskDevice  # import diferit per evitar cicle
    if not token:
        return None
    digest = hash_token(token)
    result = await db.execute(
        select(KioskDevice).where(
            KioskDevice.token_hash == digest,
            KioskDevice.revoked_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def is_enrolled_kiosk(request: Request, db: AsyncSession) -> bool:
    """True si la petició porta una cookie de quiosc vàlida i no revocada.
    Actualitza last_seen_at / last_seen_ip de la fila corresponent."""
    from app.db.models import KioskDevice  # import diferit
    token = request.cookies.get(KIOSK_COOKIE_NAME, "")
    device = await find_active_device_by_token(token, db)
    if not device:
        return False
    client_ip = request.client.host if request.client else None
    await db.execute(
        update(KioskDevice)
        .where(KioskDevice.id == device.id)
        .values(
            last_seen_at=datetime.now(timezone.utc),
            last_seen_ip=client_ip,
        )
    )
    # No fem commit aquí: això es fa des del handler que ja gestiona
    # la transacció, perquè una cancel·lació downstream pugui revertir-ho
    # tot junt si cal.
    return True


# ── Helpers unificats ───────────────────────────────────────────────────

def _has_valid_shared_secret(request: Request) -> bool:
    if not settings.KIOSK_SHARED_SECRET:
        return False
    provided = request.headers.get("X-Kiosk-Secret", "")
    return _secrets.compare_digest(provided, settings.KIOSK_SHARED_SECRET)


async def is_kiosk_request(request: Request, db: AsyncSession) -> bool:
    """True si la petició s'ha d'acceptar com a quiosc per qualsevol via
    configurada (cookie matriculada / IP / header secret). En dev sense
    cap mecanisme configurat retorna True per facilitar la feina local."""
    # 1) Cookie de matriculació (sense dependència de la xarxa)
    if await is_enrolled_kiosk(request, db):
        return True
    # 2) IP allowlist
    client_ip = request.client.host if request.client else ""
    if settings.KIOSK_IP_ALLOWLIST and is_kiosk_ip(client_ip):
        return True
    # 3) Header secret
    if _has_valid_shared_secret(request):
        return True
    # 4) Dev: si no hi ha cap mecanisme, deixem passar
    if not any([
        settings.KIOSK_IP_ALLOWLIST,
        settings.KIOSK_SHARED_SECRET,
    ]):
        return settings.ENV != "production"
    return False
