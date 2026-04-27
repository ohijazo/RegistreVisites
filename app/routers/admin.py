import base64
import hashlib
import json
from datetime import datetime, timezone, timedelta, date

from fastapi import APIRouter, Request, Depends, Form, Query, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, and_, or_, text, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from jose import jwt

from app.services.auth import hash_password, verify_password

from app.config import settings
from app.db.database import get_db
from app.db.models import AdminUser, Visit, Department, LegalDocument, AuditLog
from app.dependencies import get_current_admin, require_role
from app.services.crypto import decrypt
from app.services.export import visits_to_excel, visits_to_csv

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

    # Generar JWT
    token = jwt.encode(
        {
            "sub": str(user.id),
            "exp": datetime.now(timezone.utc) + timedelta(hours=settings.SESSION_HOURS),
        },
        settings.SECRET_KEY,
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
async def logout():
    response = RedirectResponse("/admin/login", status_code=302)
    response.delete_cookie("access_token")
    return response


# ── Dashboard ────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
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

    ctx = _admin_context(admin)
    ctx["visit"] = visit
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

    # Auditoria de l'eliminació (visit_id=None perquè la visita s'eliminarà)
    audit = AuditLog(
        admin_id=admin.id,
        visit_id=None,
        action="delete_visit",
        ip_address=request.client.host if request.client else None,
        detail=json.dumps({
            "visit_id": str(visit.id),
            "first_name": visit.first_name,
            "last_name": visit.last_name,
            "company": visit.company,
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

    # Dades crues per filtratge interactiu (dia, dept, hora, empresa per cada visita)
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
    )
    raw_visits = [
        {
            "day": row.day.strftime("%Y-%m-%d"),
            "dept": row.dept or "—",
            "hour": int(row.hour),
            "company": row.company,
            "name": f"{row.first_name} {row.last_name}",
        }
        for row in raw_result
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
    result = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.password_hash = hash_password(password)
        await db.commit()
    return RedirectResponse("/admin/users", status_code=302)
