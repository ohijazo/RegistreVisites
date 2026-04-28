import base64
import hashlib
import json
from datetime import datetime, timezone, timedelta, date

import bleach
from fastapi import APIRouter, Request, Depends, Form, Query, Response, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, and_, or_, text, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from jose import jwt

from app.services.auth import hash_password, verify_password
from app.services.rate_limit import limiter

from app.config import settings
from app.db.database import get_db
from app.db.models import AdminUser, BlockedVisitor, Visit, Department, LegalDocument, AuditLog, ExpectedVisit
from app.dependencies import get_current_admin, require_role
from app.services.crypto import decrypt, hash_id_document, normalize_id_document
from app.services.email import send_email, smtp_configured
from app.services.expected import (
    find_matching_visit_for_expected,
    generate_unique_access_code,
)
from app.services.export import visits_to_excel, visits_to_csv

MIN_ADMIN_PASSWORD_LEN = 12

LEGAL_ALLOWED_TAGS = ["p", "br", "strong", "em", "u", "ol", "ul", "li",
                      "h2", "h3", "h4", "a", "span"]
LEGAL_ALLOWED_ATTRS = {"a": ["href", "title", "rel"]}


def _clean_legal(html: str) -> str:
    """Saneja HTML del contingut legal: només etiquetes inofensives."""
    return bleach.clean(html or "", tags=LEGAL_ALLOWED_TAGS,
                        attributes=LEGAL_ALLOWED_ATTRS, strip=True)

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["b64encode"] = lambda data: base64.b64encode(data).decode() if data else ""


# ── Helpers ──────────────────────────────────────────────

async def _get_filtered_visits(
    db: AsyncSession,
    date_from: date | None = None,
    date_to: date | None = None,
    company: str | None = None,
    dept_id: str | None = None,
    name: str | None = None,
    status: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[Visit], int]:
    """Retorna (visites, total_count) amb filtres aplicats."""
    q = select(Visit).options(selectinload(Visit.department))

    filters = []
    if date_from:
        filters.append(Visit.checked_in_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc))
    if date_to:
        filters.append(Visit.checked_in_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
    if company:
        filters.append(Visit.company.ilike(f"%{company}%"))
    if dept_id:
        filters.append(Visit.department_id == dept_id)
    if name:
        filters.append(
            or_(
                Visit.first_name.ilike(f"%{name}%"),
                Visit.last_name.ilike(f"%{name}%"),
            )
        )
    if status == "active":
        filters.append(Visit.checked_out_at.is_(None))
    elif status == "completed":
        filters.append(Visit.checked_out_at.isnot(None))

    if filters:
        q = q.where(and_(*filters))

    # Count total
    count_q = select(func.count(Visit.id))
    if filters:
        count_q = count_q.where(and_(*filters))
    count_result = await db.execute(count_q)
    total = count_result.scalar()

    # Fetch page
    q = q.order_by(Visit.checked_in_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    visits = result.scalars().all()

    return visits, total


def _admin_context(admin: AdminUser) -> dict:
    return {
        "admin": admin,
        "settings": settings,
        "now": datetime.now(timezone.utc),
    }


# ── Ajuda ────────────────────────────────────────────────

@router.get("/help", response_class=HTMLResponse)
async def help_page(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
):
    ctx = _admin_context(admin)
    return templates.TemplateResponse(request, "admin/help.html", ctx)


# ── Audit logs ───────────────────────────────────────────

@router.get("/audit-logs", response_class=HTMLResponse)
async def audit_logs_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
    date_from: str = "",
    date_to: str = "",
    action: str = "",
):
    q = select(AuditLog).options(selectinload(AuditLog.admin)).order_by(AuditLog.created_at.desc())

    filters_list = []
    if date_from:
        filters_list.append(AuditLog.created_at >= datetime.combine(date.fromisoformat(date_from), datetime.min.time(), tzinfo=timezone.utc))
    if date_to:
        filters_list.append(AuditLog.created_at < datetime.combine(date.fromisoformat(date_to) + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
    if action:
        filters_list.append(AuditLog.action == action)
    if filters_list:
        q = q.where(and_(*filters_list))

    result = await db.execute(q.limit(500))
    logs = result.scalars().all()

    ctx = _admin_context(admin)
    ctx["logs"] = logs
    ctx["filters"] = {"date_from": date_from, "date_to": date_to, "action": action}
    return templates.TemplateResponse(request, "admin/audit_logs.html", context=ctx)


# ── Checkout massiu ──────────────────────────────────────

@router.post("/bulk-checkout")
async def bulk_checkout(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist")),
):
    result = await db.execute(
        select(Visit).where(Visit.checked_out_at.is_(None))
    )
    active_visits = result.scalars().all()
    count = len(active_visits)

    for visit in active_visits:
        visit.checked_out_at = datetime.now(timezone.utc)
        visit.checkout_method = "manual"

    audit = AuditLog(
        admin_id=admin.id,
        visit_id=None,
        action="bulk_checkout",
        ip_address=request.client.host if request.client else None,
        detail=json.dumps({"count": count}),
    )
    db.add(audit)
    await db.commit()

    return RedirectResponse("/admin/", status_code=302)


# ── Llista d'evacuació ───────────────────────────────────

@router.get("/evacuation", response_class=HTMLResponse)
async def evacuation_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    result = await db.execute(
        select(Visit)
        .options(selectinload(Visit.department))
        .where(Visit.checked_out_at.is_(None))
        .order_by(Visit.checked_in_at.asc())
    )
    active_visits = result.scalars().all()

    ctx = _admin_context(admin)
    ctx["active_visits"] = active_visits
    return templates.TemplateResponse(request, "admin/evacuation.html", ctx)


# ── Login / Logout ───────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "admin/login.html", context={
        "error": None,
    })


@router.post("/login")
@limiter.limit("5/minute;20/hour")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AdminUser).where(AdminUser.email == email, AdminUser.active.is_(True))
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        # Registrar login fallit
        audit = AuditLog(
            admin_id=user.id if user else None,
            action="failed_login",
            ip_address=request.client.host if request.client else None,
            detail=json.dumps({"email": email}),
        )
        db.add(audit)
        await db.commit()
        return templates.TemplateResponse(request, "admin/login.html", context={
            "error": "Credencials incorrectes.",
        })

    # Actualitzar last_login
    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    # Generar JWT (iat és necessari per a la invalidació via last_logout_at)
    now_utc = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "iat": int(now_utc.timestamp()),
            "exp": now_utc + timedelta(hours=settings.SESSION_HOURS),
        },
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )

    response = RedirectResponse("/admin/", status_code=302)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="strict",
        max_age=settings.SESSION_HOURS * 3600,
        secure=settings.ENV == "production",
    )
    return response


