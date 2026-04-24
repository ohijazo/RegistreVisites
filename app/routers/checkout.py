from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Visit
from app.services.crypto import decrypt
from app.services.i18n import t

router = APIRouter(prefix="/checkout")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def checkout_page(request: Request):
    ctx = {"t": lambda key, **kw: t("ca", key, **kw), "error": None}
    return templates.TemplateResponse(request, "checkout/scan.html", ctx)


@router.get("/done", response_class=HTMLResponse)
async def checkout_done(request: Request):
    ctx = {"t": lambda key, **kw: t("ca", key, **kw)}
    return templates.TemplateResponse(request, "checkout/done.html", ctx)


@router.post("/qr")
async def checkout_qr(
    request: Request,
    exit_token: str = Form(...),
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
        ctx = {"t": lambda key, **kw: t("ca", key, **kw), "error": t("ca", "checkout_not_found")}
        return templates.TemplateResponse(request, "checkout/scan.html", ctx)

    visit.checked_out_at = datetime.now(timezone.utc)
    visit.checkout_method = "qr"
    await db.commit()
    return RedirectResponse("/checkout/done", status_code=302)


@router.post("/pin")
async def checkout_pin(
    request: Request,
    exit_pin: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Visit).where(
            Visit.exit_pin == exit_pin,
            Visit.checked_out_at.is_(None),
        )
    )
    visit = result.scalar_one_or_none()

    if not visit:
        ctx = {"t": lambda key, **kw: t("ca", key, **kw), "error": t("ca", "checkout_not_found")}
        return templates.TemplateResponse(request, "checkout/scan.html", ctx)

    visit.checked_out_at = datetime.now(timezone.utc)
    visit.checkout_method = "pin"
    await db.commit()
    return RedirectResponse("/checkout/done", status_code=302)


@router.post("/dni")
async def checkout_dni(
    request: Request,
    id_document: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Buscar entre visites actives desxifrant el DNI
    result = await db.execute(
        select(Visit).where(Visit.checked_out_at.is_(None))
    )
    active_visits = result.scalars().all()

    needle = id_document.strip().upper().replace(" ", "")
    found = None
    for visit in active_visits:
        try:
            decrypted = decrypt(visit.id_document_enc, visit.id_document_iv)
            if decrypted.upper().replace(" ", "") == needle:
                found = visit
                break
        except Exception:
            continue

    if not found:
        ctx = {"t": lambda key, **kw: t("ca", key, **kw), "error": t("ca", "checkout_not_found")}
        return templates.TemplateResponse(request, "checkout/scan.html", ctx)

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
        ctx = {"t": lambda key, **kw: t("ca", key, **kw), "error": t("ca", "checkout_not_found")}
        return templates.TemplateResponse(request, "checkout/scan.html", ctx)

    visit.checked_out_at = datetime.now(timezone.utc)
    visit.checkout_method = "qr"
    await db.commit()
    return RedirectResponse("/checkout/done", status_code=302)
