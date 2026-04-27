import logging
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.db.database import get_db
from app.routers import visitor, checkout, admin
from app.services.csrf import (
    CSRF_COOKIE, CSRF_FIELD, CSRF_HEADER, PROTECTED_METHODS,
    is_exempt, issue_token, validate_token,
)
from app.services.rate_limit import limiter

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Registre de Visites",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
    debug=settings.DEBUG,
)

# Middleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com "
            "https://unpkg.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com "
            "https://fonts.googleapis.com; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Patró double-submit: cookie + camp/header signats que han de coincidir.

    Validació activa per a POST/PUT/PATCH/DELETE excepte rutes a la llista
    d'exempció. La cookie es refresca per a clients que encara no en tenen.
    """

    async def dispatch(self, request, call_next):
        cookie = request.cookies.get(CSRF_COOKIE)
        path = request.url.path

        if request.method in PROTECTED_METHODS and not is_exempt(path):
            submitted = request.headers.get(CSRF_HEADER)
            if not submitted:
                ct = request.headers.get("content-type", "") or ""
                if ct.startswith("application/x-www-form-urlencoded"):
                    # Llegir el body un cop i re-injectar-lo a request._receive
                    # perquè el handler downstream el pugui consumir.
                    # BaseHTTPMiddleware passa request.receive al downstream, i
                    # _form cached al middleware no es propaga (Request nou).
                    from urllib.parse import parse_qs
                    body_bytes = await request.body()

                    async def replay():
                        return {"type": "http.request", "body": body_bytes, "more_body": False}

                    request._receive = replay
                    parsed = parse_qs(body_bytes.decode("utf-8", errors="ignore"))
                    submitted = (parsed.get(CSRF_FIELD) or [""])[0]
                elif ct.startswith("multipart/form-data"):
                    # Per a multipart cal el header X-CSRF-Token (rar perquè
                    # els forms del projecte són tots application/x-www-form-
                    # urlencoded; els fetch/HTMX que enviïn multipart han
                    # d'incloure el header explícitament).
                    pass
            if not validate_token(submitted, cookie):
                return JSONResponse({"detail": "CSRF token invàlid o absent"}, status_code=403)

        # Assegurar que sempre hi hagi un token al state per als templates
        if not cookie:
            cookie = issue_token()
        request.state.csrf_token = cookie

        response = await call_next(request)

        # Crear la cookie si encara no existia (primera visita o expirada)
        if not request.cookies.get(CSRF_COOKIE):
            response.set_cookie(
                key=CSRF_COOKIE,
                value=cookie,
                httponly=False,  # llegible des de JS per HTMX/fetch
                samesite="strict",
                secure=settings.ENV == "production",
                max_age=8 * 3600,
                path="/",
            )
        return response


app.add_middleware(CSRFMiddleware)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="visites_session",
    max_age=3600,
    same_site="strict",
    https_only=settings.ENV == "production",
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Error page for DB/server errors
_error_html = Path("app/templates/error.html").read_text(encoding="utf-8")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Error: {exc}", exc_info=True)
    # Admin panel: let debug errors through in dev
    if settings.DEBUG and str(request.url.path).startswith("/admin"):
        raise exc
    return HTMLResponse(content=_error_html, status_code=503)


# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers (admin i checkout primer, visitor al final perquè /{lang}/ no capturi /admin/ ni /checkout/)
app.include_router(admin.router)
app.include_router(checkout.router)
app.include_router(visitor.router)


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        return JSONResponse({"status": "error"}, status_code=503)


@app.get("/")
async def root(request: Request):
    accept_lang = request.headers.get("accept-language", "ca")
    for lang in ["ca", "es", "fr", "en"]:
        if lang in accept_lang:
            return RedirectResponse(f"/{lang}/", status_code=302)
    return RedirectResponse("/ca/", status_code=302)
