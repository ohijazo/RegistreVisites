"""Tests del panell d'administració."""
import pytest


# ── Pàgines ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_page(client):
    assert (await client.get("/admin/login")).status_code == 200

@pytest.mark.asyncio
async def test_dashboard_requires_auth(client):
    resp = await client.get("/admin/")
    assert resp.status_code == 302

@pytest.mark.asyncio
async def test_login_invalid(client):
    resp = await client.post("/admin/login", data={"email": "test@test.com", "password": "Wrong"})
    assert resp.status_code == 200
    assert "incorrectes" in resp.text.lower()

@pytest.mark.asyncio
async def test_login_valid(client):
    resp = await client.post("/admin/login", data={"email": "test@test.com", "password": "TestPassword12"})
    assert resp.status_code == 302
    assert "access_token" in resp.headers.get("set-cookie", "")

@pytest.mark.asyncio
async def test_dashboard(client, admin_cookies):
    assert (await client.get("/admin/", cookies=admin_cookies)).status_code == 200

@pytest.mark.asyncio
async def test_visits(client, admin_cookies):
    assert (await client.get("/admin/visits", cookies=admin_cookies)).status_code == 200

@pytest.mark.asyncio
async def test_visits_empty_date_filter(client, admin_cookies):
    assert (await client.get("/admin/visits?date_from=&date_to=&company=X", cookies=admin_cookies)).status_code == 200

@pytest.mark.asyncio
async def test_stats(client, admin_cookies):
    assert (await client.get("/admin/stats", cookies=admin_cookies)).status_code == 200

@pytest.mark.asyncio
async def test_departments(client, admin_cookies):
    assert (await client.get("/admin/departments", cookies=admin_cookies)).status_code == 200

@pytest.mark.asyncio
async def test_legal(client, admin_cookies):
    assert (await client.get("/admin/legal", cookies=admin_cookies)).status_code == 200

@pytest.mark.asyncio
async def test_users(client, admin_cookies):
    assert (await client.get("/admin/users", cookies=admin_cookies)).status_code == 200

@pytest.mark.asyncio
async def test_audit_logs(client, admin_cookies):
    assert (await client.get("/admin/audit-logs", cookies=admin_cookies)).status_code == 200

@pytest.mark.asyncio
async def test_help(client, admin_cookies):
    assert (await client.get("/admin/help", cookies=admin_cookies)).status_code == 200

@pytest.mark.asyncio
async def test_evacuation(client, admin_cookies):
    resp = await client.get("/admin/evacuation", cookies=admin_cookies)
    assert resp.status_code == 200
    assert "EVACUACIÓ" in resp.text


# ── Exportació ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_xlsx(client, admin_cookies):
    resp = await client.get("/admin/visits/export?fmt=xlsx", cookies=admin_cookies)
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_export_csv(client, admin_cookies):
    resp = await client.get("/admin/visits/export?fmt=csv", cookies=admin_cookies)
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_print_visits(client, admin_cookies):
    assert (await client.get("/admin/visits/print", cookies=admin_cookies)).status_code == 200


# ── Accions ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manual_checkout(client, admin_cookies):
    # Buscar visit "Manual" pel token
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import select
    from app.db.models import Visit
    import os
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(engine, class_=AsyncSession)
    async with sf() as s:
        result = await s.execute(select(Visit).where(Visit.exit_token == "manual-test-token"))
        visit = result.scalar_one()
        vid = str(visit.id)
    await engine.dispose()

    resp = await client.post(f"/admin/visits/{vid}/checkout", cookies=admin_cookies)
    assert resp.status_code == 302

@pytest.mark.asyncio
async def test_delete_visit(client, admin_cookies):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import select
    from app.db.models import Visit
    import os
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(engine, class_=AsyncSession)
    async with sf() as s:
        result = await s.execute(select(Visit).where(Visit.exit_token == "delete-test-token"))
        visit = result.scalar_one()
        vid = str(visit.id)
    await engine.dispose()

    resp = await client.post(f"/admin/visits/{vid}/delete", cookies=admin_cookies)
    assert resp.status_code == 200
    assert resp.json().get("ok") is True

@pytest.mark.asyncio
async def test_bulk_checkout(client, admin_cookies):
    resp = await client.post("/admin/bulk-checkout", cookies=admin_cookies)
    assert resp.status_code == 302

@pytest.mark.asyncio
async def test_logout(client, admin_cookies):
    resp = await client.get("/admin/logout", cookies=admin_cookies)
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["location"]
