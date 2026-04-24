"""Tests del flux complet del visitant."""
import pytest


@pytest.mark.asyncio
async def test_root_redirects(client):
    assert (await client.get("/")).status_code == 302

@pytest.mark.asyncio
async def test_language_page(client):
    resp = await client.get("/ca/")
    assert resp.status_code == 200
    assert "Català" in resp.text

@pytest.mark.asyncio
async def test_invalid_language_redirects(client):
    assert (await client.get("/xx/")).status_code == 302

@pytest.mark.asyncio
async def test_action_page_all_languages(client):
    for lang in ["ca", "es", "fr", "en"]:
        assert (await client.get(f"/{lang}/action")).status_code == 200

@pytest.mark.asyncio
async def test_register_form(client):
    assert (await client.get("/ca/register")).status_code == 200

@pytest.mark.asyncio
async def test_register_empty_fields(client):
    resp = await client.post("/ca/register", data={
        "first_name": "", "last_name": "", "company": "",
        "id_document": "", "department_id": "", "visit_reason": "", "phone": "",
    })
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_register_valid_redirects_to_legal(client):
    # Obtenir dept_id
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import select
    from app.db.models import Department
    import os
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(engine, class_=AsyncSession)
    async with sf() as s:
        result = await s.execute(select(Department).limit(1))
        dept_id = str(result.scalar_one().id)
    await engine.dispose()

    resp = await client.post("/ca/register", data={
        "first_name": "Joan", "last_name": "Test", "company": "test",
        "id_document": "12345678A", "department_id": dept_id,
        "visit_reason": "Reunió", "phone": "",
    })
    assert resp.status_code == 302
    assert "/ca/legal" in resp.headers["location"]

@pytest.mark.asyncio
async def test_legal_without_session_redirects(client):
    assert (await client.get("/ca/legal")).status_code == 302
