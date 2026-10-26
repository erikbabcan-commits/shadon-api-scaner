import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import (
    App,
    Finding,
    FindingSeverity,
    FindingSource,
    FindingStatus,
    Organization,
    OrganizationMember,
    OrgRole,
    RunStatus,
    ScanProfile,
    ScanRun,
    Target,
    TargetStatus,
    User,
)
from app.security import create_session_token, hash_password


@pytest.mark.asyncio
async def test_api_key_lifecycle_and_auth(client: AsyncClient, db_session: AsyncSession):
    settings = get_settings()

    user = User(
        id=uuid.uuid4(),
        email="devsecops@example.com",
        password_hash=hash_password("Pass123!"),
        token_version=1,
    )
    org = Organization(
        id=uuid.uuid4(),
        name="Security Org",
        slug="security-org",
        plan_tier="starter",
    )
    member = OrganizationMember(
        id=uuid.uuid4(),
        org_id=org.id,
        user_id=user.id,
        role=OrgRole.admin,
    )
    app = App(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Production Portal",
        base_url="https://portal.example.com",
        safe_enabled=True,
    )
    target = Target(
        id=uuid.uuid4(),
        app_id=app.id,
        host="portal.example.com",
        status=TargetStatus.verified,
        verify_token="token-123",
    )
    db_session.add_all([user, org, member, app, target])
    await db_session.commit()

    token = create_session_token(settings, str(user.id), user.token_version)
    client.cookies.set(settings.straz_cookie_name, token)

    # 1. Create API key
    create_resp = await client.post(
        f"/api/orgs/{org.id}/api-keys",
        headers={"X-Organization-Id": str(org.id)},
        json={"name": "GitHub CI Staging", "scopes": ["ci:scan", "apps:read"]},
    )
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    assert "raw_key" in created_data
    raw_key = created_data["raw_key"]
    key_id = created_data["id"]
    assert raw_key.startswith("straz_live_")
    assert created_data["key_prefix"] == raw_key[:16]

    # 2. List API keys (raw_key and hash must not be present)
    list_resp = await client.get(
        f"/api/orgs/{org.id}/api-keys",
        headers={"X-Organization-Id": str(org.id)},
    )
    assert list_resp.status_code == 200
    keys = list_resp.json()
    assert len(keys) == 1
    assert "raw_key" not in keys[0]
    assert "key_hash" not in keys[0]
    assert keys[0]["id"] == key_id

    # 3. Authenticate with Bearer API Key (clear cookie to ensure header auth)
    client.cookies.clear()
    authed_resp = await client.get(
        "/api/apps",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert authed_resp.status_code == 200, authed_resp.json()
    apps_data = authed_resp.json()
    assert any(a["id"] == str(app.id) for a in apps_data)

    # 4. Revoke key
    # Re-login with user cookie to delete key
    client.cookies.set(settings.straz_cookie_name, token)
    del_resp = await client.delete(
        f"/api/orgs/{org.id}/api-keys/{key_id}",
        headers={"X-Organization-Id": str(org.id)},
    )
    assert del_resp.status_code == 204

    # 5. Accessing with revoked key returns 401
    client.cookies.clear()
    revoked_resp = await client.get(
        "/api/apps",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert revoked_resp.status_code == 401


@pytest.mark.asyncio
async def test_api_key_scope_enforcement(client: AsyncClient, db_session: AsyncSession):
    settings = get_settings()

    user = User(
        id=uuid.uuid4(),
        email="scoped@example.com",
        password_hash=hash_password("Pass123!"),
        token_version=1,
    )
    org = Organization(
        id=uuid.uuid4(),
        name="Scoped Org",
        slug="scoped-org",
        plan_tier="pro",
    )
    member = OrganizationMember(
        id=uuid.uuid4(),
        org_id=org.id,
        user_id=user.id,
        role=OrgRole.admin,
    )
    db_session.add_all([user, org, member])
    await db_session.commit()

    token = create_session_token(settings, str(user.id), user.token_version)
    client.cookies.set(settings.straz_cookie_name, token)

    # Create key with only "ci:scan" scope
    create_resp = await client.post(
        f"/api/orgs/{org.id}/api-keys",
        headers={"X-Organization-Id": str(org.id)},
        json={"name": "CI Runner Only", "scopes": ["ci:scan"]},
    )
    assert create_resp.status_code == 201
    raw_key = create_resp.json()["raw_key"]

    client.cookies.clear()

    # Accessing endpoint requiring "findings:read" or non-granted scope
    # (or test require_scope in deps)
    from app.deps import require_scope

    # Let's test calling CI scan endpoint (has "ci:scan" scope)
    # Target missing -> 404/400 (not 403 scope error)
    resp = await client.post(
        "/api/ci/scan",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"app_id": str(uuid.uuid4()), "profile": "safe", "wait": False},
    )
    # The key was authorized; it failed at app lookup (404), proving scope check passed
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_key_quotas_by_plan(client: AsyncClient, db_session: AsyncSession):
    settings = get_settings()

    user = User(
        id=uuid.uuid4(),
        email="freequota@example.com",
        password_hash=hash_password("Pass123!"),
        token_version=1,
    )
    free_org = Organization(
        id=uuid.uuid4(),
        name="Free Workspace",
        slug="free-api-test",
        plan_tier="free",
    )
    member = OrganizationMember(
        id=uuid.uuid4(),
        org_id=free_org.id,
        user_id=user.id,
        role=OrgRole.owner,
    )
    db_session.add_all([user, free_org, member])
    await db_session.commit()

    token = create_session_token(settings, str(user.id), user.token_version)
    client.cookies.set(settings.straz_cookie_name, token)

    # 1. Attempt to create API key on Free tier -> 402 Payment Required
    resp = await client.post(
        f"/api/orgs/{free_org.id}/api-keys",
        headers={"X-Organization-Id": str(free_org.id)},
        json={"name": "Not Allowed Key"},
    )
    assert resp.status_code == 402
    assert resp.headers.get("x-upgrade-required") == "true"

    # 2. Upgrade to Starter (limit is 2 keys)
    free_org.plan_tier = "starter"
    await db_session.commit()

    # First key succeeds
    resp1 = await client.post(
        f"/api/orgs/{free_org.id}/api-keys",
        headers={"X-Organization-Id": str(free_org.id)},
        json={"name": "Starter Key 1"},
    )
    assert resp1.status_code == 201

    # Second key succeeds
    resp2 = await client.post(
        f"/api/orgs/{free_org.id}/api-keys",
        headers={"X-Organization-Id": str(free_org.id)},
        json={"name": "Starter Key 2"},
    )
    assert resp2.status_code == 201

    # Third key fails with 402
    resp3 = await client.post(
        f"/api/orgs/{free_org.id}/api-keys",
        headers={"X-Organization-Id": str(free_org.id)},
        json={"name": "Starter Key 3"},
    )
    assert resp3.status_code == 402


@pytest.mark.asyncio
async def test_ci_scan_gate_execution(client: AsyncClient, db_session: AsyncSession):
    settings = get_settings()

    user = User(
        id=uuid.uuid4(),
        email="ciuser@example.com",
        password_hash=hash_password("Pass123!"),
        token_version=1,
    )
    org = Organization(
        id=uuid.uuid4(),
        name="CI Enterprise",
        slug="ci-enterprise",
        plan_tier="pro",
    )
    member = OrganizationMember(
        id=uuid.uuid4(),
        org_id=org.id,
        user_id=user.id,
        role=OrgRole.owner,
    )
    app = App(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Microservice Auth",
        base_url="https://auth.example.com",
        safe_enabled=True,
    )
    # Pending target (unverified)
    target = Target(
        id=uuid.uuid4(),
        app_id=app.id,
        host="auth.example.com",
        status=TargetStatus.pending,
        verify_token="vtoken",
    )
    db_session.add_all([user, org, member, app, target])
    await db_session.commit()

    token = create_session_token(settings, str(user.id), user.token_version)
    client.cookies.set(settings.straz_cookie_name, token)

    # 1. Reject CI scan when target is not verified
    resp_unverified = await client.post(
        "/api/ci/scan",
        headers={"X-Organization-Id": str(org.id)},
        json={"app_id": str(app.id), "profile": "safe", "wait": False},
    )
    assert resp_unverified.status_code == 400
    assert "domain verification required" in resp_unverified.json()["detail"]

    # 2. Verify target
    target.status = TargetStatus.verified
    await db_session.commit()

    # 3. Run CI scan without waiting (returns 202 Accepted)
    resp_queued = await client.post(
        "/api/ci/scan",
        headers={"X-Organization-Id": str(org.id)},
        json={"app_id": str(app.id), "profile": "safe", "wait": False},
    )
    assert resp_queued.status_code == 202
    queued_data = resp_queued.json()
    assert queued_data["passed"] is False
    assert queued_data["status"] == "queued"
    run_id = queued_data["run_id"]

    # 4. Mark run done and add a CRITICAL finding
    run = await db_session.get(ScanRun, uuid.UUID(run_id))
    assert run is not None
    run.status = RunStatus.done
    run.observations_complete = True

    crit_finding = Finding(
        id=uuid.uuid4(),
        app_id=app.id,
        source=FindingSource.nuclei,
        severity=FindingSeverity.critical,
        title="SQL Injection in Login Endpoint",
        fingerprint="sql-inj-login",
        status=FindingStatus.open,
    )
    db_session.add(crit_finding)
    await db_session.flush()
    from app.models import ScanRunFinding
    db_session.add(ScanRunFinding(scan_run_id=run.id, finding_id=crit_finding.id, observed_severity="critical", is_new=True))
    await db_session.commit()

    # 5. Check run status via GET /api/ci/runs/{run_id} -> should fail gate due to critical finding (HTTP 424)
    resp_gate = await client.get(
        f"/api/ci/runs/{run_id}",
        headers={"X-Organization-Id": str(org.id)},
    )
    assert resp_gate.status_code == 424
    gate_data = resp_gate.json()
    assert gate_data["passed"] is False
    assert gate_data["summary"]["critical"] == 1
    assert "prekračujúce prah" in gate_data["failure_reason"]