@router.get("/logout")
async def logout(
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    # Marcar el moment del logout per invalidar tots els JWTs emesos abans
    admin.last_logout_at = datetime.now(timezone.utc)
    await db.commit()
    response = RedirectResponse("/admin/login", status_code=302)
    response.delete_cookie("access_token")
    return response


# ── Dashboard ────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    expected_mine: str = "",
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Visites actives
    active_result = await db.execute(
        select(Visit)
        .options(selectinload(Visit.department))
        .where(Visit.checked_out_at.is_(None))
        .order_by(Visit.checked_in_at.asc())
    )
    active_visits = active_result.scalars().all()

    # Stats del dia
    entries_result = await db.execute(
        select(func.count(Visit.id)).where(Visit.checked_in_at >= today_start)
    )
    entries_today = entries_result.scalar()

    exits_result = await db.execute(
        select(func.count(Visit.id)).where(
            Visit.checked_out_at >= today_start,
            Visit.checked_out_at.isnot(None),
        )
    )
    exits_today = exits_result.scalar()

    # Durada mitjana avui (només visites completades)
    avg_result = await db.execute(
        select(
            func.avg(
                func.extract("epoch", Visit.checked_out_at - Visit.checked_in_at) / 60
            )
        ).where(
            Visit.checked_in_at >= today_start,
            Visit.checked_out_at.isnot(None),
        )
    )
    avg_duration = avg_result.scalar()

    # Visitants llargs
    alert_cutoff = now - timedelta(hours=settings.MAX_VISIT_HOURS_ALERT)
    long_stay_count = sum(1 for v in active_visits if v.checked_in_at <= alert_cutoff)

    # Visites previstes per avui: incloem pendents + arribades (arribades
    # surten tatxades com a checklist de progrés). El filtre "Les meves"
    # només s'activa si l'admin té host_alias al perfil.
    today_date = now.date()
    expected_mine_active = bool(expected_mine) and bool(admin.host_alias)
    expected_q = (
        select(ExpectedVisit)
        .options(selectinload(ExpectedVisit.department))
        .where(
            ExpectedVisit.expected_date == today_date,
            ExpectedVisit.status.in_(["pending", "arrived"]),
        )
        .order_by(ExpectedVisit.expected_time.asc().nullslast())
    )
    if expected_mine_active:
        expected_q = expected_q.where(
            ExpectedVisit.host_name.ilike(f"%{admin.host_alias}%")
        )
    expected_today_result = await db.execute(expected_q)
    expected_today = expected_today_result.scalars().all()
    expected_pending_count = sum(1 for e in expected_today if e.status == "pending")
    expected_arrived_count = sum(1 for e in expected_today if e.status == "arrived")

    ctx = _admin_context(admin)
    ctx.update({
        "active_visits": active_visits,
        "active_count": len(active_visits),
        "entries_today": entries_today,
        "exits_today": exits_today,
        "avg_duration": round(avg_duration) if avg_duration else None,
        "max_hours_warn": settings.MAX_VISIT_HOURS_WARN,
        "max_hours_alert": settings.MAX_VISIT_HOURS_ALERT,
        "long_stay_count": long_stay_count,
        "expected_today": expected_today,
        "expected_today_count": len(expected_today),
        "expected_pending_count": expected_pending_count,
        "expected_arrived_count": expected_arrived_count,
        "expected_mine_active": expected_mine_active,
    })
    return templates.TemplateResponse(request, "admin/dashboard.html", context=ctx)


# ── API endpoints per HTMX ──────────────────────────────

@router.get("/api/active-visits", response_class=HTMLResponse)
async def api_active_visits(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    result = await db.execute(
        select(Visit)
        .options(selectinload(Visit.department))
        .where(Visit.checked_out_at.is_(None))
        .order_by(Visit.checked_in_at.asc())
    )
    active_visits = result.scalars().all()

    ctx = _admin_context(admin)
    ctx["active_visits"] = active_visits
    ctx["max_hours_warn"] = settings.MAX_VISIT_HOURS_WARN
    ctx["max_hours_alert"] = settings.MAX_VISIT_HOURS_ALERT
    return templates.TemplateResponse(request, "admin/_active_visits_table.html", context=ctx)


@router.get("/api/stats-cards", response_class=HTMLResponse)
async def api_stats_cards(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    active_result = await db.execute(
        select(func.count(Visit.id)).where(Visit.checked_out_at.is_(None))
    )
    entries_result = await db.execute(
        select(func.count(Visit.id)).where(Visit.checked_in_at >= today_start)
    )
    exits_result = await db.execute(
        select(func.count(Visit.id)).where(
            Visit.checked_out_at >= today_start,
            Visit.checked_out_at.isnot(None),
        )
    )
    avg_result = await db.execute(
        select(
            func.avg(func.extract("epoch", Visit.checked_out_at - Visit.checked_in_at) / 60)
        ).where(
            Visit.checked_in_at >= today_start,
            Visit.checked_out_at.isnot(None),
        )
    )
    avg_duration = avg_result.scalar()

    # Visitants que porten massa hores
    alert_cutoff = now - timedelta(hours=settings.MAX_VISIT_HOURS_ALERT)
    long_stay_result = await db.execute(
        select(func.count(Visit.id)).where(
            Visit.checked_out_at.is_(None),
            Visit.checked_in_at <= alert_cutoff,
        )
    )

    ctx = _admin_context(admin)
    ctx.update({
        "active_count": active_result.scalar(),
        "entries_today": entries_result.scalar(),
        "exits_today": exits_result.scalar(),
        "avg_duration": round(avg_duration) if avg_duration else None,
        "long_stay_count": long_stay_result.scalar(),
        "max_hours_alert": settings.MAX_VISIT_HOURS_ALERT,
    })
    return templates.TemplateResponse(request, "admin/_stats_cards.html", context=ctx)


@router.get("/api/stats")
async def api_stats(
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    active_result = await db.execute(
        select(func.count(Visit.id)).where(Visit.checked_out_at.is_(None))
    )
    entries_result = await db.execute(
        select(func.count(Visit.id)).where(Visit.checked_in_at >= today_start)
    )
    exits_result = await db.execute(
        select(func.count(Visit.id)).where(
            Visit.checked_out_at >= today_start,
            Visit.checked_out_at.isnot(None),
        )
    )
    avg_result = await db.execute(
        select(
            func.avg(func.extract("epoch", Visit.checked_out_at - Visit.checked_in_at) / 60)
        ).where(
            Visit.checked_in_at >= today_start,
            Visit.checked_out_at.isnot(None),
        )
    )

    return {
        "active_now": active_result.scalar(),
        "entries_today": entries_result.scalar(),
        "exits_today": exits_result.scalar(),
        "avg_duration_minutes": round(avg_result.scalar() or 0),
    }


# ── Historial de visites ─────────────────────────────────

@router.get("/visits", response_class=HTMLResponse)
async def visits_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    date_from: str = "",
    date_to: str = "",
    company: str = "",
    dept_id: str = "",
    name: str = "",
    status: str = "",
    page: int = 1,
):
    per_page = 25
    offset = (page - 1) * per_page

    d_from = date.fromisoformat(date_from) if date_from else None
    d_to = date.fromisoformat(date_to) if date_to else None

    visits, total = await _get_filtered_visits(
        db, d_from, d_to, company or None, dept_id or None, name or None, status or None,
        limit=per_page, offset=offset,
    )

    # Departaments per al filtre
    dept_result = await db.execute(
        select(Department).where(Department.active.is_(True)).order_by(Department.order)
    )
    departments = dept_result.scalars().all()

    total_pages = (total + per_page - 1) // per_page

    ctx = _admin_context(admin)
    ctx.update({
        "visits": visits,
        "departments": departments,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "filters": {
            "date_from": date_from,
            "date_to": date_to,
            "company": company or "",
            "dept_id": dept_id or "",
            "name": name or "",
            "status": status or "",
        },
    })
    return templates.TemplateResponse(request, "admin/visits.html", context=ctx)


# ── Impressió i exportació (ABANS de /visits/{visit_id} per evitar conflicte de rutes) ──

@router.get("/visits/print", response_class=HTMLResponse)
async def print_visits(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist")),
    date_from: str = "",
    date_to: str = "",
    company: str = "",
    dept_id: str = "",
    name: str = "",
    status: str = "",
):
    d_from = date.fromisoformat(date_from) if date_from else None
    d_to = date.fromisoformat(date_to) if date_to else None

    visits, _ = await _get_filtered_visits(
        db, d_from, d_to, company or None, dept_id or None, name or None, status or None,
        limit=500, offset=0,
    )

    ctx = _admin_context(admin)
    ctx.update({
        "visits": visits,
        "filters": {
            "date_from": date_from,
            "date_to": date_to,
            "company": company,
            "name": name,
            "status": status,
        },
    })
    return templates.TemplateResponse(request, "admin/visits_print.html", context=ctx)


@router.get("/visits/export")
async def export_visits(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist")),
    date_from: str = "",
    date_to: str = "",
    company: str = "",
    dept_id: str = "",
    name: str = "",
    status: str = "",
    fmt: str = "xlsx",
):
    d_from = date.fromisoformat(date_from) if date_from else None
    d_to = date.fromisoformat(date_to) if date_to else None

    visits, _ = await _get_filtered_visits(
        db, d_from, d_to, company or None, dept_id or None, name or None, status or None,
        limit=10000, offset=0,
    )

    date_range = f"{date_from or 'inici'}_{date_to or 'fi'}"

    if fmt == "csv":
        content = visits_to_csv(visits)
        media_type = "text/csv"
        filename = f"visites_{date_range}.csv"
    else:
        content = visits_to_excel(visits, date_range)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"visites_{date_range}.xlsx"

    return Response(
        content=content.getvalue(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Detall visita ────────────────────────────────────────

@router.get("/visits/{visit_id}", response_class=HTMLResponse)
async def visit_detail(
    visit_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    result = await db.execute(
        select(Visit)
        .options(selectinload(Visit.department), selectinload(Visit.legal_document))
        .where(Visit.id == visit_id)
    )
    visit = result.scalar_one_or_none()
    if not visit:
        return RedirectResponse("/admin/visits", status_code=302)

    # Si hi ha una visita prevista vinculada, la mostrem al detall
    expected_result = await db.execute(
        select(ExpectedVisit).where(ExpectedVisit.visit_id == visit.id)
    )
    expected = expected_result.scalar_one_or_none()

    ctx = _admin_context(admin)
    ctx["visit"] = visit
    ctx["expected"] = expected
    return templates.TemplateResponse(request, "admin/visit_detail.html", context=ctx)


# ── Desxifrar DNI ────────────────────────────────────────

@router.post("/visits/{visit_id}/view-id")
async def view_id_document(
    visit_id: str,
    request: Request,
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    # Verificar contrasenya de l'admin
    if not verify_password(password, admin.password_hash):
        return {"error": "Contrasenya incorrecta."}

    result = await db.execute(select(Visit).where(Visit.id == visit_id))
    visit = result.scalar_one_or_none()
    if not visit:
        return {"error": "Visita no trobada."}

    # Desxifrar
    id_doc = decrypt(visit.id_document_enc, visit.id_document_iv)

    # Log d'auditoria
    audit = AuditLog(
        admin_id=admin.id,
        visit_id=visit.id,
        action="view_id_document",
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    await db.commit()

    return JSONResponse(
        {"id_document": id_doc},
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "Pragma": "no-cache",
        },
    )


# ── Sortida manual ───────────────────────────────────────

@router.post("/visits/{visit_id}/checkout")
async def manual_checkout(
    visit_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist")),
):
    result = await db.execute(
        select(Visit).where(Visit.id == visit_id, Visit.checked_out_at.is_(None))
    )
    visit = result.scalar_one_or_none()
    if not visit:
        return RedirectResponse("/admin/", status_code=302)

    visit.checked_out_at = datetime.now(timezone.utc)
    visit.checkout_method = "manual"

    # Auditoria
    audit = AuditLog(
        admin_id=admin.id,
        visit_id=visit.id,
        action="manual_checkout",
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit)
    await db.commit()

    # Si és HTMX, retornar fragment
    if request.headers.get("HX-Request"):
        return HTMLResponse('<td colspan="7" class="text-center text-gray-400 py-2">Sortida registrada</td>')

    return RedirectResponse("/admin/", status_code=302)


# ── Eliminar visita (RGPD) ───────────────────────────────

@router.post("/visits/{visit_id}/delete")
async def delete_visit(
    visit_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
):
    result = await db.execute(select(Visit).where(Visit.id == visit_id))
    visit = result.scalar_one_or_none()
    if not visit:
        return {"error": "Visita no trobada."}

    # Eliminar audit logs associats a aquesta visita
    await db.execute(
        delete(AuditLog).where(AuditLog.visit_id == visit_id)
    )

    # Auditoria de l'eliminació (visit_id=None perquè la visita s'eliminarà).
    # No persistim PII (nom, cognoms, empresa) per complir el dret d'oblit
    # RGPD: només l'identificador i la marca de temps de l'acció.
    audit = AuditLog(
        admin_id=admin.id,
        visit_id=None,
        action="delete_visit",
        ip_address=request.client.host if request.client else None,
        detail=json.dumps({
            "visit_id": str(visit.id),
            "deleted_at": datetime.now(timezone.utc).isoformat(),
        }),
    )
    db.add(audit)
    await db.delete(visit)
    await db.commit()

    return {"ok": True}


# ── Estadístiques ────────────────────────────────────────

@router.get("/stats", response_class=HTMLResponse)
async def stats_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    date_from: str = "",
    date_to: str = "",
):
    date_from = date.fromisoformat(date_from) if date_from else datetime.now(timezone.utc).replace(day=1).date()
    date_to = date.fromisoformat(date_to) if date_to else datetime.now(timezone.utc).date()

    dt_from = datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
    dt_to = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

    period_filter = and_(Visit.checked_in_at >= dt_from, Visit.checked_in_at < dt_to)

    # Resum del període
    total_result = await db.execute(
        select(func.count(Visit.id)).where(period_filter)
    )
    total_visits = total_result.scalar()

    unique_names_result = await db.execute(
        select(func.count(func.distinct(
            func.concat(Visit.first_name, " ", Visit.last_name)
        ))).where(period_filter)
    )
    unique_visitors = unique_names_result.scalar()

    unique_companies_result = await db.execute(
        select(func.count(func.distinct(Visit.company))).where(period_filter)
    )
    unique_companies = unique_companies_result.scalar()

    avg_duration_result = await db.execute(
        select(
            func.avg(func.extract("epoch", Visit.checked_out_at - Visit.checked_in_at) / 60)
        ).where(period_filter, Visit.checked_out_at.isnot(None))
    )
    avg_duration = avg_duration_result.scalar()

    no_checkout_result = await db.execute(
        select(func.count(Visit.id)).where(period_filter, Visit.checked_out_at.is_(None))
    )
    no_checkout = no_checkout_result.scalar()

    # Visites per dia (per gràfic)
    daily_result = await db.execute(
        select(
            func.date_trunc("day", Visit.checked_in_at).label("day"),
            func.count(Visit.id).label("total"),
        ).where(period_filter)
        .group_by(text("1"))
        .order_by(text("1"))
    )
    daily_data = [{"day": row.day.strftime("%Y-%m-%d"), "total": row.total} for row in daily_result]

    # Visites per departament
    dept_result = await db.execute(
        select(
            Department.name_ca,
            func.count(Visit.id).label("total"),
        ).join(Visit, Visit.department_id == Department.id)
        .where(period_filter)
        .group_by(Department.name_ca)
        .order_by(func.count(Visit.id).desc())
    )
    dept_data = [{"name": row.name_ca, "total": row.total} for row in dept_result]

    # Visites per franja horària
    hourly_result = await db.execute(
        select(
            func.extract("hour", Visit.checked_in_at).label("hour"),
            func.count(Visit.id).label("total"),
        ).where(period_filter)
        .group_by(text("1"))
        .order_by(text("1"))
    )
    hourly_data = [{"hour": int(row.hour), "total": row.total} for row in hourly_result]

    # Top empreses
    top_companies_result = await db.execute(
        select(
            Visit.company,
            func.count(Visit.id).label("total"),
            func.max(Visit.checked_in_at).label("last_visit"),
        ).where(period_filter)
        .group_by(Visit.company)
        .order_by(func.count(Visit.id).desc())
        .limit(10)
    )
    top_companies = [
        {"company": row.company, "total": row.total, "last_visit": row.last_visit}
        for row in top_companies_result
    ]

    # Dades crues per filtratge interactiu (dia, dept, hora, empresa per cada visita).
    # Limitem a 5000 perquè el JSON s'injecta al HTML i es processa al navegador;
    # períodes amb més registres es trunquen i s'avisa l'usuari.
    RAW_VISITS_LIMIT = 5000
    raw_result = await db.execute(
        select(
            func.date_trunc("day", Visit.checked_in_at).label("day"),
            Department.name_ca.label("dept"),
            func.extract("hour", Visit.checked_in_at).label("hour"),
            Visit.company,
            Visit.first_name,
            Visit.last_name,
        ).outerjoin(Department, Visit.department_id == Department.id)
        .where(period_filter)
        .order_by(Visit.checked_in_at)
        .limit(RAW_VISITS_LIMIT + 1)
    )
    raw_rows = list(raw_result)
    raw_visits_truncated = len(raw_rows) > RAW_VISITS_LIMIT
    raw_visits = [
        {
            "day": row.day.strftime("%Y-%m-%d"),
            "dept": row.dept or "—",
            "hour": int(row.hour),
            "company": row.company,
            "name": f"{row.first_name} {row.last_name}",
        }
        for row in raw_rows[:RAW_VISITS_LIMIT]
    ]

    ctx = _admin_context(admin)
    ctx.update({
        "date_from": date_from,
        "date_to": date_to,
        "total_visits": total_visits,
        "unique_visitors": unique_visitors,
        "unique_companies": unique_companies,
        "avg_duration": round(avg_duration) if avg_duration else None,
        "no_checkout": no_checkout,
        "daily_data": json.dumps(daily_data),
        "dept_data": json.dumps(dept_data),
        "hourly_data": json.dumps(hourly_data),
        "top_companies": top_companies,
        "raw_visits": raw_visits,
        "raw_visits_truncated": raw_visits_truncated,
        "raw_visits_limit": RAW_VISITS_LIMIT,
    })
    return templates.TemplateResponse(request, "admin/stats.html", context=ctx)


# ── CRUD Departaments ────────────────────────────────────

@router.get("/departments", response_class=HTMLResponse)
async def departments_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
):
    result = await db.execute(select(Department).order_by(Department.order))
    departments = result.scalars().all()
    ctx = _admin_context(admin)
    ctx["departments"] = departments
    return templates.TemplateResponse(request, "admin/departments.html", context=ctx)


@router.post("/departments")
async def create_department(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
    name_ca: str = Form(...),
    name_es: str = Form(...),
    name_fr: str = Form(...),
    name_en: str = Form(...),
    order: int = Form(0),
):
    dept = Department(
        name_ca=name_ca, name_es=name_es,
        name_fr=name_fr, name_en=name_en,
        order=order,
    )
    db.add(dept)
    await db.commit()
    return RedirectResponse("/admin/departments", status_code=302)


@router.post("/departments/{dept_id}/update")
async def update_department(
    dept_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
    name_ca: str = Form(...),
    name_es: str = Form(...),
    name_fr: str = Form(...),
    name_en: str = Form(...),
    order: int = Form(0),
):
    result = await db.execute(select(Department).where(Department.id == dept_id))
    dept = result.scalar_one_or_none()
    if dept:
        dept.name_ca = name_ca
        dept.name_es = name_es
        dept.name_fr = name_fr
        dept.name_en = name_en
        dept.order = order
        await db.commit()
    return RedirectResponse("/admin/departments", status_code=302)


@router.post("/departments/{dept_id}/delete")
async def delete_department(
    dept_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
):
    result = await db.execute(select(Department).where(Department.id == dept_id))
    dept = result.scalar_one_or_none()
    if dept:
        dept.active = False
        await db.commit()
    return RedirectResponse("/admin/departments", status_code=302)


# ── Textos legals ────────────────────────────────────────

@router.get("/legal", response_class=HTMLResponse)
async def legal_docs_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
):
    result = await db.execute(
        select(LegalDocument).order_by(LegalDocument.created_at.desc())
    )
    docs = result.scalars().all()
    ctx = _admin_context(admin)
    ctx["docs"] = docs
    return templates.TemplateResponse(request, "admin/legal_docs.html", context=ctx)


@router.post("/legal")
async def create_legal_doc(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
    content_ca: str = Form(...),
    content_es: str = Form(...),
    content_fr: str = Form(...),
    content_en: str = Form(...),
):
    content_ca = _clean_legal(content_ca)
    content_es = _clean_legal(content_es)
    content_fr = _clean_legal(content_fr)
    content_en = _clean_legal(content_en)

    content_hash = hashlib.sha256(
        (content_ca + content_es + content_fr + content_en).encode()
    ).hexdigest()

    doc = LegalDocument(
        content_hash=content_hash,
        content_ca=content_ca,
        content_es=content_es,
        content_fr=content_fr,
        content_en=content_en,
        active=False,
    )
    db.add(doc)
    await db.commit()
    return RedirectResponse("/admin/legal", status_code=302)


@router.post("/legal/{doc_id}/activate")
async def activate_legal_doc(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
):
    # Desactivar tots
    all_docs = await db.execute(select(LegalDocument))
    for doc in all_docs.scalars():
        doc.active = False

    # Activar el seleccionat
    result = await db.execute(select(LegalDocument).where(LegalDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc:
        doc.active = True
    await db.commit()
    return RedirectResponse("/admin/legal", status_code=302)


# ── Gestió d'usuaris admin ───────────────────────────────

@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
):
    result = await db.execute(select(AdminUser).order_by(AdminUser.created_at))
    users = result.scalars().all()
    ctx = _admin_context(admin)
    ctx["users"] = users
    return templates.TemplateResponse(request, "admin/users.html", context=ctx)


@router.post("/users")
async def create_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
    email: str = Form(...),
    name: str = Form(...),
    password: str = Form(...),
    role: str = Form("receptionist"),
):
    if len(password) < MIN_ADMIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"La contrasenya ha de tenir com a mínim {MIN_ADMIN_PASSWORD_LEN} caràcters.",
        )
    if role not in ("admin", "receptionist", "viewer"):
        raise HTTPException(status_code=400, detail="Rol invàlid.")
    password_hash = hash_password(password)
    user = AdminUser(
        email=email,
        name=name,
        password_hash=password_hash,
        role=role,
    )
    db.add(user)
    await db.commit()
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/update")
async def update_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
    name: str = Form(...),
    role: str = Form(...),
    active: str = Form("off"),
):
    result = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.name = name
        user.role = role
        user.active = active == "on"
        await db.commit()
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
    password: str = Form(...),
):
    if len(password) < MIN_ADMIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"La contrasenya ha de tenir com a mínim {MIN_ADMIN_PASSWORD_LEN} caràcters.",
        )
    result = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.password_hash = hash_password(password)
        # Forçar logout de totes les sessions actives de l'usuari
        user.last_logout_at = datetime.now(timezone.utc)
        await db.commit()
    return RedirectResponse("/admin/users", status_code=302)


