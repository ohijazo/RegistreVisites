import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_login_page(client: AsyncClient):
    response = await client.get("/admin/login")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_dashboard_requires_auth(client: AsyncClient):
    response = await client.get("/admin/", follow_redirects=False)
    assert response.status_code == 302
    assert "/admin/login" in response.headers.get("location", "")


@pytest.mark.asyncio
async def test_admin_login_invalid_credentials(client: AsyncClient):
    response = await client.post("/admin/login", data={
        "email": "fake@test.com",
        "password": "wrongpassword",
    })
    assert response.status_code == 200
    assert "incorrectes" in response.text.lower() or "error" in response.text.lower()
