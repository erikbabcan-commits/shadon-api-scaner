import pytest
from httpx import AsyncClient
from app.config import get_settings
from app.models import User
from app.security import create_session_token


@pytest.mark.asyncio
async def test_create_and_get_app(auth_client: AsyncClient):
    # 1. Create app
    resp = await auth_client.post(
        "/api/apps",
        json={
            "name": "Production App",
            "environment": "prod",
            "base_url": "https://example.com",
            "heartbeat_enabled": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    app_id = data["id"]
    assert data["name"] == "Production App"
    assert len(data["targets"]) == 1
    assert data["targets"][0]["host"] == "example.com"

    # 2. Get app
    get_resp = await auth_client.get(f"/api/apps/{app_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == app_id

    # 3. List apps
    list_resp = await auth_client.get("/api/apps")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # 4. Update app
    patch_resp = await auth_client.patch(
        f"/api/apps/{app_id}",
        json={"git_url": "https://github.com/example/repo.git"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["git_url"] == "https://github.com/example/repo.git"

    # 5. Delete app
    del_resp = await auth_client.delete(f"/api/apps/{app_id}")
    assert del_resp.status_code == 204

    # 6. Verify deleted
    get_deleted = await auth_client.get(f"/api/apps/{app_id}")
    assert get_deleted.status_code == 404


@pytest.mark.asyncio
async def test_ssrf_protection_base_url(auth_client: AsyncClient):
    # Block localhost
    resp1 = await auth_client.post(
        "/api/apps",
        json={"name": "Bad App", "base_url": "http://localhost:8080"},
    )
    assert resp1.status_code == 422

    # Block 127.0.0.1
    resp2 = await auth_client.post(
        "/api/apps",
        json={"name": "Bad App 2", "base_url": "http://127.0.0.1/admin"},
    )
    assert resp2.status_code == 422

    # Block cloud metadata
    resp3 = await auth_client.post(
        "/api/apps",
        json={"name": "Metadata Exploit", "base_url": "http://169.254.169.254/latest"},
    )
    assert resp3.status_code == 422


@pytest.mark.asyncio
async def test_cross_org_app_access_and_non_existent(auth_client: AsyncClient, test_user: User):
    settings = get_settings()

    # 1. Unauthenticated request to app must return 401
    auth_client.cookies.clear()
    unauth_resp = await auth_client.get("/api/apps/6dce8ff3-6b95-49ff-bcab-3894f4075d58")
    assert unauth_resp.status_code == 401

    # Re-authenticate client
    token = create_session_token(settings, str(test_user.id), test_user.token_version)
    auth_client.cookies.set(settings.straz_cookie_name, token)

    # 2. Non-existent UUID must return 404
    non_existent = await auth_client.get("/api/apps/00000000-0000-0000-0000-000000000000")
    assert non_existent.status_code == 404

    # 3. Create Org 1 and App 1
    org1_resp = await auth_client.post("/api/orgs", json={"name": "Org Alpha"})
    assert org1_resp.status_code == 201
    org1_id = org1_resp.json()["id"]

    app1_resp = await auth_client.post(
        "/api/apps",
        headers={"X-Organization-Id": org1_id},
        json={
            "name": "Alpha Portal",
            "environment": "prod",
            "base_url": "https://alpha.example.com",
            "heartbeat_enabled": True,
        },
    )
    assert app1_resp.status_code == 201
    app1_id = app1_resp.json()["id"]

    # 4. Create Org 2 (same user is owner)
    org2_resp = await auth_client.post("/api/orgs", json={"name": "Org Beta"})
    assert org2_resp.status_code == 201
    org2_id = org2_resp.json()["id"]

    # 5. Access App 1 while X-Organization-Id header is pointing to Org 2
    cross_resp = await auth_client.get(
        f"/api/apps/{app1_id}",
        headers={"X-Organization-Id": org2_id},
    )
    assert cross_resp.status_code == 200
    assert cross_resp.json()["id"] == app1_id
    assert cross_resp.json()["organization_id"] == org1_id