# ── Perfil de l'usuari logat ──────────────────────────────

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    saved: str = "",
):
    ctx = _admin_context(admin)
    ctx["saved"] = saved
    return templates.TemplateResponse(request, "admin/profile.html", ctx)


@router.post("/profile")
async def profile_save(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    host_alias: str = Form(""),
):
    admin.host_alias = (host_alias or "").strip() or None
    await db.commit()
    return RedirectResponse("/admin/profile?saved=1", status_code=302)


# ── Dashboard de salut del sistema ─────────────────────────

@router.get("/health-status", response_class=HTMLResponse)
async def health_status_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
):
    import time
    started = time.monotonic()
    try:
        await db.execute(text("SELECT 1"))
        db_latency_ms = round((time.monotonic() - started) * 1000, 1)
        db_ok = True
    except Exception:
        db_latency_ms = None
        db_ok = False

    now = datetime.now(timezone.utc)
    today = now.date()
    cutoff_24h = now - timedelta(hours=24)

    # Comptadors operatius
    active_visits = (await db.execute(
        select(func.count(Visit.id)).where(Visit.checked_out_at.is_(None))
    )).scalar() or 0
    visits_today = (await db.execute(
        select(func.count(Visit.id)).where(
            Visit.checked_in_at >= datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
        )
    )).scalar() or 0
    expected_pending = (await db.execute(
        select(func.count(ExpectedVisit.id)).where(
            ExpectedVisit.expected_date == today,
            ExpectedVisit.status == "pending",
        )
    )).scalar() or 0
    blocked_active = (await db.execute(
        select(func.count(BlockedVisitor.id)).where(
            BlockedVisitor.active.is_(True),
            or_(BlockedVisitor.expires_at.is_(None), BlockedVisitor.expires_at > now),
        )
    )).scalar() or 0

    # Tendències d'auditoria (24h)
    failed_logins_24h = (await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "failed_login",
            AuditLog.created_at >= cutoff_24h,
        )
    )).scalar() or 0
    blocked_attempts_24h = (await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "blocked_attempt",
            AuditLog.created_at >= cutoff_24h,
        )
    )).scalar() or 0
    view_id_24h = (await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "view_id_document",
            AuditLog.created_at >= cutoff_24h,
        )
    )).scalar() or 0

    # Última execució del cron auto-checkout
    last_auto = (await db.execute(
        select(AuditLog).where(AuditLog.action == "auto_checkout")
        .order_by(AuditLog.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    # Comprovació crítica de configuració (executar abans de pg_class
    # perquè una falla a aquella query pot deixar la transacció en
    # estat 'aborted' i bloquejar totes les consultes posteriors).
    config_warnings = []
    if not settings.JWT_SECRET_KEY or settings.JWT_SECRET_KEY == settings.SECRET_KEY:
        if settings.ENV == "production":
            config_warnings.append("JWT_SECRET_KEY no és diferent de SECRET_KEY (prod).")
    if not settings.LOOKUP_PEPPER and settings.ENV == "production":
        config_warnings.append("LOOKUP_PEPPER no configurada (prod).")
    if not settings.KIOSK_IP_ALLOWLIST and not settings.KIOSK_SHARED_SECRET and settings.ENV == "production":
        config_warnings.append("Cap mecanisme d'autenticació de quiosc configurat (prod).")
    legal_active = (await db.execute(
        select(func.count(LegalDocument.id)).where(LegalDocument.active.is_(True))
    )).scalar() or 0
    if legal_active == 0:
        config_warnings.append("No hi ha cap document legal actiu — el flux del visitant fallarà.")

    # Mides de taula (Postgres específic). Usem només pg_class (sempre
    # accessible). reltuples és una estimació, prou bona per a aquest
    # dashboard. Si igualment falla, rollback per no contaminar la
    # transacció.
    try:
        size_rows = (await db.execute(text(
            "SELECT relname, pg_size_pretty(pg_total_relation_size(C.oid)) AS size, "
            "reltuples::bigint AS rows "
            "FROM pg_class C "
            "JOIN pg_namespace N ON N.oid = C.relnamespace "
            "WHERE relkind='r' AND nspname='public' "
            "ORDER BY pg_total_relation_size(C.oid) DESC LIMIT 10"
        ))).all()
        table_sizes = [{"name": r[0], "size": r[1], "rows": r[2] or 0} for r in size_rows]
    except Exception:
        await db.rollback()
        table_sizes = []

    ctx = _admin_context(admin)
    ctx.update({
        "db_ok": db_ok,
        "db_latency_ms": db_latency_ms,
        "active_visits": active_visits,
        "visits_today": visits_today,
        "expected_pending": expected_pending,
        "blocked_active": blocked_active,
        "failed_logins_24h": failed_logins_24h,
        "blocked_attempts_24h": blocked_attempts_24h,
        "view_id_24h": view_id_24h,
        "last_auto_close": last_auto,
        "table_sizes": table_sizes,
        "config_warnings": config_warnings,
        "smtp_configured": bool(settings.SMTP_HOST),
        "auto_close_after_hours": settings.AUTO_CLOSE_AFTER_HOURS,
        "now": now,
    })
    return templates.TemplateResponse(request, "admin/health_status.html", ctx)


# ── Watchlist (DNIs bloquejats) ───────────────────────────

@router.get("/blocked-visitors", response_class=HTMLResponse)
async def blocked_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
    show: str = Query("active", pattern="^(active|all|expired)$"),
):
    stmt = select(BlockedVisitor).options(selectinload(BlockedVisitor.blocked_by))
    now = datetime.now(timezone.utc)
    if show == "active":
        stmt = stmt.where(
            BlockedVisitor.active.is_(True),
            or_(BlockedVisitor.expires_at.is_(None), BlockedVisitor.expires_at > now),
        )
    elif show == "expired":
        stmt = stmt.where(
            or_(BlockedVisitor.active.is_(False),
                and_(BlockedVisitor.expires_at.isnot(None), BlockedVisitor.expires_at <= now)),
        )
    stmt = stmt.order_by(BlockedVisitor.blocked_at.desc())

    items = (await db.execute(stmt)).scalars().all()

    ctx = _admin_context(admin)
    ctx.update({"items": items, "show": show, "now": now})
    return templates.TemplateResponse(request, "admin/blocked_visitors.html", ctx)


@router.post("/blocked-visitors")
async def blocked_create(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
    id_document: str = Form(...),
    reason: str = Form(...),
    internal_label: str = Form(""),
    expires_at: str = Form(""),
):
    if not id_document.strip() or not reason.strip():
        return RedirectResponse("/admin/blocked-visitors", status_code=302)

    digest = hash_id_document(id_document)
    expires_dt = None
    if expires_at.strip():
        try:
            d = date.fromisoformat(expires_at.strip())
            expires_dt = datetime.combine(d, datetime.max.time(), tzinfo=timezone.utc)
        except ValueError:
            pass

    item = BlockedVisitor(
        id_document_hash=digest,
        reason=reason.strip(),
        internal_label=(internal_label or "").strip() or None,
        blocked_by_id=admin.id,
        expires_at=expires_dt,
        active=True,
    )
    db.add(item)
    db.add(AuditLog(
        admin_id=admin.id,
        visit_id=None,
        action="blocked_visitor_added",
        ip_address=request.client.host if request.client else None,
        detail=json.dumps({
            "digest_prefix": digest[:12],
            "reason": reason.strip()[:200],
            "expires_at": expires_dt.isoformat() if expires_dt else None,
        }),
    ))
    await db.commit()
    return RedirectResponse("/admin/blocked-visitors", status_code=302)


@router.post("/blocked-visitors/{item_id}/deactivate")
async def blocked_deactivate(
    item_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
):
    result = await db.execute(select(BlockedVisitor).where(BlockedVisitor.id == item_id))
    item = result.scalar_one_or_none()
    if item:
        item.active = False
        db.add(AuditLog(
            admin_id=admin.id,
            visit_id=None,
            action="blocked_visitor_deactivated",
            ip_address=request.client.host if request.client else None,
            detail=json.dumps({"blocked_id": str(item.id), "digest_prefix": item.id_document_hash[:12]}),
        ))
        await db.commit()
    return RedirectResponse("/admin/blocked-visitors", status_code=302)


@router.post("/blocked-visitors/{item_id}/delete")
async def blocked_delete(
    item_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
):
    result = await db.execute(select(BlockedVisitor).where(BlockedVisitor.id == item_id))
    item = result.scalar_one_or_none()
    if item:
        db.add(AuditLog(
            admin_id=admin.id,
            visit_id=None,
            action="blocked_visitor_deleted",
            ip_address=request.client.host if request.client else None,
            detail=json.dumps({"digest_prefix": item.id_document_hash[:12]}),
        ))
        await db.delete(item)
        await db.commit()
    return RedirectResponse("/admin/blocked-visitors", status_code=302)


# ── RGPD: cerca per DNI i dret d'oblit ────────────────────

@router.get("/rgpd", response_class=HTMLResponse)
async def rgpd_search_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
    q: str = Query(""),
    anonymized: str = Query(""),
):
    """Cerca visites pel DNI normalitzat (HMAC). Permet exercir
    el dret d'accés (mostrar les visites del visitant) i el dret
    d'oblit (anonimitzar-les) sense haver de tocar SQL.
    """
    visits: list[Visit] = []
    not_found = False
    digest = None
    if q.strip():
        digest = hash_id_document(q)
        result = await db.execute(
            select(Visit)
            .options(selectinload(Visit.department))
            .where(Visit.id_document_hash == digest)
            .order_by(Visit.checked_in_at.desc())
        )
        visits = result.scalars().all()
        not_found = not visits

    ctx = _admin_context(admin)
    ctx.update({
        "q": q.strip(),
        "visits": visits,
        "not_found": not_found,
        "anonymized": anonymized,
        "digest_preview": digest[:12] + "…" if digest else None,
    })
    return templates.TemplateResponse(request, "admin/rgpd.html", ctx)


@router.post("/rgpd/anonymize")
async def rgpd_anonymize(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
    q: str = Form(...),
):
    """Anonimitza totes les visites associades a un DNI.

    L'estratègia és pseudonimització: substituïm les dades personals per
    valors marca aigua i esborrem el ciphertext del DNI. Conservem
    l'estructura (id, dates, departament, durada) per mantenir agregats
    estadístics. Documentat com a alternativa preferent a l'esborrat
    total fins als 5 anys.
    """
    if not q.strip():
        return RedirectResponse("/admin/rgpd", status_code=302)

    digest = hash_id_document(q)
    result = await db.execute(
        select(Visit).where(Visit.id_document_hash == digest)
    )
    visits = result.scalars().all()
    if not visits:
        return RedirectResponse("/admin/rgpd?anonymized=none", status_code=302)

    placeholder = "[ANONIMITZAT]"
    redacted_bytes = b""
    count = 0
    for v in visits:
        v.first_name = placeholder
        v.last_name = ""
        v.company = placeholder
        v.phone = None
        v.id_document_enc = redacted_bytes
        v.id_document_iv = redacted_bytes
        v.id_document_hash = None
        v.signature = None
        v.user_agent = None
        # ip_address es manté per traçabilitat tècnica però el visitant
        # ja no es pot identificar a partir d'aquí.
        count += 1

    db.add(AuditLog(
        admin_id=admin.id,
        visit_id=None,
        action="rgpd_anonymize",
        ip_address=request.client.host if request.client else None,
        detail=json.dumps({
            "visits_affected": count,
            "performed_at": datetime.now(timezone.utc).isoformat(),
            # No conservem el DNI en clar: només el hash truncat com a
            # referència interna per a futures auditories.
            "digest_prefix": digest[:12],
        }),
    ))
    await db.commit()
    return RedirectResponse(f"/admin/rgpd?anonymized={count}", status_code=302)


# ── Visites previstes ────────────────────────────────────

EXPECTED_STATUSES = ("pending", "arrived", "cancelled", "no_show")

# Alias del builtin per usar-lo dins de funcions on `range` és el nom d'un
# paràmetre Query.
range_builtin = range


async def _log_expected_status_change(
    db: AsyncSession,
    request: Request,
    admin: AdminUser,
    item: "ExpectedVisit",
    old_status: str,
    new_status: str,
) -> None:
    """Auditoria centralitzada per als canvis d'estat d'una visita prevista."""
    if old_status == new_status:
        return
    db.add(AuditLog(
        admin_id=admin.id,
        visit_id=None,
        action="expected_status_changed",
        ip_address=request.client.host if request.client else None,
        detail=json.dumps({
            "expected_id": str(item.id),
            "from": old_status,
            "to": new_status,
            "visitor": f"{item.visitor_first_name} {item.visitor_last_name or ''}".strip(),
        }),
    ))


def _parse_date_or(value: str, default):
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return default


def _parse_time_or_none(value: str):
    if not value:
        return None
    try:
        # HTML <input type="time"> sol enviar HH:MM
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        try:
            return datetime.strptime(value, "%H:%M:%S").time()
        except ValueError:
            return None


EXPECTED_PER_PAGE = 50

EXPECTED_SORT_OPTIONS = {
    "date": (ExpectedVisit.expected_date, ExpectedVisit.expected_time),
    "host": (ExpectedVisit.host_name,),
    "visitor": (ExpectedVisit.visitor_first_name, ExpectedVisit.visitor_last_name),
    "company": (ExpectedVisit.visitor_company,),
    "status": (ExpectedVisit.status,),
}


def _build_expected_query(
    *,
    today,
    range_val: str,
    status_filter: str,
    mine_active: bool,
    host_alias: str | None,
    q: str,
    sort: str,
    order: str,
):
    """Construeix una select(...) amb els filtres d'expected_list.
    Retorna l'statement sense load options ni offset/limit."""
    stmt = select(ExpectedVisit)

    if range_val == "today":
        stmt = stmt.where(ExpectedVisit.expected_date == today)
    elif range_val == "week":
        stmt = stmt.where(
            ExpectedVisit.expected_date >= today,
            ExpectedVisit.expected_date <= today + timedelta(days=7),
        )
    elif range_val == "past":
        stmt = stmt.where(ExpectedVisit.expected_date < today)
    elif range_val == "upcoming":
        stmt = stmt.where(ExpectedVisit.expected_date >= today)

    if status_filter in EXPECTED_STATUSES:
        stmt = stmt.where(ExpectedVisit.status == status_filter)

    if mine_active and host_alias:
        stmt = stmt.where(ExpectedVisit.host_name.ilike(f"%{host_alias}%"))

    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            ExpectedVisit.visitor_first_name.ilike(like),
            ExpectedVisit.visitor_last_name.ilike(like),
            ExpectedVisit.visitor_company.ilike(like),
            ExpectedVisit.host_name.ilike(like),
            ExpectedVisit.visit_reason.ilike(like),
        ))

    sort_cols = EXPECTED_SORT_OPTIONS.get(sort, EXPECTED_SORT_OPTIONS["date"])
    if order == "desc":
        stmt = stmt.order_by(*[c.desc().nullslast() for c in sort_cols])
    else:
        stmt = stmt.order_by(*[c.asc().nullslast() for c in sort_cols])
    return stmt


