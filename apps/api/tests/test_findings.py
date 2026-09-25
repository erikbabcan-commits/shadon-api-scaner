import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import App, Finding, FindingSeverity, FindingStatus, FindingSource


@pytest.mark.asyncio
async def test_findings_crud_and_overview(auth_client: AsyncClient, db_session: AsyncSession):
    # Setup test app
    app = App(
        id=uuid.uuid4(),
        name="Security Target",
        base_url="https://sec.example.com",
    )
    db_session.add(app)
    await db_session.flush()

    # Add findings
    f1 = Finding(
        id=uuid.uuid4(),
        app_id=app.id,
        source=FindingSource.heartbeat,
        severity=FindingSeverity.high,
        title="App down",
        fingerprint="fp1",
        status=FindingStatus.open,
    )
    f2 = Finding(
        id=uuid.uuid4(),
        app_id=app.id,
        source=FindingSource.tls,
        severity=FindingSeverity.medium,
        title="Certificate expires in 5 days",
        fingerprint="fp2",
        status=FindingStatus.open,
    )
    db_session.add_all([f1, f2])
    await db_session.commit()

    # 1. List findings
    resp = await auth_client.get("/api/findings")
    assert resp.status_code == 200
    findings = resp.json()
    assert len(findings) == 2

    # 2. Filter findings
    resp_filtered = await auth_client.get("/api/findings?status_filter=open")
    assert resp_filtered.status_code == 200
    assert len(resp_filtered.json()) == 2

    # 3. Update finding status
    patch_resp = await auth_client.patch(
        f"/api/findings/{f1.id}",
        json={"status": "accepted"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "accepted"

    # 4. Overview endpoint
    ov_resp = await auth_client.get("/api/overview")
    assert ov_resp.status_code == 200
    ov_data = ov_resp.json()
    assert len(ov_data["apps"]) >= 1
    assert "medium" in ov_data["open_by_severity"]
    assert ov_data["certs_expiring_soon"] == 1
