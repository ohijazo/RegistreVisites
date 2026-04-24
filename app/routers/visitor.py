import base64
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.db.models import Department, LegalDocument, Visit
from app.services.crypto import encrypt
from app.services.i18n import t, SUPPORTED_LANGS
from app.services.qr import generate_qr_base64, exit_url
from app.services.rate_limit import limiter

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["lang_attr"] = lambda obj, attr_prefix, lang: getattr(obj, f"{attr_prefix}{lang}", getattr(obj, f"{attr_prefix}ca", ""))


def _lang_context(lang: str) -> dict:
    return {
        "lang": lang,
        "t": lambda key, **kw: t(lang, key, **kw),
        "settings": settings,
    }


@router.get("/{lang}/", response_class=HTMLResponse)
async def language_page(lang: str, request: Request):
    if lang not in SUPPORTED_LANGS:
        return RedirectResponse("/ca/", status_code=302)
    return templates.TemplateResponse(request, "visitor/language.html", _lang_context(lang))


@router.get("/{lang}/action", response_class=HTMLResponse)
async def action_page(lang: str, request: Request):
    if lang not in SUPPORTED_LANGS:
        return RedirectResponse("/ca/", status_code=302)
    return templates.TemplateResponse(request, "visitor/action.html", _lang_context(lang))


@router.get("/{lang}/checkout", response_class=HTMLResponse)
async def checkout_lang(lang: str, request: Request):
    if lang not in SUPPORTED_LANGS:
        return RedirectResponse("/ca/", status_code=302)
    request.session["checkout_lang"] = lang
    return RedirectResponse("/checkout", status_code=302)