@router.get("/expected", response_class=HTMLResponse)
async def expected_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist", "viewer")),
    range: str = Query("today", pattern="^(today|week|upcoming|past|all)$"),
    status_filter: str = Query("", alias="status"),
    mine: str = Query(""),
    q: str = Query(""),
    sort: str = Query("date", pattern="^(date|host|visitor|company|status)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
):
    today = datetime.now(timezone.utc).date()
    mine_active = bool(mine) and bool(admin.host_alias)
    q_stripped = (q or "").strip()
    # Si l'usuari ha demanat ordre 'past', la convenció anterior era descendent
    # per defecte. Mantenim aquest hàbit només si no s'ha tocat sort/order.
    effective_order = order
    if range == "past" and order == "asc" and sort == "date":
        effective_order = "desc"

    base = _build_expected_query(
        today=today,
        range_val=range,
        status_filter=status_filter,
        mine_active=mine_active,
        host_alias=admin.host_alias,
        q=q_stripped,
        sort=sort,
        order=effective_order,
    )

    # Comptar totals abans de paginar
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0
    total_pages = max(1, (total + EXPECTED_PER_PAGE - 1) // EXPECTED_PER_PAGE)
    page = min(page, total_pages)

    paged = (
        base.options(
            selectinload(ExpectedVisit.department),
            selectinload(ExpectedVisit.created_by),
            selectinload(ExpectedVisit.visit),
        )
        .offset((page - 1) * EXPECTED_PER_PAGE)
        .limit(EXPECTED_PER_PAGE)
    )

    items = (await db.execute(paged)).scalars().all()

    ctx = _admin_context(admin)
    ctx.update({
        "items": items,
        "range": range,
        "status_filter": status_filter,
        "mine_active": mine_active,
        "q": q_stripped,
        "sort": sort,
        "order": effective_order,
        "page": page,
        "total": total,
        "total_pages": total_pages,
        "per_page": EXPECTED_PER_PAGE,
        "page_numbers": list(range_builtin(1, total_pages + 1)),
        "any_filter_applied": (
            range != "today" or bool(status_filter) or mine_active or bool(q_stripped)
        ),
    })
    return templates.TemplateResponse(request, "admin/expected_list.html", ctx)


@router.get("/api/host-suggestions")
async def api_host_suggestions(
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """Llista distinta dels últims amfitrions usats (per a datalist)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    result = await db.execute(
        select(ExpectedVisit.host_name)
        .where(ExpectedVisit.created_at >= cutoff)
        .distinct()
        .order_by(ExpectedVisit.host_name)
    )
    return {"hosts": [row[0] for row in result if row[0]]}


@router.get("/expected/new", response_class=HTMLResponse)
async def expected_new_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist")),
):
    dept_result = await db.execute(
        select(Department).where(Department.active.is_(True)).order_by(Department.order)
    )
    ctx = _admin_context(admin)
    ctx["departments"] = dept_result.scalars().all()
    ctx["error"] = None
    ctx["today_iso"] = datetime.now(timezone.utc).date().isoformat()
    ctx["form"] = {}
    return templates.TemplateResponse(request, "admin/expected_new.html", ctx)


@router.post("/expected")
async def expected_create(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist")),
    visitor_first_name: str = Form(...),
    visitor_last_name: str = Form(""),
    visitor_company: str = Form(""),
    visitor_phone: str = Form(""),
    host_name: str = Form(...),
    department_id: str = Form(""),
    expected_date: str = Form(...),
    expected_time: str = Form(""),
    visit_reason: str = Form(""),
    notes: str = Form(""),
):
    parsed_date = _parse_date_or(expected_date, None)
    if not parsed_date or not visitor_first_name.strip() or not host_name.strip():
        dept_result = await db.execute(
            select(Department).where(Department.active.is_(True)).order_by(Department.order)
        )
        ctx = _admin_context(admin)
        ctx["departments"] = dept_result.scalars().all()
        ctx["error"] = "Els camps Nom, Amfitrió i Data són obligatoris."
        ctx["today_iso"] = datetime.now(timezone.utc).date().isoformat()
        # Preservar el que l'usuari ja havia escrit per no haver-ho de teclejar de nou
        ctx["form"] = {
            "visitor_first_name": visitor_first_name,
            "visitor_last_name": visitor_last_name,
            "visitor_company": visitor_company,
            "visitor_phone": visitor_phone,
            "host_name": host_name,
            "department_id": department_id,
            "expected_date": expected_date,
            "expected_time": expected_time,
            "visit_reason": visit_reason,
            "notes": notes,
        }
        return templates.TemplateResponse(request, "admin/expected_new.html", ctx)

    item = ExpectedVisit(
        visitor_first_name=visitor_first_name.strip(),
        visitor_last_name=(visitor_last_name or "").strip() or None,
        visitor_company=(visitor_company or "").strip() or None,
        visitor_phone=(visitor_phone or "").strip() or None,
        host_name=host_name.strip(),
        department_id=department_id or None,
        expected_date=parsed_date,
        expected_time=_parse_time_or_none(expected_time),
        visit_reason=(visit_reason or "").strip() or None,
        notes=(notes or "").strip() or None,
        status="pending",
        created_by_id=admin.id,
        access_code=await generate_unique_access_code(db),
    )
    db.add(item)
    await db.commit()
    return RedirectResponse("/admin/expected", status_code=302)


def _expected_full_name(item: ExpectedVisit) -> str:
    """Retorna el nom complet formatat per mostrar / cercar."""
    parts = [item.visitor_first_name or ""]
    if item.visitor_last_name:
        parts.append(item.visitor_last_name)
    return " ".join(p for p in parts if p).strip()


def _build_email_defaults(item: ExpectedVisit) -> tuple[str, str]:
    """Assumpte i cos prefilats per a la notificació d'una visita prevista."""
    full_name = _expected_full_name(item)
    subject = f"Visita prevista: {full_name} el {item.expected_date.strftime('%d/%m/%Y')}"

    lines = [
        "Hola,",
        "",
        "Us notifico la visita prevista següent:",
        "",
        f"Visitant: {full_name}",
    ]
    if item.visitor_company:
        lines.append(f"Empresa: {item.visitor_company}")
    if item.visitor_phone:
        lines.append(f"Telèfon: {item.visitor_phone}")
    lines.append(f"Amfitrió: {item.host_name}")
    if item.department:
        lines.append(f"Departament: {item.department.name_ca}")
    lines.append(f"Data: {item.expected_date.strftime('%d/%m/%Y')}")
    if item.expected_time:
        lines.append(f"Hora aproximada: {item.expected_time.strftime('%H:%M')}")
    if item.visit_reason:
        lines.append(f"Motiu: {item.visit_reason}")
    if item.notes:
        lines.append("")
        lines.append(f"Notes: {item.notes}")
    lines.append("")
    lines.append("Salutacions,")
    lines.append(settings.COMPANY_NAME)
    return subject, "\n".join(lines)


# ─── Vistes especials de visites previstes (cal declarar-les abans del
# /expected/{item_id} perquè FastAPI captura per ordre de declaració). ───

@router.get("/expected/print", response_class=HTMLResponse)
async def expected_print(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist", "viewer")),
    range: str = Query("today", pattern="^(today|tomorrow|week|date)$"),
    date: str = Query(""),
    mine: str = Query(""),
):
    """Vista imprimible de les visites previstes (per al cap o recepció)."""
    today = datetime.now(timezone.utc).date()
    mine_active = bool(mine) and bool(admin.host_alias)

    if range == "today":
        date_from, date_to = today, today
        title = "Visites previstes per a avui"
    elif range == "tomorrow":
        d = today + timedelta(days=1)
        date_from, date_to = d, d
        title = "Visites previstes per a demà"
    elif range == "week":
        date_from, date_to = today, today + timedelta(days=6)
        title = "Visites previstes (7 dies)"
    elif range == "date":
        d = _parse_date_or(date, today)
        date_from, date_to = d, d
        title = f"Visites previstes per al {d.strftime('%d/%m/%Y')}"
    else:
        date_from, date_to = today, today
        title = "Visites previstes"

    stmt = (
        select(ExpectedVisit)
        .options(selectinload(ExpectedVisit.department))
        .where(
            ExpectedVisit.expected_date >= date_from,
            ExpectedVisit.expected_date <= date_to,
            ExpectedVisit.status.in_(["pending", "arrived"]),
        )
        .order_by(
            ExpectedVisit.expected_date.asc(),
            ExpectedVisit.expected_time.asc().nullslast(),
        )
    )
    if mine_active:
        stmt = stmt.where(ExpectedVisit.host_name.ilike(f"%{admin.host_alias}%"))

    items = (await db.execute(stmt)).scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/expected_print.html",
        {
            "items": items,
            "title": title,
            "now": datetime.now(timezone.utc),
            "settings": settings,
            "admin": admin,
            "mine_active": mine_active,
        },
    )


EXPECTED_CSV_HEADERS = [
    "visitor_first_name", "visitor_last_name", "visitor_company",
    "visitor_phone", "host_name", "department", "expected_date",
    "expected_time", "visit_reason", "notes",
]


@router.get("/expected/import", response_class=HTMLResponse)
async def expected_import_page(
    request: Request,
    admin: AdminUser = Depends(require_role("admin", "receptionist")),
):
    ctx = _admin_context(admin)
    ctx["headers"] = EXPECTED_CSV_HEADERS
    ctx["errors"] = []
    ctx["preview"] = []
    ctx["created"] = None
    return templates.TemplateResponse(request, "admin/expected_import.html", ctx)


@router.get("/expected/import/template")
async def expected_import_template(
    admin: AdminUser = Depends(require_role("admin", "receptionist")),
):
    """Plantilla CSV buida amb les columnes correctes i una fila d'exemple."""
    import csv
    import io
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPECTED_CSV_HEADERS)
    writer.writerow([
        "Maria", "Sànchez Pérez", "Test SL", "+34666123456",
        "Joan Pi", "Direcció", "2026-05-15", "10:00",
        "Reunió comercial trimestral", "",
    ])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="visites_previstes_plantilla.csv"'},
    )


