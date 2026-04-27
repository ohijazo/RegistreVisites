"""Protecció CSRF amb el patró double-submit cookie + camp/header signat.

El middleware (a app/main.py) emet una cookie `csrf_token` a tot client i
exposa el seu valor a `request.state.csrf_token` perquè els templates el
puguin incloure als formularis. En POST/PUT/PATCH/DELETE es valida que el
formulari porti `csrf_token` (o un header X-CSRF-Token) i que coincideixi
amb la cookie. Tots dos valors es signen amb itsdangerous per detectar
manipulacions.

Endpoints exempts: els autenticats per IP+secret de quiosc o webhooks
purament read-only no participen del flux d'usuari amb cookies.
"""
import secrets

from itsdangerous import BadSignature, URLSafeSerializer

from app.config import settings


CSRF_COOKIE = "csrf_token"
CSRF_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"

PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

EXEMPT_PREFIXES: tuple[str, ...] = (
    "/api/lookup-visitor",  # auth pròpia per IP/secret de quiosc
    "/health",
)


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.SECRET_KEY, salt="csrf-token")


def issue_token() -> str:
    """Genera un token CSRF nou signat amb la SECRET_KEY de l'app."""
    raw = secrets.token_urlsafe(32)
    return _serializer().dumps(raw)


def validate_token(submitted: str | None, cookie: str | None) -> bool:
    """Comprova que el token enviat coincideixi amb el de la cookie i
    que tots dos siguin signatures vàlides."""
    if not submitted or not cookie:
        return False
    try:
        a = _serializer().loads(submitted)
        b = _serializer().loads(cookie)
    except BadSignature:
        return False
    return secrets.compare_digest(str(a), str(b))


def is_exempt(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)
