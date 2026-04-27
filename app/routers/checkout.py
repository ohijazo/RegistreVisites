import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.db.models import Visit, AuditLog
from app.services.crypto import hash_id_document, normalize_id_document
from app.services.i18n import t, DEFAULT_LANG
from app.services.rate_limit import limiter

router = APIRouter(prefix="/checkout")
templates = Jinja2Templates(directory="app/templates")


def _get_lang(request: Request) -> str:
    return request.session.get("checkout_lang", DEFAULT_LANG)


def _ctx(request: Request, error=None):
    lang = _get_lang(request)
    return {"t": lambda key, **kw: t(lang, key, **kw), "lang": lang, "error": error}


def _is_kiosk_ip(request: Request) -> bool:
    """True si la IP del client està a KIOSK_IP_ALLOWLIST. En dev, sense
    allowlist configurada, es tracta qualsevol client com a quiosc."""
    if not settings.KIOSK_IP_ALLOWLIST:
        return settings.ENV != "production"
    allowed = {ip.strip() for ip in settings.KIOSK_IP_ALLOWLIST.split(",") if ip.strip()}
    client_ip = request.client.host if request.client else ""
    return client_ip in allowed


async def _audit(
    db: AsyncSession,
    request: Request,
    action: str,
    visit_id=None,
    detail: dict | None = None,
) -> None:
    db.add(AuditLog(
        admin_id=None,
        visit_id=visit_id,
        action=action,
        ip_address=request.client.host if request.client else None,
        detail=json.dumps(detail or {}),
    ))


@router.get("", response_class=HTMLResponse)
async def checkout_page(request: Request):
    return templates.TemplateResponse(request, "checkout/scan.html", _ctx(request))


@router.get("/done", response_class=HTMLResponse)
async def checkout_done(request: Request):
    return templates.TemplateResponse(request, "checkout/done.html", _ctx(request))


@router.post("/dni")
@limiter.limit("10/minute")
async def checkout_dni(
    request: Request,
    id_document: str = Form(...),
    exit_pin: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Sortida via DNI.

    Acceptat si:
      - La petició ve d'una IP de quiosc (KIOSK_IP_ALLOWLIST), O bé
      - El visitant proporciona DNI + PIN correcte (segon factor).
    Cerca indexada per id_document_hash, no desxifra cap registre.
    """
    needle = normalize_id_document(id_document)
    if not needle:
        await _audit(db, request, "checkout_dni_failed", detail={"reason": "empty"})
        await db.commit()
        return templates.TemplateResponse(request, "checkout/scan.html",
            _ctx(request, error=t(_get_lang(request), "checkout_not_found")))

    digest = hash_id_document(needle)

    result = await db.execute(
        select(Visit)
        .where(
            Visit.checked_out_at.is_(None),
            Visit.id_document_hash == digest,
        )
        .order_by(Visit.checked_in_at.desc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    visit = result.scalar_one_or_none()

    is_kiosk = _is_kiosk_ip(request)
    pin_ok = bool(
        visit
        and exit_pin
        and visit.exit_pin
        and secrets.compare_digest(visit.exit_pin, exit_pin.strip())
    )

    if not visit or not (is_kiosk or pin_ok):
        reason = "no_match" if not visit else ("missing_pin" if not pin_ok else "not_kiosk")
        await _audit(
            db, request, "checkout_dni_failed",
            visit_id=visit.id if visit else None,
            detail={"reason": reason},
        )
        await db.commit()
        return templates.TemplateResponse(request, "checkout/scan.html",
            _ctx(request, error=t(_get_lang(request), "checkout_not_found")))

    visit.checked_out_at = datetime.now(timezone.utc)
    visit.checkout_method = "dni" if is_kiosk else "pin"
    await _audit(
        db, request, "checkout_dni_success",
        visit_id=visit.id,
        detail={"method": visit.checkout_method},
    )
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
        await _audit(
            db, request, "checkout_qr_failed",
            detail={"token_prefix": exit_token[:8]},
        )
        await db.commit()
        return templates.TemplateResponse(request, "checkout/scan.html",
            _ctx(request, error=t(_get_lang(request), "checkout_not_found")))

    visit.checked_out_at = datetime.now(timezone.utc)
    visit.checkout_method = "qr"
    await _audit(db, request, "checkout_qr_success", visit_id=visit.id)
    await db.commit()
    return RedirectResponse("/checkout/done", status_code=302)