@router.post("/expected/import")
async def expected_import_submit(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist")),
):
    """Parseja un CSV de visites previstes i les crea en bloc (tot o res).

    Si alguna fila falla la validació, no es crea cap previsió i es
    retorna la mateixa pàgina amb la llista d'errors per fila.
    """
    import csv
    import io

    form = await request.form()
    upload = form.get("file")
    if not upload or not hasattr(upload, "read"):
        ctx = _admin_context(admin)
        ctx["headers"] = EXPECTED_CSV_HEADERS
        ctx["errors"] = ["Cal seleccionar un fitxer CSV."]
        ctx["preview"] = []
        ctx["created"] = None
        return templates.TemplateResponse(request, "admin/expected_import.html", ctx)

    raw = await upload.read()
    if isinstance(raw, bytes):
        try:
            text_content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text_content = raw.decode("latin-1")
    else:
        text_content = raw

    # Carregar departaments per nom (case-insensitive contra el català)
    dept_result = await db.execute(select(Department).where(Department.active.is_(True)))
    dept_by_name = {d.name_ca.lower().strip(): d for d in dept_result.scalars().all()}

    reader = csv.DictReader(io.StringIO(text_content))
    if not reader.fieldnames:
        ctx = _admin_context(admin)
        ctx["headers"] = EXPECTED_CSV_HEADERS
        ctx["errors"] = ["El CSV està buit o no té capçalera."]
        ctx["preview"] = []
        ctx["created"] = None
        return templates.TemplateResponse(request, "admin/expected_import.html", ctx)

    missing_cols = [c for c in ("visitor_first_name", "host_name", "expected_date") if c not in reader.fieldnames]
    if missing_cols:
        ctx = _admin_context(admin)
        ctx["headers"] = EXPECTED_CSV_HEADERS
        ctx["errors"] = [f"Falten columnes obligatòries: {', '.join(missing_cols)}"]
        ctx["preview"] = []
        ctx["created"] = None
        return templates.TemplateResponse(request, "admin/expected_import.html", ctx)

    rows_to_create: list[dict] = []
    errors: list[str] = []
    today = datetime.now(timezone.utc).date()

    for line_no, row in enumerate(reader, start=2):  # capçalera = 1
        first = (row.get("visitor_first_name") or "").strip()
        last = (row.get("visitor_last_name") or "").strip() or None
        company = (row.get("visitor_company") or "").strip() or None
        phone = (row.get("visitor_phone") or "").strip() or None
        host = (row.get("host_name") or "").strip()
        dept_name = (row.get("department") or "").strip()
        date_str = (row.get("expected_date") or "").strip()
        time_str = (row.get("expected_time") or "").strip()
        reason = (row.get("visit_reason") or "").strip() or None
        notes = (row.get("notes") or "").strip() or None

        if not first:
            errors.append(f"Fila {line_no}: Nom del visitant és obligatori.")
            continue
        if not host:
            errors.append(f"Fila {line_no}: Amfitrió és obligatori.")
            continue

        try:
            expected_date = date.fromisoformat(date_str)
        except (ValueError, TypeError):
            errors.append(f"Fila {line_no}: Data invàlida ('{date_str}'). Format requerit: AAAA-MM-DD.")
            continue
        if expected_date < today:
            errors.append(f"Fila {line_no}: La data ({expected_date}) és al passat.")
            continue

        expected_time = None
        if time_str:
            try:
                expected_time = datetime.strptime(time_str, "%H:%M").time()
            except ValueError:
                errors.append(f"Fila {line_no}: Hora invàlida ('{time_str}'). Format requerit: HH:MM.")
                continue

        dept = None
        if dept_name:
            dept = dept_by_name.get(dept_name.lower())
            if not dept:
                errors.append(f"Fila {line_no}: Departament '{dept_name}' no trobat. Comprova el nom (case-insensitive).")
                continue

        rows_to_create.append({
            "visitor_first_name": first,
            "visitor_last_name": last,
            "visitor_company": company,
            "visitor_phone": phone,
            "host_name": host,
            "department_id": dept.id if dept else None,
            "expected_date": expected_date,
            "expected_time": expected_time,
            "visit_reason": reason,
            "notes": notes,
        })

    if errors:
        ctx = _admin_context(admin)
        ctx["headers"] = EXPECTED_CSV_HEADERS
        ctx["errors"] = errors
        ctx["preview"] = rows_to_create
        ctx["created"] = None
        return templates.TemplateResponse(request, "admin/expected_import.html", ctx)

    if not rows_to_create:
        ctx = _admin_context(admin)
        ctx["headers"] = EXPECTED_CSV_HEADERS
        ctx["errors"] = ["El CSV no conté cap fila vàlida."]
        ctx["preview"] = []
        ctx["created"] = None
        return templates.TemplateResponse(request, "admin/expected_import.html", ctx)

    # Tot validat: crear-les amb codi d'accés únic per a cadascuna
    for d in rows_to_create:
        db.add(ExpectedVisit(
            **d,
            status="pending",
            created_by_id=admin.id,
            access_code=await generate_unique_access_code(db),
        ))
    await db.commit()
    return RedirectResponse(
        f"/admin/expected?range=upcoming&imported={len(rows_to_create)}",
        status_code=302,
    )


