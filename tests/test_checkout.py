import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_checkout_page_returns_200(client: AsyncClient):
    response = await client.get("/checkout")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_checkout_invalid_pin(client: AsyncClient):
    response = await client.post("/checkout/pin", data={"exit_pin": "000000"})
    assert response.status_code == 200
    assert "no trobat" in response.text.lower() or "not found" in response.text.lower() or "checkout_not_found" in response.text


@pytest.mark.asyncio
async def test_checkout_invalid_token(client: AsyncClient):
    response = await client.get("/checkout/invalid-token-xxx", follow_redirects=False)
    # Hauria de mostrar error o redirigir
    assert response.status_code in [200, 302]
