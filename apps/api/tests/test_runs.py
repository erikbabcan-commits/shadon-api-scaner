import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import App, ScanProfile, Target, TargetStatus


@pytest.mark.asyncio
@pytest.mark.usefixtures("allow_cli_profiles")
async def test_run_creation_and_validation(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    from sqlalchemy import select
    from app.models import OrganizationMember
    org_id = await db_session.scalar(select(OrganizationMember.org_id).where(OrganizationMember.user_id == test_user.id))
    # Setup test app
    app = App(
        id=uuid.uuid4(),
        organization_id=org_id,
        name="Scanned App",
        base_url="https://scanned.example.com",
        heartbeat_enabled=True,
        tls_enabled=True,
    )
    target = Target(
        id=uuid.uuid4(),
        app_id=app.id,
        host="scanned.example.com",
        status=TargetStatus.pending,
        verify_token="test-token",
    )
    db_session.add_all([app, target])
    await db_session.commit()

    # 1. Heartbeat scan is allowed even without verified target
    resp_hb = await auth_client.post(
        f"/api/apps/{app.id}/runs",
        json={"profile": "heartbeat"},
    )
    assert resp_hb.status_code == 201
    assert resp_hb.json()["profile"] == "heartbeat"
    assert resp_hb.json()["status"] == "queued"

    # 2. TLS scan is rejected because target is pending (not verified)
    resp_tls_unverified = await auth_client.post(
        f"/api/apps/{app.id}/runs",
        json={"profile": "tls"},
    )
    assert resp_tls_unverified.status_code == 400
    assert "No verified targets" in resp_tls_unverified.json()["detail"]

    # 3. Verify target
    target.status = TargetStatus.verified
    await db_session.commit()

    # 4. TLS scan now succeeds
    resp_tls_verified = await auth_client.post(
        f"/api/apps/{app.id}/runs",
        json={"profile": "tls"},
    )
    assert resp_tls_verified.status_code == 201
    assert resp_tls_verified.json()["profile"] == "tls"

    # 5. List runs
    list_resp = await auth_client.get(f"/api/runs?app_id={app.id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 2