@router.get("/expected/calendar", response_class=HTMLResponse)
async def expected_calendar(
    request: Request,
    admin: AdminUser = Depends(require_role("admin", "receptionist", "viewer")),
):
    ctx = _admin_context(admin)
    return templates.TemplateResponse(request, "admin/expected_calendar.html", ctx)


@router.get("/api/expected-events")
async def api_expected_events(
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    start: str = Query(""),
    end: str = Query(""),
    mine: str = Query(""),
):
    """Esdeveniments per a FullCalendar. Format compatible amb la lib."""
    today = datetime.now(timezone.utc).date()
    start_d = _parse_date_or(start, today - timedelta(days=30))
    end_d = _parse_date_or(end, today + timedelta(days=60))
    mine_active = bool(mine) and bool(admin.host_alias)

    stmt = (
        select(ExpectedVisit)
        .where(
            ExpectedVisit.expected_date >= start_d,
            ExpectedVisit.expected_date <= end_d,
        )
        .order_by(ExpectedVisit.expected_date.asc())
    )
    if mine_active:
        stmt = stmt.where(ExpectedVisit.host_name.ilike(f"%{admin.host_alias}%"))

    items = (await db.execute(stmt)).scalars().all()

    color_by_status = {
        "pending": "#3b82f6",
        "arrived": "#10b981",
        "cancelled": "#9ca3af",
        "no_show": "#f59e0b",
    }

    events = []
    for it in items:
        full_name = f"{it.visitor_first_name} {it.visitor_last_name or ''}".strip()
        time_str = it.expected_time.strftime("%H:%M") if it.expected_time else ""
        title = f"{time_str} {full_name} → {it.host_name}".strip()
        # Si hi ha hora, fem un esdeveniment amb timestamp; sinó, all-day
        if it.expected_time:
            start_iso = datetime.combine(it.expected_date, it.expected_time).isoformat()
            events.append({
                "id": str(it.id),
                "title": title,
                "start": start_iso,
                "url": f"/admin/expected/{it.id}",
                "backgroundColor": color_by_status.get(it.status, "#3b82f6"),
                "borderColor": color_by_status.get(it.status, "#3b82f6"),
            })
        else:
            events.append({
                "id": str(it.id),
                "title": title,
                "start": it.expected_date.isoformat(),
                "allDay": True,
                "url": f"/admin/expected/{it.id}",
                "backgroundColor": color_by_status.get(it.status, "#3b82f6"),
                "borderColor": color_by_status.get(it.status, "#3b82f6"),
            })
    return events


