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
@pytest.mark.parametrize("samesite", ["lax", "none"])
async def test_secure_logout_expires_host_cookie(client: AsyncClient, test_user: User, monkeypatch, samesite):
    from http.cookies import SimpleCookie
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "straz_cookie_secure", True)
    monkeypatch.setattr(settings, "straz_cookie_samesite", samesite)
    monkeypatch.setattr(settings, "straz_cookie_domain", ".example.com")
    login = await client.post("/api/auth/login", json={
        "email": test_user.email, "password": "SuperSecret123!",
    })
    assert login.status_code == 200
    name = "__Host-" + settings.straz_cookie_name
    cookie = f"{name}={login.cookies[name]}"
    response = await client.post("/api/auth/logout", headers={"Cookie": cookie})
    assert response.status_code == 204
    expired = {}
    for header in response.headers.get_list("set-cookie"):
        expired.update(SimpleCookie(header))
    host_cookie = expired[name]
    # __Host- expiry headers must satisfy the same browser prefix rules as creation.
    assert host_cookie["secure"]
    assert host_cookie["path"] == "/" and not host_cookie["domain"]
    assert host_cookie["max-age"] == "0" and host_cookie.value == ""
    assert host_cookie["samesite"] == samesite
    assert expired[settings.straz_cookie_name]["domain"] == ".example.com"
    assert (await client.get("/api/auth/me", headers={"Cookie": cookie})).status_code == 401


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


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "newuser@example.com", "password": "RegisterPassword123!"},
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "newuser@example.com"

    # Check that user is logged in
    me_resp = await client.get("/api/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "newuser@example.com"


@pytest.mark.asyncio
async def test_register_duplicate(client: AsyncClient, test_user: User):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "tester@example.com", "password": "SomePassword123!"},
    )
    assert resp.status_code == 400
    assert "Používateľ s týmto emailom už existuje" in resp.json()["detail"]

