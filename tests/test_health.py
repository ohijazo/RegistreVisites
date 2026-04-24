"""Tests del health check i endpoints bàsics."""
import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_static_logo(client):
    resp = await client.get("/static/logo.png")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_checkout_lang_redirect(client):
    resp = await client.get("/ca/checkout")
    assert resp.status_code == 302
    assert "/checkout" in resp.headers["location"]