@router.get("/{lang}/register", response_class=HTMLResponse)
async def register_form(
    lang: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if lang not in SUPPORTED_LANGS:
        return RedirectResponse("/ca/", status_code=302)

    # Verificar que hi ha departaments i document legal actiu
    dept_result = await db.execute(
        select(Department).where(Department.active.is_(True)).order_by(Department.order)
    )
    departments = dept_result.scalars().all()

    legal_result = await db.execute(
        select(LegalDocument).where(LegalDocument.active.is_(True))
    )
    legal_doc = legal_result.scalar_one_or_none()

    if not departments or not legal_doc:
        ctx = _lang_context(lang)
        ctx["error"] = t(lang, "error_system_unavailable")
        return templates.TemplateResponse(request, "visitor/unavailable.html", ctx)

    ctx = _lang_context(lang)
    ctx["departments"] = departments
    ctx["errors"] = {}
    ctx["form_data"] = request.session.get("visit_draft", {})
    return templates.TemplateResponse(request, "visitor/form.html", ctx)


@router.post("/{lang}/register")
@limiter.limit("10/minute")
async def submit_register(
    lang: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    first_name: str = Form(""),
    last_name: str = Form(""),
    company: str = Form(""),
    id_document: str = Form(""),
    department_id: str = Form(""),
    visit_reason: str = Form(""),
    phone: str = Form(""),
):
    if lang not in SUPPORTED_LANGS:
        return RedirectResponse("/ca/", status_code=302)

    errors = {}
    if not first_name.strip():
        errors["first_name"] = t(lang, "error_required")
    if not last_name.strip():
        errors["last_name"] = t(lang, "error_required")
    if not company.strip():
        errors["company"] = t(lang, "error_required")
    if not id_document.strip():
        errors["id_document"] = t(lang, "error_required")
    if not department_id.strip():
        errors["department_id"] = t(lang, "error_required")
    if not visit_reason.strip():
        errors["visit_reason"] = t(lang, "error_required")

    form_data = {
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "company": company.strip().upper(),
        "id_document": id_document.strip().upper(),
        "department_id": department_id,
        "visit_reason": visit_reason.strip(),
        "phone": phone.strip() if phone else "",
    }

    if errors:
        result = await db.execute(
            select(Department).where(Department.active.is_(True)).order_by(Department.order)
        )
        departments = result.scalars().all()
        ctx = _lang_context(lang)
        ctx["departments"] = departments
        ctx["errors"] = errors
        ctx["form_data"] = form_data
        return templates.TemplateResponse(request, "visitor/form.html", ctx)

    # Guardar a sessió
    request.session["visit_draft"] = form_data
    return RedirectResponse(f"/{lang}/legal", status_code=302)


@router.get("/{lang}/legal", response_class=HTMLResponse)
async def legal_page(
    lang: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if lang not in SUPPORTED_LANGS:
        return RedirectResponse("/ca/", status_code=302)

    if "visit_draft" not in request.session:
        return RedirectResponse(f"/{lang}/", status_code=302)

    result = await db.execute(
        select(LegalDocument).where(LegalDocument.active.is_(True))
    )
    legal_doc = result.scalar_one_or_none()

    ctx = _lang_context(lang)
    ctx["legal_doc"] = legal_doc
    ctx["error"] = None
    return templates.TemplateResponse(request, "visitor/legal.html", ctx)


@router.post("/{lang}/legal")
async def submit_legal(
    lang: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    check_rules: str = Form(None),
    check_rgpd: str = Form(None),
    signature: str = Form(None),
):
    if lang not in SUPPORTED_LANGS:
        return RedirectResponse("/ca/", status_code=302)

    session_data = request.session.get("visit_draft")
    if not session_data:
        return RedirectResponse(f"/{lang}/", status_code=302)

    # Validar checkboxes i signatura
    has_error = False
    error_msg = None

    if not check_rules or not check_rgpd:
        has_error = True
        error_msg = t(lang, "legal_both_required")

    # Processar signatura
    signature_bytes = None
    if signature and signature.startswith("data:image/png;base64,"):
        try:
            raw = base64.b64decode(signature.split(",", 1)[1])
            if len(raw) > 500_000:  # Màx 500KB
                has_error = True
                error_msg = t(lang, "error_generic")
            else:
                signature_bytes = raw
        except Exception:
            pass

    if not signature_bytes:
        has_error = True
        error_msg = error_msg or t(lang, "legal_signature_required")

    if has_error:
        result = await db.execute(
            select(LegalDocument).where(LegalDocument.active.is_(True))
        )
        legal_doc = result.scalar_one_or_none()
        ctx = _lang_context(lang)
        ctx["legal_doc"] = legal_doc
        ctx["error"] = error_msg
        return templates.TemplateResponse(request, "visitor/legal.html", ctx)

    # Xifrar DNI
    enc, iv = encrypt(session_data["id_document"])

    # Obtenir document legal actiu
    result = await db.execute(
        select(LegalDocument).where(LegalDocument.active.is_(True))
    )
    legal_doc = result.scalar_one_or_none()
    if not legal_doc:
        return RedirectResponse(f"/{lang}/register", status_code=302)

    # Generar tokens de sortida
    exit_token = secrets.token_urlsafe(32)
    exit_pin = f"{secrets.randbelow(1_000_000):06d}"

    # Crear visita
    visit = Visit(
        first_name=session_data["first_name"],
        last_name=session_data["last_name"],
        company=session_data["company"],
        id_document_enc=enc,
        id_document_iv=iv,
        phone=session_data.get("phone") or None,
        department_id=session_data["department_id"],
        visit_reason=session_data["visit_reason"],
        language=lang,
        legal_document_id=legal_doc.id if legal_doc else None,
        accepted_at=datetime.now(timezone.utc),
        signature=signature_bytes,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        exit_token=exit_token,
        exit_pin=exit_pin,
    )
    db.add(visit)
    await db.commit()
    await db.refresh(visit)

    # Netejar sessió
    request.session.pop("visit_draft", None)
    return RedirectResponse(f"/{lang}/confirmation/{visit.id}", status_code=302)


@router.get("/{lang}/confirmation/{visit_id}", response_class=HTMLResponse)
async def confirmation_page(
    lang: str,
    visit_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if lang not in SUPPORTED_LANGS:
        return RedirectResponse("/ca/", status_code=302)

    result = await db.execute(select(Visit).where(Visit.id == visit_id))
    visit = result.scalar_one_or_none()
    if not visit:
        return RedirectResponse(f"/{lang}/", status_code=302)

    qr_data = exit_url(visit.exit_token)
    qr_b64 = generate_qr_base64(qr_data)

    ctx = _lang_context(lang)
    ctx["visit"] = visit
    ctx["qr_b64"] = qr_b64
    ctx["kiosk_reset_seconds"] = settings.KIOSK_CONFIRM_SECONDS
    return templates.TemplateResponse(request, "visitor/confirmation.html", ctx)
