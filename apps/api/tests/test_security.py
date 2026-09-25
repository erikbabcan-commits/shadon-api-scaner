import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.security import create_session_token, read_session_token


def test_session_token_serialization():
    settings = get_settings()
    token = create_session_token(settings, "user-12345", token_version=2)
    data = read_session_token(settings, token)
    assert data is not None
    assert data["uid"] == "user-12345"
    assert data["ver"] == 2


def test_tampered_token_rejected():
    settings = get_settings()
    token = create_session_token(settings, "user-12345", token_version=1)
    tampered = token[:-4] + "xxxx"
    assert read_session_token(settings, tampered) is None


@pytest.mark.asyncio
async def test_security_headers_and_request_id(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert "x-request-id" in resp.headers
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert "strict-origin-when-cross-origin" in resp.headers.get("referrer-policy", "")
