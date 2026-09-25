import pytest
from httpx import AsyncClient


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
