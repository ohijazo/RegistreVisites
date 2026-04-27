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
