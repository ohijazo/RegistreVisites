"""Validació de si una petició ve d'un dispositiu de quiosc autoritzat.

L'allowlist accepta tant IPs individuals com rangs CIDR per facilitar la
configuració d'una subxarxa sencera (ex: tota la wifi de recepció).
"""
import ipaddress
from functools import lru_cache

from app.config import settings


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
            # Entrada malformada: la ignorem en lloc de petar.
            continue
    return frozenset(exact), tuple(cidr)


def is_kiosk_ip(client_ip: str) -> bool:
    """True si client_ip està dins de KIOSK_IP_ALLOWLIST (IP o CIDR).

    Quan l'allowlist està buida, en producció es retorna False (cal
    autorització explícita); en altres entorns es retorna True per
    facilitar el desenvolupament.
    """
    raw = settings.KIOSK_IP_ALLOWLIST or ""
    if not raw.strip():
        return settings.ENV != "production"
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
