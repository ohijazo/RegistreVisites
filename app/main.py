import traceback

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, PlainTextResponse
from starlette.middleware.sessions import SessionMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.routers import visitor, checkout, admin
from app.services.rate_limit import limiter

app = FastAPI(
    title="Registre de Visites",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
    debug=settings.DEBUG,
)

# Middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="visites_session",
    max_age=1800,
    same_site="strict",
    https_only=settings.ENV == "production",
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers (admin i checkout primer, visitor al final perquè /{lang}/ no capturi /admin/ ni /checkout/)
app.include_router(admin.router)
app.include_router(checkout.router)
app.include_router(visitor.router)


@app.get("/")
async def root(request: Request):
    accept_lang = request.headers.get("accept-language", "ca")
    for lang in ["ca", "es", "fr", "en"]:
        if lang in accept_lang:
            return RedirectResponse(f"/{lang}/", status_code=302)
    return RedirectResponse("/ca/", status_code=302)
