import asyncio
import base64
import hashlib
import os
import secrets

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

# Configurar entorn test ABANS d'importar app
os.environ["DATABASE_URL"] = "postgresql+asyncpg://visites_user:Ra9%21fT32%40Qlm@localhost/visites_test"
os.environ["ENCRYPTION_KEY"] = base64.b64encode(os.urandom(32)).decode()
os.environ["SECRET_KEY"] = secrets.token_urlsafe(32)
os.environ["DEBUG"] = "false"
os.environ["ENV"] = "test"

from app.config import get_settings
get_settings.cache_clear()

from app.db.database import Base, get_db
from app.db.models import Department, LegalDocument, AdminUser, Visit
from app.services.auth import hash_password
from app.services.crypto import encrypt
from app.main import app

DATABASE_URL_TEST = os.environ["DATABASE_URL"]


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    """Crear taules i dades seed un sol cop."""
    engine = create_async_engine(DATABASE_URL_TEST)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as session:
        dept = Department(
            name_ca="Producció", name_es="Producción",
            name_fr="Production", name_en="Production", order=1,
        )
        session.add(dept)

        content = "Text legal de test"
        doc = LegalDocument(
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            content_ca=content, content_es=content,
            content_fr=content, content_en=content, active=True,
        )
        session.add(doc)

        admin = AdminUser(
            email="test@test.com", name="Test Admin",
            password_hash=hash_password("TestPassword12"),
            role="admin", active=True,
        )
        session.add(admin)

        # Visites per tests de checkout/admin
        for i, (name, token, pin, dni) in enumerate([
            ("Checkout", "checkout-test-token", "100001", "CHECKOUT_TEST_1"),
            ("Token", "direct-test-token", "100002", "TOKEN_TEST_1"),
            ("Manual", "manual-test-token", "100003", "MANUAL_TEST_1"),
            ("Delete", "delete-test-token", "100004", "DELETE_TEST_1"),
            ("Bulk", "bulk-test-token", "100005", "BULK_TEST_1"),
        ]):
            enc, iv = encrypt(dni)
            v = Visit(
                first_name=name, last_name="Test", company="TEST CO",
                id_document_enc=enc, id_document_iv=iv,
                visit_reason="Test", language="ca",
                exit_token=token, exit_pin=pin,
            )
            session.add(v)

        # Visita ja tancada
        from datetime import datetime, timezone
        enc, iv = encrypt("ALREADY_OUT_1")
        v_out = Visit(
            first_name="Already", last_name="Out", company="TEST CO",
            id_document_enc=enc, id_document_iv=iv,
            visit_reason="Test", language="ca",
            exit_token="already-out-token", exit_pin="100006",
            checked_out_at=datetime.now(timezone.utc), checkout_method="manual",
        )
        session.add(v_out)

        await session.commit()

    await engine.dispose()
    yield


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(DATABASE_URL_TEST)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with sf() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as c:
        yield c

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def admin_cookies(client):
    resp = await client.post("/admin/login", data={
        "email": "test@test.com", "password": "TestPassword12",
    })
    return resp.cookies
