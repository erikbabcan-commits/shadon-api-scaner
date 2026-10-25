import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AuditEvent, Organization, OrganizationMember, OrgRole, User
from app.security import create_session_token, hash_password
from app.services.audit import sanitize_audit_details, write_audit_log


@pytest.mark.asyncio
async def test_audit_log_redaction_and_persistence(db_session: AsyncSession):
    org_id = uuid.uuid4()
    details_with_secrets = {
        "user_email": "auditor@example.com",
        "password": "SuperSecretPassword123!",
        "api_key": "straz_live_a1b2c3d4e5f6g7h8",
        "nested": {
            "token": "secret_token_val",
            "safe_property": "production_environment",
        },
    }

    event = await write_audit_log(
        db_session,
        action="app.create",
        org_id=org_id,
        actor_email="admin@example.com",
        details=details_with_secrets,
    )
    await db_session.commit()
    await db_session.refresh(event)

    assert event.action == "app.create"
    assert event.details["password"] == "[REDACTED]"
    assert event.details["api_key"] == "[REDACTED]"
    assert event.details["nested"]["token"] == "[REDACTED]"
    assert event.details["nested"]["safe_property"] == "production_environment"


@pytest.mark.asyncio
async def test_audit_log_query_and_csv_export(client: AsyncClient, db_session: AsyncSession):
    settings = get_settings()

    user = User(
        id=uuid.uuid4(),
        email="compliance-officer@example.com",
        password_hash=hash_password("Pass123!"),
        token_version=1,
    )
    org = Organization(
        id=uuid.uuid4(),
        name="Enterprise Audit Co",
        slug="enterprise-audit",
        plan_tier="pro",
    )
    member = OrganizationMember(
        id=uuid.uuid4(),
        org_id=org.id,
        user_id=user.id,
        role=OrgRole.owner,
    )
    db_session.add_all([user, org, member])
    await db_session.commit()

    # Create several audit events, including a formula injection test string
    await write_audit_log(
        db_session,
        action="target.verify",
        org_id=org.id,
        actor_email="compliance-officer@example.com",
        entity_type="target",
        entity_id="=cmd|' /C calc'!A0",  # CSV injection payload
        ip_address="192.168.1.100",
        user_agent="Mozilla/5.0 TestBrowser",
    )
    await write_audit_log(
        db_session,
        action="scan.trigger",
        org_id=org.id,
        actor_email="compliance-officer@example.com",
        entity_type="scan_run",
        entity_id="run-1234",
    )
    await db_session.commit()

    token = create_session_token(settings, str(user.id), user.token_version)
    client.cookies.set(settings.straz_cookie_name, token)

    # 1. Query audit events (JSON)
    resp = await client.get(
        f"/api/orgs/{org.id}/audit-logs",
        headers={"X-Organization-Id": str(org.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    actions = [item["action"] for item in data["items"]]
    assert "target.verify" in actions
    assert "scan.trigger" in actions

    # 2. Filter by action
    resp_filter = await client.get(
        f"/api/orgs/{org.id}/audit-logs?action=target.verify",
        headers={"X-Organization-Id": str(org.id)},
    )
    assert resp_filter.status_code == 200
    filtered_data = resp_filter.json()
    assert filtered_data["total"] == 1
    assert filtered_data["items"][0]["action"] == "target.verify"

    # 3. Export CSV with Formula Injection verification
    resp_csv = await client.get(
        f"/api/orgs/{org.id}/audit-logs/export.csv",
        headers={"X-Organization-Id": str(org.id)},
    )
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers["content-type"]
    assert "attachment;" in resp_csv.headers["content-disposition"]
    csv_text = resp_csv.text
    assert "Timestamp (UTC)" in csv_text
    assert "compliance-officer@example.com" in csv_text
    # Cell starting with '=' must be prefixed with single quote "'"
    assert "'=cmd|' /C calc'!A0" in csv_text


@pytest.mark.asyncio
async def test_member_role_update_and_audit(client: AsyncClient, db_session: AsyncSession):
    settings = get_settings()

    owner = User(
        id=uuid.uuid4(),
        email="owner@example.com",
        password_hash=hash_password("Pass123!"),
        token_version=1,
    )
    member_user = User(
        id=uuid.uuid4(),
        email="junior@example.com",
        password_hash=hash_password("Pass123!"),
        token_version=1,
    )
    org = Organization(
        id=uuid.uuid4(),
        name="Team Roles Corp",
        slug="team-roles",
        plan_tier="pro",
    )
    m_owner = OrganizationMember(
        id=uuid.uuid4(), org_id=org.id, user_id=owner.id, role=OrgRole.owner
    )
    m_member = OrganizationMember(
        id=uuid.uuid4(), org_id=org.id, user_id=member_user.id, role=OrgRole.member
    )
    db_session.add_all([owner, member_user, org, m_owner, m_member])
    await db_session.commit()

    token = create_session_token(settings, str(owner.id), owner.token_version)
    client.cookies.set(settings.straz_cookie_name, token)

    # Promote member to admin
    patch_resp = await client.patch(
        f"/api/orgs/{org.id}/members/{member_user.id}",
        headers={"X-Organization-Id": str(org.id)},
        json={"role": "admin"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["role"] == "admin"

    await db_session.refresh(m_member)
    assert m_member.role == OrgRole.admin


@pytest.mark.asyncio
async def test_observability_healthz_probes(client: AsyncClient):
    # 1. Liveness probe (public)
    live_resp = await client.get("/healthz/liveness")
    assert live_resp.status_code == 200
    live_data = live_resp.json()
    assert live_data["status"] == "ok"
    assert "uptime_seconds" in live_data

    # 2. Readiness probe (public)
    ready_resp = await client.get("/healthz/readiness")
    assert ready_resp.status_code in (200, 503)
    ready_data = ready_resp.json()
    assert "checks" in ready_data
    assert "database" in ready_data["checks"]
    assert "latency_ms" in ready_data["checks"]["database"]


@pytest.mark.asyncio
async def test_audit_immutability_triggers(db_session: AsyncSession):
    await db_session.execute(
        text(
            """
            CREATE TRIGGER IF NOT EXISTS test_prevent_audit_update
            BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'Audit log records are immutable and cannot be updated');
            END;
            """
        )
    )
    await db_session.commit()

    event = await write_audit_log(
        db_session,
        action="app.delete",
        actor_email="admin@example.com",
    )
    await db_session.commit()

    # Attempting to update must fail due to trigger
    with pytest.raises(Exception) as exc_info:
        await db_session.execute(
            text("UPDATE audit_events SET detail='tampered' WHERE id=:eid").bindparams(eid=str(event.id))
        )
        await db_session.commit()
    assert "immutable" in str(exc_info.value).lower()


