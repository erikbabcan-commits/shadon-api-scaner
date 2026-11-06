import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models import (
    App,
    AuditEvent,
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
async def test_docker_compose_and_staging_env_verification():
    """Keep the local staging template free of ready-to-use authentication secrets."""
    compose_path = Path(__file__).resolve().parents[3] / "deploy" / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist in deploy/"
    compose_content = compose_path.read_text()

    # 1. Isolated volumes
    assert "volumes:" in compose_content
    assert "straz_pg:" in compose_content

    # 2. No hardcoded production DB URLs or secrets
    assert "railway.app" not in compose_content
    assert "straz-api-production" not in compose_content

    # 3. Dedicated staging env template verification
    staging_env_path = Path(__file__).resolve().parents[3] / "deploy" / ".env.example"
    assert staging_env_path.exists(), "deploy/.env.example must exist"
    staging_env_content = staging_env_path.read_text()
    assert "STRAZ_ENV=staging" in staging_env_content
    assert "STRIPE_SECRET_KEY=" in staging_env_content  # Blank / disabled
    values = dict(
        line.split("=", 1)
        for line in staging_env_content.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    for name in ("POSTGRES_PASSWORD", "DATABASE_URL", "STRAZ_ADMIN_EMAIL", "STRAZ_ADMIN_PASSWORD", "STRAZ_SESSION_SECRET"):
        assert values[name] == "", f"{name} must require private staging setup"
    assert values["STRAZ_ALLOW_SIMULATED_BILLING"] == "false"


@pytest.mark.asyncio
async def test_simulate_activation_security(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    """Require admin opt-in, deny production/Stripe changes, and audit plan transitions."""
    settings = get_settings()

    user = User(
        id=uuid.uuid4(),
        email="viewer@example.com",
        password_hash=hash_password("Pass123!"),
        token_version=1,
    )
    org = Organization(
        id=uuid.uuid4(),
        name="Security Audit Org",
        slug="sec-audit-org",
        plan_tier="free",
    )
    member = OrganizationMember(
        id=uuid.uuid4(),
        org_id=org.id,
        user_id=user.id,
        role=OrgRole.viewer,  # Viewer only
    )
    db_session.add_all([user, org, member])
    await db_session.commit()

    # 1. Unauthenticated -> 401
    resp_unauth = await client.post(
        "/api/billing/simulate-activation",
        json={"tier": "starter"},
    )
    assert resp_unauth.status_code == 401

    # 2. Viewer role -> 403
    token = create_session_token(settings, str(user.id), user.token_version)
    client.cookies.set(settings.straz_cookie_name, token)

    resp_viewer = await client.post(
        "/api/billing/simulate-activation",
        headers={"X-Organization-Id": str(org.id), "X-Requested-With": "XMLHttpRequest"},
        json={"tier": "starter"},
    )
    assert resp_viewer.status_code == 403
    assert "admin" in resp_viewer.json()["detail"].lower()

    # 3. Missing opt-in denies every non-production environment.
    member.role = OrgRole.admin
    await db_session.commit()
    monkeypatch.delenv("STRAZ_ALLOW_SIMULATED_BILLING", raising=False)
    defaults = Settings(_env_file=None)
    assert defaults.straz_allow_simulated_billing is False
    monkeypatch.setattr(settings, "straz_allow_simulated_billing", defaults.straz_allow_simulated_billing)
    for environment in ("development", "staging", "unrecognized"):
        monkeypatch.setattr(settings, "straz_env", environment)
        denied = await client.post(
            "/api/billing/simulate-activation",
            headers={"X-Organization-Id": str(org.id), "X-Requested-With": "XMLHttpRequest"},
            json={"tier": "starter"},
        )
        assert denied.status_code == 403
        assert "disabled" in denied.json()["detail"].lower()
        await db_session.refresh(org)
        assert org.plan_tier == "free"

    # 4. Production remains denied even with explicit opt-in.
    monkeypatch.setattr(settings, "straz_allow_simulated_billing", True)
    monkeypatch.setattr(settings, "straz_env", "production")
    resp_prod = await client.post(
        "/api/billing/simulate-activation",
        headers={"X-Organization-Id": str(org.id), "X-Requested-With": "XMLHttpRequest"},
        json={"tier": "starter"},
    )
    assert resp_prod.status_code == 403
    assert "production" in resp_prod.json()["detail"].lower()

    # 5. Explicitly opted-in staging grants and audits the synthetic plan.
    monkeypatch.setattr(settings, "straz_env", "staging")
    resp_staging = await client.post(
        "/api/billing/simulate-activation",
        headers={"X-Organization-Id": str(org.id), "X-Requested-With": "XMLHttpRequest"},
        json={"tier": "starter"},
    )
    assert resp_staging.status_code == 200
    assert resp_staging.json()["tier"] == "starter"

    await db_session.refresh(org)
    assert org.plan_tier == "starter"
    assert org.subscription_status == "active"
    event = await db_session.scalar(select(AuditEvent).where(
        AuditEvent.action == "billing.simulated_activation",
        AuditEvent.entity_id == str(org.id),
    ))
    assert event is not None
    assert event.organization_id == org.id
    assert event.user_id == user.id
    assert event.details == {"previous_tier": "free", "next_tier": "starter"}
    assert event.detail == "Simulated plan activation from free to starter"

    # 6. An existing Stripe subscription is never overwritten by simulation.
    org.stripe_subscription_id = "sub_synthetic_existing"
    await db_session.commit()
    previous_period = (org.current_period_start, org.current_period_end)
    rejected = await client.post(
        "/api/billing/simulate-activation",
        headers={"X-Organization-Id": str(org.id), "X-Requested-With": "XMLHttpRequest"},
        json={"tier": "agency"},
    )
    assert rejected.status_code == 409
    await db_session.refresh(org)
    assert org.plan_tier == "starter"
    assert org.subscription_status == "active"
    assert (org.current_period_start, org.current_period_end) == previous_period
    events = list(await db_session.scalars(select(AuditEvent).where(
        AuditEvent.action == "billing.simulated_activation",
        AuditEvent.entity_id == str(org.id),
    )))
    assert len(events) == 1


@pytest.mark.asyncio
async def test_m2m_acceptance_lifecycle(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    """Full end-to-end M2M acceptance lifecycle on isolated staging database."""
    settings = get_settings()
    monkeypatch.setattr(settings, "straz_env", "staging")
    monkeypatch.setattr(settings, "straz_allow_simulated_billing", True)

    # 1. Bootstrap Staging Admin & Organization
    admin_user = User(
        id=uuid.uuid4(),
        email="staging-admin@guard-vorkei.com",
        password_hash=hash_password("StagingSecurePass2026!"),
        token_version=1,
    )
    test_org = Organization(
        id=uuid.uuid4(),
        name="Acceptance WordPress Staging Org",
        slug="wp-staging-org",
        plan_tier="free",
    )
    admin_member = OrganizationMember(
        id=uuid.uuid4(),
        org_id=test_org.id,
        user_id=admin_user.id,
        role=OrgRole.owner,
    )
    db_session.add_all([admin_user, test_org, admin_member])
    await db_session.commit()

    admin_token = create_session_token(settings, str(admin_user.id), admin_user.token_version)
    client.cookies.set(settings.straz_cookie_name, admin_token)

    # 2. Grant internal Starter entitlement
    act_resp = await client.post(
        "/api/billing/simulate-activation",
        headers={"X-Organization-Id": str(test_org.id), "X-Requested-With": "XMLHttpRequest"},
        json={"tier": "starter"},
    )
    assert act_resp.status_code == 200

    # 3. Create Monitored App & Verified Target for https://vorkei.com
    test_app = App(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        name="Acceptance WordPress Site",
        base_url="https://vorkei.com",
        heartbeat_enabled=True,
    )
    verified_target = Target(
        id=uuid.uuid4(),
        app_id=test_app.id,
        host="vorkei.com",
        status=TargetStatus.verified,
        verify_token="test-verify-token-acceptance",
        verified_at=datetime.now(timezone.utc),
    )
    db_session.add_all([test_app, verified_target])
    await db_session.commit()

    # 4. Generate Scoped M2M API Key
    key_resp = await client.post(
        f"/api/orgs/{test_org.id}/api-keys",
        headers={"X-Organization-Id": str(test_org.id), "X-Requested-With": "XMLHttpRequest"},
        json={
            "name": "Nexify Guard M2M Bridge Key",
            "scopes": ["ci:scan"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        },
    )
    assert key_resp.status_code == 201
    key_data = key_resp.json()
    raw_api_key = key_data["raw_key"]
    api_key_id = key_data["id"]
    assert raw_api_key.startswith("straz_live_")

    # Clear admin cookie: all subsequent calls are strictly M2M Bearer authentication
    client.cookies.clear()

    # 5. POST /api/ci/scan with wait=false, profile="heartbeat"
    scan_req_body = {
        "app_id": str(test_app.id),
        "profile": "heartbeat",
        "fail_on": "high",
        "wait": False,
        "timeout_seconds": 60,
    }
    scan_resp = await client.post(
        "/api/ci/scan",
        headers={
            "Authorization": f"Bearer {raw_api_key}",
            "X-Organization-Id": str(test_org.id),
            "Content-Type": "application/json",
        },
        json=scan_req_body,
    )
    assert scan_resp.status_code == 202
    scan_resp_data = scan_resp.json()
    assert scan_resp_data["passed"] is False
    assert scan_resp_data["status"] == "queued"
    assert "run_id" in scan_resp_data
    run_id = scan_resp_data["run_id"]
    assert scan_resp_data["status_url"] == f"/api/ci/runs/{run_id}"

    # 6. Simulate worker processing job to completion with verified observations
    run_record = await db_session.get(ScanRun, uuid.UUID(run_id))
    assert run_record is not None
    run_record.status = RunStatus.done
    run_record.observations_complete = True
    run_record.started_at = datetime.now(timezone.utc)
    run_record.finished_at = datetime.now(timezone.utc)
    await db_session.commit()

    # 7. GET /api/ci/runs/{run_id} polling
    poll_resp = await client.get(
        f"/api/ci/runs/{run_id}",
        headers={
            "Authorization": f"Bearer {raw_api_key}",
            "X-Organization-Id": str(test_org.id),
        },
    )
    assert poll_resp.status_code == 200
    poll_data = poll_resp.json()
    assert poll_data["passed"] is True
    assert poll_data["run_id"] == run_id
    assert poll_data["status"] == "done"
    assert poll_data["failure_reason"] is None
    assert poll_data["summary"] == {"critical": 0, "high": 0, "medium": 0, "total_new": 0}

    # 8. Negative Tests:
    # 8a. No token -> 401
    resp_no_token = await client.get(f"/api/ci/runs/{run_id}")
    assert resp_no_token.status_code == 401

    # 8b. Invalid token -> 401
    resp_bad_token = await client.get(
        f"/api/ci/runs/{run_id}",
        headers={"Authorization": "Bearer straz_live_invalid_bad_token_123"},
    )
    assert resp_bad_token.status_code == 401

    # 8c. Insufficient Scope: Create a key with only "apps:read" and attempt CI scan
    client.cookies.set(settings.straz_cookie_name, admin_token)
    read_only_key_resp = await client.post(
        f"/api/orgs/{test_org.id}/api-keys",
        headers={"X-Organization-Id": str(test_org.id), "X-Requested-With": "XMLHttpRequest"},
        json={"name": "Read Only Key", "scopes": ["apps:read"]},
    )
    assert read_only_key_resp.status_code == 201
    read_only_raw_key = read_only_key_resp.json()["raw_key"]
    client.cookies.clear()

    resp_insufficient_scope = await client.post(
        "/api/ci/scan",
        headers={
            "Authorization": f"Bearer {read_only_raw_key}",
            "X-Organization-Id": str(test_org.id),
            "Content-Type": "application/json",
        },
        json=scan_req_body,
    )
    assert resp_insufficient_scope.status_code == 403

    # 8d. Foreign Organization Header -> 403
    foreign_org_id = str(uuid.uuid4())
    resp_bad_org = await client.get(
        f"/api/ci/runs/{run_id}",
        headers={
            "Authorization": f"Bearer {raw_api_key}",
            "X-Organization-Id": foreign_org_id,
        },
    )
    assert resp_bad_org.status_code == 403
    assert "not valid for the requested organization" in resp_bad_org.json()["detail"]

    # 8e. Foreign Run ID -> 404
    foreign_run_id = str(uuid.uuid4())
    resp_foreign_run = await client.get(
        f"/api/ci/runs/{foreign_run_id}",
        headers={
            "Authorization": f"Bearer {raw_api_key}",
            "X-Organization-Id": str(test_org.id),
        },
    )
    assert resp_foreign_run.status_code == 404
    assert "Run not found in organization" in resp_foreign_run.json()["detail"]

    # 8f. Revoked Key -> 401
    client.cookies.set(settings.straz_cookie_name, admin_token)
    revoke_resp = await client.delete(
        f"/api/orgs/{test_org.id}/api-keys/{api_key_id}",
        headers={"X-Organization-Id": str(test_org.id), "X-Requested-With": "XMLHttpRequest"},
    )
    assert revoke_resp.status_code == 204

    # Subsequent M2M call with revoked key -> 401
    client.cookies.clear()
    resp_revoked = await client.get(
        f"/api/ci/runs/{run_id}",
        headers={
            "Authorization": f"Bearer {raw_api_key}",
            "X-Organization-Id": str(test_org.id),
        },
    )
    assert resp_revoked.status_code == 401


@pytest.mark.asyncio
async def test_least_privilege_scope_split(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    """Verify scope split: ci:runs:read allows status retrieval but blocks scan triggering."""
    settings = get_settings()
    monkeypatch.setattr(settings, "straz_env", "staging")

    user = User(
        id=uuid.uuid4(),
        email="scope_audit@guard-vorkei.com",
        password_hash=hash_password("Pass123!"),
        token_version=1,
    )
    org = Organization(
        id=uuid.uuid4(),
        name="Scope Split Org",
        slug="scope-split-org",
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
        name="WordPress Scope Test",
        base_url="https://vorkei.com",
    )
    target = Target(
        id=uuid.uuid4(),
        app_id=app.id,
        host="vorkei.com",
        status=TargetStatus.verified,
        verify_token="token-scope-123",
        verified_at=datetime.now(timezone.utc),
    )
    run = ScanRun(
        id=uuid.uuid4(),
        app_id=app.id,
        profile=ScanProfile.heartbeat,
        status=RunStatus.done,
        observations_complete=True,
    )
    db_session.add_all([user, org, member, app, target, run])
    await db_session.commit()

    token = create_session_token(settings, str(user.id), user.token_version)
    client.cookies.set(settings.straz_cookie_name, token)

    # 1. Create a key with ONLY ci:runs:read
    read_key_resp = await client.post(
        f"/api/orgs/{org.id}/api-keys",
        headers={"X-Organization-Id": str(org.id), "X-Requested-With": "XMLHttpRequest"},
        json={"name": "Read Only CI Key", "scopes": ["ci:runs:read"]},
    )
    assert read_key_resp.status_code == 201
    read_only_key = read_key_resp.json()["raw_key"]

    client.cookies.clear()

    # 2. ci:runs:read CAN read /api/ci/runs/{run_id} -> 200
    get_resp = await client.get(
        f"/api/ci/runs/{run.id}",
        headers={
            "Authorization": f"Bearer {read_only_key}",
            "X-Organization-Id": str(org.id),
        },
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["run_id"] == str(run.id)

    # 3. ci:runs:read CANNOT trigger /api/ci/scan -> 403 Forbidden
    scan_resp = await client.post(
        "/api/ci/scan",
        headers={
            "Authorization": f"Bearer {read_only_key}",
            "X-Organization-Id": str(org.id),
            "Content-Type": "application/json",
        },
        json={
            "app_id": str(app.id),
            "profile": "heartbeat",
            "fail_on": "high",
            "wait": False,
        },
    )
    assert scan_resp.status_code == 403