@router.get("/api/expected/{item_id}/qr.png")
async def api_expected_qr(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist", "viewer")),
):
    """Genera un PNG amb el QR del codi d'accés de la prevista. El QR
    codifica la URL completa al fast-track perquè el visitant pugui
    escanejar-lo amb la càmera del mòbil."""
    import base64
    import io
    import qrcode

    result = await db.execute(
        select(ExpectedVisit).where(ExpectedVisit.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item or not item.access_code:
        return Response(status_code=404)

    base_url = settings.BASE_URL.rstrip("/")
    url = f"{base_url}/ca/code/{item.access_code}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/api/expected-banner", response_class=HTMLResponse)
async def api_expected_banner(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    expected_mine: str = "",
):
    """Fragment HTML del bàner de visites previstes (per a HTMX live update)."""
    today_date = datetime.now(timezone.utc).date()
    mine_active = bool(expected_mine) and bool(admin.host_alias)
    stmt = (
        select(ExpectedVisit)
        .options(selectinload(ExpectedVisit.department))
        .where(
            ExpectedVisit.expected_date == today_date,
            ExpectedVisit.status.in_(["pending", "arrived"]),
        )
        .order_by(ExpectedVisit.expected_time.asc().nullslast())
    )
    if mine_active:
        stmt = stmt.where(ExpectedVisit.host_name.ilike(f"%{admin.host_alias}%"))
    expected_today = (await db.execute(stmt)).scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/_expected_banner.html",
        {
            "admin": admin,
            "expected_today": expected_today,
            "expected_today_count": len(expected_today),
            "expected_pending_count": sum(1 for e in expected_today if e.status == "pending"),
            "expected_arrived_count": sum(1 for e in expected_today if e.status == "arrived"),
            "expected_mine_active": mine_active,
        },
    )


