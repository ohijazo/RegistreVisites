import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_language_page_returns_200(client: AsyncClient):
    response = await client.get("/ca/")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_language_redirect_invalid(client: AsyncClient):
    response = await client.get("/xx/", follow_redirects=False)
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_register_form_page(client: AsyncClient):
    response = await client.get("/ca/register")
    assert response.status_code == 200
    assert "Registre de visita" in response.text or "form_title" in response.text


@pytest.mark.asyncio
async def test_root_redirects(client: AsyncClient):
    response = await client.get("/", follow_redirects=False)
    assert response.status_code == 302
