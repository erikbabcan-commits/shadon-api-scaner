import pytest
from httpx import AsyncClient

from app.models import User


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: User):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "tester@example.com", "password": "SuperSecret123!"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "tester@example.com"
    assert "straz_session" in client.cookies or "Set-Cookie" in resp.headers


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user: User):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "tester@example.com", "password": "WrongPassword!"},
    )
    assert resp.status_code == 401
    assert "Invalid credentials" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_me_unauthorized(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_authorized(auth_client: AsyncClient, test_user: User):
    resp = await auth_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == test_user.email


@pytest.mark.asyncio
async def test_logout(auth_client: AsyncClient):
    resp = await auth_client.post("/api/auth/logout")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_change_password(auth_client: AsyncClient, test_user: User):
    # Change password
    resp = await auth_client.post(
        "/api/auth/change-password",
        json={
            "old_password": "SuperSecret123!",
            "new_password": "NewSuperPassword999!",
        },
    )
    assert resp.status_code == 200

    # Old password no longer works
    login_fail = await auth_client.post(
        "/api/auth/login",
        json={"email": "tester@example.com", "password": "SuperSecret123!"},
    )
    assert login_fail.status_code == 401

    # New password works
    login_ok = await auth_client.post(
        "/api/auth/login",
        json={"email": "tester@example.com", "password": "NewSuperPassword999!"},
    )
    assert login_ok.status_code == 200
