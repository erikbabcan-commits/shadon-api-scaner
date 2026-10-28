from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.config import Settings, get_settings
from app.rate_limit import InMemorySlidingWindow, client_ip
from app.security import create_session_token, read_session_token


@pytest.mark.parametrize("path", ["/healthz/liveness", "/api/auth/me"])
async def test_https_responses_include_hsts(client, path):
    response = await client.get("https://test" + path)
    assert response.status_code in (200, 401)
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


async def test_production_csrf_failure_also_has_security_headers(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "straz_env", "production")
    response = await client.post("/api/auth/login", headers={"Origin": "https://untrusted.invalid"}, json={})
    assert response.status_code == 403
    assert "max-age=31536000" in response.headers["Strict-Transport-Security"]
    assert response.headers["Cache-Control"] == "no-store"


async def test_plain_http_development_does_not_set_hsts(client):
    response = await client.get("/healthz/liveness")
    assert "Strict-Transport-Security" not in response.headers


def test_session_secret_rotation_invalidates_old_tokens():
    before = Settings(straz_session_secret="a" * 48)
    after = Settings(straz_session_secret="b" * 48)
    token = create_session_token(before, "local-fixture", 1)
    assert read_session_token(before, token) is not None
    assert read_session_token(after, token) is None


def proxy_fixture():
    app = FastAPI()
    budget = InMemorySlidingWindow()

    @app.get("/budget")
    async def check(request: Request):
        remaining, _ = await budget.check(client_ip(request), 1, 60)
        return {"allowed": remaining >= 0}

    return ProxyHeadersMiddleware(app, trusted_hosts=["192.0.2.10"])


async def test_untrusted_forwarded_header_cannot_reset_budget():
    transport = httpx.ASGITransport(app=proxy_fixture(), client=("198.51.100.1", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://fixture") as client:
        first = await client.get("/budget", headers={"X-Forwarded-For": "203.0.113.1"})
        second = await client.get("/budget", headers={"X-Forwarded-For": "203.0.113.2"})
    assert first.json()["allowed"] is True
    assert second.json()["allowed"] is False


async def test_verified_proxy_separates_clients_and_ignores_spoofed_leftmost_hop():
    transport = httpx.ASGITransport(app=proxy_fixture(), client=("192.0.2.10", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://fixture") as client:
        first = await client.get("/budget", headers={"X-Forwarded-For": "203.0.113.99, 198.51.100.1"})
        second = await client.get("/budget", headers={"X-Forwarded-For": "198.51.100.2"})
        repeat = await client.get("/budget", headers={"X-Forwarded-For": "203.0.113.88, 198.51.100.1"})
    assert first.json()["allowed"] is True
    assert second.json()["allowed"] is True
    assert repeat.json()["allowed"] is False
