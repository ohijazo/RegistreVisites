"""Tests del flux de checkout."""
import pytest


@pytest.mark.asyncio
async def test_checkout_page_returns_200(client):
    resp = await client.get("/checkout")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_checkout_done_returns_200(client):
    resp = await client.get("/checkout/done")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_checkout_invalid_dni(client):
    resp = await client.post("/checkout/dni", data={"id_document": "INVALID999"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_checkout_invalid_token(client):
    resp = await client.get("/checkout/invalid-xxx")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_checkout_valid_dni(client):
    # Crear visita fresca per aquest test
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.db.models import Visit
    from app.services.crypto import encrypt
    import os
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(engine, class_=AsyncSession)
    async with sf() as s:
        enc, iv = encrypt("FRESH_DNI_CHECKOUT")
        v = Visit(first_name="Fresh", last_name="DNI", company="TEST",
                  id_document_enc=enc, id_document_iv=iv,
                  visit_reason="Test", language="ca",
                  exit_token="fresh-dni-token", exit_pin="900001")
        s.add(v)
        await s.commit()
    await engine.dispose()

    resp = await client.post("/checkout/dni", data={"id_document": "FRESH_DNI_CHECKOUT"})
    assert resp.status_code == 302
    assert "/checkout/done" in resp.headers["location"]


@pytest.mark.asyncio
async def test_checkout_direct_token(client):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.db.models import Visit
    from app.services.crypto import encrypt
    import os
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sf = async_sessionmaker(engine, class_=AsyncSession)
    async with sf() as s:
        enc, iv = encrypt("FRESH_TOKEN_1")
        v = Visit(first_name="Fresh", last_name="Token", company="TEST",
                  id_document_enc=enc, id_document_iv=iv,
                  visit_reason="Test", language="ca",
                  exit_token="fresh-direct-token", exit_pin="900002")
        s.add(v)
        await s.commit()
    await engine.dispose()

    resp = await client.get("/checkout/fresh-direct-token")
    assert resp.status_code == 302
    assert "/checkout/done" in resp.headers["location"]


@pytest.mark.asyncio
async def test_checkout_already_done(client):
    resp = await client.post("/checkout/dni", data={"id_document": "ALREADY_OUT_1"})
    assert resp.status_code == 200
