import base64
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.db.models import BlockedVisitor, Department, LegalDocument, Visit
from app.services.crypto import encrypt, hash_id_document, normalize_id_document
from app.services.expected import auto_link_expected_visit, find_active_expected_by_code
from app.services.i18n import t, SUPPORTED_LANGS
from app.services.qr import generate_qr_base64, exit_url
from app.services.rate_limit import limiter


async def _is_blocked_dni(dni: str, db: AsyncSession) -> bool:
    """True si aquest DNI consta a la watchlist amb un bloqueig actiu
    (active=True i, si té data d'expiració, encara no ha passat).
    """
    if not dni or not dni.strip():
        return False
    digest = hash_id_document(dni)
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(BlockedVisitor.id).where(
            BlockedVisitor.id_document_hash == digest,
            BlockedVisitor.active.is_(True),
            or_(
                BlockedVisitor.expires_at.is_(None),
                BlockedVisitor.expires_at > now,
            ),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _has_active_visit_for_dni(dni: str, db: AsyncSession) -> bool:
    """True si ja existeix una visita activa (sense checkout) amb aquest DNI.

    Utilitza el hash HMAC indexat — no desxifra cap registre. Permet
    bloquejar registres duplicats al quiosc quan algú encara consta com
    a present a les instal·lacions.
    """
    if not dni or not dni.strip():
        return False
    digest = hash_id_document(dni)
    result = await db.execute(
        select(Visit.id).where(
            Visit.id_document_hash == digest,
            Visit.checked_out_at.is_(None),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


def _is_kiosk_request(request: Request) -> bool:
    """Comprova si la petició ve d'una tablet de quiosc autoritzada.

    L'autorització és la conjunció de filtres configurats:
      - KIOSK_IP_ALLOWLIST (CSV d'IPs): si està definit, la IP del client
        ha de coincidir.
      - KIOSK_SHARED_SECRET: si està definit, ha d'arribar el header
        X-Kiosk-Secret igual al configurat (constant-time compare).
    Si cap dels dos està configurat, en producció es bloqueja (config.py
    no permet aquesta combinació en prod) i en dev passa.
    """
    if settings.KIOSK_IP_ALLOWLIST:
        allowed = {ip.strip() for ip in settings.KIOSK_IP_ALLOWLIST.split(",") if ip.strip()}
        client_ip = request.client.host if request.client else ""
        if client_ip not in allowed:
            return False
    if settings.KIOSK_SHARED_SECRET:
        provided = request.headers.get("X-Kiosk-Secret", "")
        if not secrets.compare_digest(provided, settings.KIOSK_SHARED_SECRET):
            return False
    if not settings.KIOSK_IP_ALLOWLIST and not settings.KIOSK_SHARED_SECRET:
        return settings.ENV != "production"
    return True

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["lang_attr"] = lambda obj, attr_prefix, lang: getattr(obj, f"{attr_prefix}{lang}", getattr(obj, f"{attr_prefix}ca", ""))


def _lang_context(lang: str) -> dict:
    return {
        "lang": lang,
        "t": lambda key, **kw: t(lang, key, **kw),
        "settings": settings,
    }


@router.get("/qr/{access_code}.png")
async def public_qr(
    access_code: str,
    db: AsyncSession = Depends(get_db),
):
    """QR PNG públic per a un codi d'accés vàlid. Endpoint sense
    autenticació perquè els clients d'email (Gmail/Outlook) puguin
    carregar la imatge des del correu HTML. El propi codi actua com
    a "secret" — qualsevol que el conegui ja pot fer pre-registre,
    així que servir-ne el QR no afegeix cap exposició addicional.
    Retornem 404 si el codi no existeix.
    """
    import base64 as _b64
    import io
    import qrcode
    from fastapi.responses import Response as _Response

    # Validar que el codi existeixi (qualsevol estat — la prevista pot
    # estar 'arrived'/'cancelled' i el visitant podria voler veure el
    # seu codi igualment fins que es purgui).
    from app.db.models import ExpectedVisit as _ExpectedVisit
    code = (access_code or "").strip().upper()
    if not code:
        return _Response(status_code=404)
    result = await db.execute(
        select(_ExpectedVisit.id).where(_ExpectedVisit.access_code == code).limit(1)
    )
    if result.scalar_one_or_none() is None:
        return _Response(status_code=404)

    base_url = settings.BASE_URL.rstrip("/")
    url = f"{base_url}/ca/code/{code}"
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return _Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


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


@router.get("/{lang}/code", response_class=HTMLResponse)
async def code_input_page(lang: str, request: Request):
    """Pantalla on el visitant introdueix manualment el codi d'accés."""
    if lang not in SUPPORTED_LANGS:
        return RedirectResponse("/ca/", status_code=302)
    ctx = _lang_context(lang)
    ctx["error"] = None
    return templates.TemplateResponse(request, "visitor/code.html", ctx)


@router.post("/{lang}/code")
@limiter.limit("10/minute")
async def code_input_submit(
    lang: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    access_code: str = Form(""),
):
    if lang not in SUPPORTED_LANGS:
        return RedirectResponse("/ca/", status_code=302)
    code = (access_code or "").strip().upper().replace("-", "").replace(" ", "")
    if not code:
        ctx = _lang_context(lang)
        ctx["error"] = t(lang, "code_required")
        return templates.TemplateResponse(request, "visitor/code.html", ctx)

    expected = await find_active_expected_by_code(code, db)
    if not expected:
        ctx = _lang_context(lang)
        ctx["error"] = t(lang, "code_invalid")
        return templates.TemplateResponse(request, "visitor/code.html", ctx)

    return RedirectResponse(f"/{lang}/code/{code}", status_code=302)


@router.get("/{lang}/code/{access_code}")
async def code_apply(
    lang: str,
    access_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Aplica el codi: prefila la sessió amb les dades de la prevista i
    redirigeix al formulari per omplir el que falta (típicament el DNI).
    """
    if lang not in SUPPORTED_LANGS:
        return RedirectResponse("/ca/", status_code=302)

    expected = await find_active_expected_by_code(access_code, db)
    if not expected:
        ctx = _lang_context(lang)
        ctx["error"] = t(lang, "code_invalid")
        return templates.TemplateResponse(request, "visitor/code.html", ctx)

    # Prefila la sessió: el flux normal de /{lang}/register llegirà el draft
    # i mostrarà els camps preomplerts. L'usuari només omple el DNI (i pot
    # corregir res si cal).
    request.session["visit_draft"] = {
        "first_name": expected.visitor_first_name or "",
        "last_name": expected.visitor_last_name or "",
        "company": (expected.visitor_company or "").upper(),
        "id_document": "",
        "department_id": str(expected.department_id) if expected.department_id else "",
        "visit_reason": expected.visit_reason or "",
        "phone": expected.visitor_phone or "",
    }
    return RedirectResponse(f"/{lang}/register", status_code=302)


@router.get("/{lang}/group", response_class=HTMLResponse)
async def group_form(
    lang: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if lang not in SUPPORTED_LANGS:
        return RedirectResponse("/ca/", status_code=302)

    dept_result = await db.execute(
        select(Department).where(Department.active.is_(True)).order_by(Department.order)
    )
    departments = dept_result.scalars().all()

    ctx = _lang_context(lang)
    ctx["departments"] = departments
    ctx["error"] = None
    return templates.TemplateResponse(request, "visitor/group.html", ctx)


@router.post("/{lang}/group")
async def submit_group(
    lang: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if lang not in SUPPORTED_LANGS:
        return RedirectResponse("/ca/", status_code=302)

    form = await request.form()
    company = (form.get("company") or "").strip().upper()
    department_id = (form.get("department_id") or "").strip()
    visit_reason = (form.get("visit_reason") or "").strip()
    names = form.getlist("members_name[]")
    dnis = form.getlist("members_dni[]")

    if not company or not department_id or not visit_reason:
        dept_result = await db.execute(
            select(Department).where(Department.active.is_(True)).order_by(Department.order)
        )
        ctx = _lang_context(lang)
        ctx["departments"] = dept_result.scalars().all()
        ctx["error"] = t(lang, "error_required")
        return templates.TemplateResponse(request, "visitor/group.html", ctx)

    # Obtenir document legal actiu
    legal_result = await db.execute(
        select(LegalDocument).where(LegalDocument.active.is_(True))
    )
    legal_doc = legal_result.scalar_one_or_none()

    # Validar que cap dels DNIs sigui a la watchlist o ja tingui visita
    # activa. Bloquejar tot el grup en qualsevol dels casos (no creem
    # visites parcials).
    blocked_members: list[str] = []
    duplicates: list[str] = []
    for i in range(len(names)):
        name = (names[i] if i < len(names) else "").strip()
        dni = (dnis[i] if i < len(dnis) else "").strip().upper()
        if not name or not dni:
            continue
        if await _is_blocked_dni(dni, db):
            blocked_members.append(name)
        elif await _has_active_visit_for_dni(dni, db):
            duplicates.append(name)

    if blocked_members:
        dept_result = await db.execute(
            select(Department).where(Department.active.is_(True)).order_by(Department.order)
        )
        ctx = _lang_context(lang)
        ctx["departments"] = dept_result.scalars().all()
        # Missatge genèric (no revelem el motiu del bloqueig).
        ctx["error"] = t(lang, "error_dni_blocked")
        return templates.TemplateResponse(request, "visitor/group.html", ctx)

    if duplicates:
        dept_result = await db.execute(
            select(Department).where(Department.active.is_(True)).order_by(Department.order)
        )
        ctx = _lang_context(lang)
        ctx["departments"] = dept_result.scalars().all()
        ctx["error"] = (
            t(lang, "error_dni_already_active")
            + " (" + ", ".join(duplicates) + ")"
        )
        return templates.TemplateResponse(request, "visitor/group.html", ctx)

    created_visits: list[Visit] = []
    for i in range(len(names)):
        name = (names[i] if i < len(names) else "").strip()
        dni = (dnis[i] if i < len(dnis) else "").strip().upper()
        if not name or not dni:
            continue

        # Separar nom i cognoms
        parts = name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        enc, iv = encrypt(dni)
        exit_token = secrets.token_urlsafe(32)
        exit_pin = f"{secrets.randbelow(1_000_000):06d}"

        visit = Visit(
            first_name=first_name,
            last_name=last_name,
            company=company,
            id_document_enc=enc,
            id_document_iv=iv,
            id_document_hash=hash_id_document(dni),
            department_id=department_id,
            visit_reason=visit_reason,
            language=lang,
            legal_document_id=legal_doc.id if legal_doc else None,
            accepted_at=datetime.now(timezone.utc),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            exit_token=exit_token,
            exit_pin=exit_pin,
        )
        db.add(visit)
        created_visits.append(visit)

    if not created_visits:
        dept_result = await db.execute(
            select(Department).where(Department.active.is_(True)).order_by(Department.order)
        )
        ctx = _lang_context(lang)
        ctx["departments"] = dept_result.scalars().all()
        ctx["error"] = t(lang, "error_required")
        return templates.TemplateResponse(request, "visitor/group.html", ctx)

    # Flush perquè cada Visit tingui id assignat abans del matching, i
    # aleshores intentar vincular-los amb visites previstes del dia.
    await db.flush()
    for v in created_visits:
        await auto_link_expected_visit(v, db)
    await db.commit()
    created = len(created_visits)

    ctx = _lang_context(lang)
    ctx["count"] = created
    ctx["kiosk_reset_seconds"] = settings.KIOSK_CONFIRM_SECONDS
    return templates.TemplateResponse(request, "visitor/group_done.html", ctx)


@router.get("/{lang}/checkout", response_class=HTMLResponse)
async def checkout_lang(lang: str, request: Request):
    if lang not in SUPPORTED_LANGS:
        return RedirectResponse("/ca/", status_code=302)
    request.session["checkout_lang"] = lang
    return RedirectResponse("/checkout", status_code=302)


@router.post("/api/lookup-visitor")
@limiter.limit("20/minute;200/hour")
async def lookup_visitor(
    request: Request,
    id_document: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Buscar si un DNI ja ha visitat abans i retornar les dades.

    Restringit a tablets de quiosc (IP allowlist + header secret). Cerca per
    HMAC-SHA256 indexat — no desxifra cap registre.
    """
    if not _is_kiosk_request(request):
        # 404 dissimulat — no revelar l'existència de l'endpoint.
        raise HTTPException(status_code=404)

    needle = normalize_id_document(id_document)
    if len(needle) < 4:
        return {"found": False}

    digest = hash_id_document(needle)

    result = await db.execute(
        select(Visit)
        .where(Visit.id_document_hash == digest)
        .order_by(Visit.checked_in_at.desc())
        .limit(1)
    )
    visit = result.scalar_one_or_none()
    if not visit:
        return {"found": False}

    return {
        "found": True,
        "first_name": visit.first_name,
        "last_name": visit.last_name,
        "company": visit.company,
        "phone": visit.phone or "",
    }


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

    # Comprovar la watchlist: si el DNI consta com a bloquejat, retornem
    # el mateix missatge genèric "dirigiu-vos a recepció" sense revelar
    # cap detall (ni que existeix watchlist, ni el motiu).
    if "id_document" not in errors:
        if await _is_blocked_dni(id_document, db):
            errors["id_document"] = t(lang, "error_dni_blocked")
            # Audit (sense PII): només prefix del hash i ip.
            from app.db.models import AuditLog
            import json as _json
            db.add(AuditLog(
                admin_id=None,
                visit_id=None,
                action="blocked_attempt",
                ip_address=request.client.host if request.client else None,
                detail=_json.dumps({
                    "digest_prefix": hash_id_document(id_document)[:12],
                    "lang": lang,
                }),
            ))
            await db.commit()

    # Bloquejar registres duplicats: si ja hi ha una visita activa amb
    # aquest DNI, no permetem crear-ne una altra fins que no es registri
    # la sortida (manualment des de recepció o pel mateix visitant).
    if "id_document" not in errors:
        if await _has_active_visit_for_dni(id_document, db):
            errors["id_document"] = t(lang, "error_dni_already_active")

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

    # Si no hi ha cap document legal actiu, no podem demanar consentiment.
    # Mostrem la pàgina d'indisponibilitat amb missatge clar en lloc de
    # deixar que la plantilla peti o que el flux acabi en error 503.
    if not legal_doc:
        ctx = _lang_context(lang)
        ctx["error"] = t(lang, "error_system_unavailable")
        return templates.TemplateResponse(request, "visitor/unavailable.html", ctx)

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
    if signature and signature.startswith("data:image/") and ";base64," in signature:
        try:
            raw = base64.b64decode(signature.split(",", 1)[1])
            if len(raw) > 2_000_000:  # Màx 2MB
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

    # Safety net per a la watchlist: el bloqueig pot haver-se afegit
    # mentre l'usuari estava al pas legal.
    if await _is_blocked_dni(session_data["id_document"], db):
        request.session.pop("visit_draft", None)
        result = await db.execute(
            select(Department).where(Department.active.is_(True)).order_by(Department.order)
        )
        departments = result.scalars().all()
        ctx = _lang_context(lang)
        ctx["departments"] = departments
        ctx["errors"] = {"id_document": t(lang, "error_dni_blocked")}
        ctx["form_data"] = session_data
        return templates.TemplateResponse(request, "visitor/form.html", ctx)

    # Safety net: si entremig algú s'ha registrat amb el mateix DNI i
    # encara no ha sortit, no permetem crear-ne un altre.
    if await _has_active_visit_for_dni(session_data["id_document"], db):
        # Tornar al formulari amb l'error perquè el visitant pugui editar
        # el camp; netegem el draft només d'aquest camp i l'error.
        request.session.pop("visit_draft", None)
        result = await db.execute(
            select(Department).where(Department.active.is_(True)).order_by(Department.order)
        )
        departments = result.scalars().all()
        ctx = _lang_context(lang)
        ctx["departments"] = departments
        ctx["errors"] = {"id_document": t(lang, "error_dni_already_active")}
        ctx["form_data"] = session_data
        return templates.TemplateResponse(request, "visitor/form.html", ctx)

    # Xifrar DNI i precalcular el hash per a cerca
    enc, iv = encrypt(session_data["id_document"])
    id_hash = hash_id_document(session_data["id_document"])

    # Obtenir document legal actiu
    result = await db.execute(
        select(LegalDocument).where(LegalDocument.active.is_(True))
    )
    legal_doc = result.scalar_one_or_none()
    if not legal_doc:
        # Mateix tractament que el GET: mostrar pàgina d'indisponibilitat
        # en comptes de redirigir a un flux que tornarà a fallar.
        ctx = _lang_context(lang)
        ctx["error"] = t(lang, "error_system_unavailable")
        return templates.TemplateResponse(request, "visitor/unavailable.html", ctx)

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
        id_document_hash=id_hash,
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

    # Auto-vincle amb visita prevista del dia (nom + empresa)
    await auto_link_expected_visit(visit, db)
    await db.commit()

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