@router.get("/expected/{item_id}", response_class=HTMLResponse)
async def expected_detail(
    item_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist", "viewer")),
    email_sent: str = "",
    email_error: str = "",
):
    result = await db.execute(
        select(ExpectedVisit)
        .where(ExpectedVisit.id == item_id)
        .options(
            selectinload(ExpectedVisit.department),
            selectinload(ExpectedVisit.created_by),
            selectinload(ExpectedVisit.last_updated_by),
            selectinload(ExpectedVisit.visit),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        return RedirectResponse("/admin/expected", status_code=302)

    dept_result = await db.execute(
        select(Department).where(Department.active.is_(True)).order_by(Department.order)
    )
    default_subject, default_body = _build_email_defaults(item)

    ctx = _admin_context(admin)
    ctx["item"] = item
    ctx["departments"] = dept_result.scalars().all()
    ctx["statuses"] = EXPECTED_STATUSES
    ctx["smtp_ready"] = smtp_configured()
    ctx["default_email_subject"] = default_subject
    ctx["default_email_body"] = default_body
    ctx["email_sent"] = email_sent
    ctx["email_error"] = email_error
    return templates.TemplateResponse(request, "admin/expected_detail.html", ctx)


@router.post("/expected/{item_id}/update")
async def expected_update(
    item_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist")),
    visitor_first_name: str = Form(...),
    visitor_last_name: str = Form(""),
    visitor_company: str = Form(""),
    visitor_phone: str = Form(""),
    host_name: str = Form(...),
    department_id: str = Form(""),
    expected_date: str = Form(...),
    expected_time: str = Form(""),
    visit_reason: str = Form(""),
    notes: str = Form(""),
    status_in: str = Form("pending", alias="status"),
):
    result = await db.execute(select(ExpectedVisit).where(ExpectedVisit.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        return RedirectResponse("/admin/expected", status_code=302)

    parsed_date = _parse_date_or(expected_date, item.expected_date)
    old_status = item.status
    item.visitor_first_name = visitor_first_name.strip()
    item.visitor_last_name = (visitor_last_name or "").strip() or None
    item.visitor_company = (visitor_company or "").strip() or None
    item.visitor_phone = (visitor_phone or "").strip() or None
    item.host_name = host_name.strip()
    item.department_id = department_id or None
    item.expected_date = parsed_date
    item.expected_time = _parse_time_or_none(expected_time)
    item.visit_reason = (visit_reason or "").strip() or None
    item.notes = (notes or "").strip() or None
    if status_in in EXPECTED_STATUSES:
        item.status = status_in
    item.last_updated_by_id = admin.id

    # Si l'admin canvia l'estat a 'arrived' i encara no hi ha vincle,
    # intentem trobar una visita real del dia que coincideixi (mateix
    # criteri que el botó "Marcar arribada").
    if item.status == "arrived" and item.visit_id is None:
        matched = await find_matching_visit_for_expected(item, db)
        if matched:
            item.visit_id = matched.id

    await _log_expected_status_change(db, request, admin, item, old_status, item.status)
    await db.commit()
    return RedirectResponse(f"/admin/expected/{item.id}", status_code=302)


@router.post("/expected/{item_id}/mark-arrived")
async def expected_mark_arrived(
    item_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist")),
):
    result = await db.execute(select(ExpectedVisit).where(ExpectedVisit.id == item_id))
    item = result.scalar_one_or_none()
    if item:
        old_status = item.status
        # Si encara no està vinculada, mirem si hi ha una visita registrada
        # avui que hi coincideixi (mateix criteri que l'auto-vincle).
        if item.visit_id is None:
            matched = await find_matching_visit_for_expected(item, db)
            if matched:
                item.visit_id = matched.id
        item.status = "arrived"
        item.last_updated_by_id = admin.id
        await _log_expected_status_change(db, request, admin, item, old_status, "arrived")
        await db.commit()
    return RedirectResponse("/admin/expected", status_code=302)


@router.post("/expected/{item_id}/cancel")
async def expected_cancel(
    item_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist")),
):
    result = await db.execute(select(ExpectedVisit).where(ExpectedVisit.id == item_id))
    item = result.scalar_one_or_none()
    if item:
        old_status = item.status
        item.status = "cancelled"
        item.last_updated_by_id = admin.id
        await _log_expected_status_change(db, request, admin, item, old_status, "cancelled")
        await db.commit()
    return RedirectResponse("/admin/expected", status_code=302)


@router.post("/expected/{item_id}/delete")
async def expected_delete(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin")),
):
    await db.execute(delete(ExpectedVisit).where(ExpectedVisit.id == item_id))
    await db.commit()
    return RedirectResponse("/admin/expected", status_code=302)


@router.post("/expected/{item_id}/notify-email")
async def expected_notify_email(
    item_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(require_role("admin", "receptionist")),
    recipients: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
):
    result = await db.execute(select(ExpectedVisit).where(ExpectedVisit.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        return RedirectResponse("/admin/expected", status_code=302)

    if not smtp_configured():
        return RedirectResponse(
            f"/admin/expected/{item.id}?email_error=SMTP+no+configurat",
            status_code=302,
        )

    rcpts = [e.strip() for e in recipients.split(",") if e.strip()]
    rcpts = [e for e in rcpts if "@" in e and len(e) <= 320]
    if not rcpts:
        return RedirectResponse(
            f"/admin/expected/{item.id}?email_error=Cal+almenys+un+destinatari+v%C3%A0lid",
            status_code=302,
        )

    ok, msg = await send_email(rcpts, subject.strip()[:300], body)

    if ok:
        item.last_email_sent_at = datetime.now(timezone.utc)
        item.last_email_recipients = ", ".join(rcpts)
        db.add(AuditLog(
            admin_id=admin.id,
            visit_id=None,
            action="expected_visit_email_sent",
            ip_address=request.client.host if request.client else None,
            detail=json.dumps({
                "expected_id": str(item.id),
                "recipients": rcpts,
                "subject": subject.strip()[:300],
            }),
        ))
        await db.commit()
        return RedirectResponse(
            f"/admin/expected/{item.id}?email_sent=ok",
            status_code=302,
        )

    # Error: registrem intent al log però no marquem last_email_sent_at
    db.add(AuditLog(
        admin_id=admin.id,
        visit_id=None,
        action="expected_visit_email_failed",
        ip_address=request.client.host if request.client else None,
        detail=json.dumps({
            "expected_id": str(item.id),
            "recipients": rcpts,
            "error": msg[:400],
        }),
    ))
    await db.commit()
    from urllib.parse import quote
    return RedirectResponse(
        f"/admin/expected/{item.id}?email_error={quote(msg[:200])}",
        status_code=302,
    )
