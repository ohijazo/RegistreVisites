from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Visit
from app.services.crypto import decrypt
from app.services.i18n import t, DEFAULT_LANG

router = APIRouter(prefix="/checkout")
templates = Jinja2Templates(directory="app/templates")


def _get_lang(request: Request) -> str:
    return request.session.get("checkout_lang", DEFAULT_LANG)


def _ctx(request: Request, error=None):
    lang = _get_lang(request)
    return {"t": lambda key, **kw: t(lang, key, **kw), "lang": lang, "error": error}


@router.get("", response_class=HTMLResponse)
async def checkout_page(request: Request):
    return templates.TemplateResponse(request, "checkout/scan.html", _ctx(request))


@router.get("/done", response_class=HTMLResponse)
async def checkout_done(request: Request):
    return templates.TemplateResponse(request, "checkout/done.html", _ctx(request))


@router.post("/dni")
async def checkout_dni(
    request: Request,
    id_document: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Visit)
        .where(Visit.checked_out_at.is_(None))
        .order_by(Visit.checked_in_at.desc())
    )
    active_visits = result.scalars().all()

    needle = id_document.strip().upper().replace(" ", "")
    matches = []
    for visit in active_visits:
        try:
            decrypted = decrypt(visit.id_document_enc, visit.id_document_iv)
            if decrypted.upper().replace(" ", "") == needle:
                matches.append(visit)
        except Exception:
            continue

    if not matches:
        lang = _get_lang(request)
        ctx = {"t": lambda key, **kw: t(lang, key, **kw), "lang": lang, "error": t(lang, "checkout_not_found")}
        return templates.TemplateResponse(request, "checkout/scan.html", ctx)

    # Tancar la visita més recent (primera de la llista, ordenada DESC)
    found = matches[0]
    found.checked_out_at = datetime.now(timezone.utc)
    found.checkout_method = "dni"
    await db.commit()
    return RedirectResponse("/checkout/done", status_code=302)


@router.get("/{exit_token}")
async def checkout_direct(
    exit_token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Visit).where(
            Visit.exit_token == exit_token,
            Visit.checked_out_at.is_(None),
        )
    )
    visit = result.scalar_one_or_none()

    if not visit:
        lang = _get_lang(request)
        ctx = {"t": lambda key, **kw: t(lang, key, **kw), "lang": lang, "error": t(lang, "checkout_not_found")}
        return templates.TemplateResponse(request, "checkout/scan.html", ctx)

    visit.checked_out_at = datetime.now(timezone.utc)
    visit.checkout_method = "qr"
    await db.commit()
    return RedirectResponse("/checkout/done", status_code=302)
