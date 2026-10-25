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
    User,
)
from app.security import create_session_token, hash_password


@pytest.mark.asyncio
async def test_compliance_and_report_generation(
    client: AsyncClient, db_session: AsyncSession
):
    settings = get_settings()

    user = User(
        id=uuid.uuid4(),
        email="auditor@example.com",
        password_hash=hash_password("AuditPass123!"),
        token_version=1,
    )
    org = Organization(
        id=uuid.uuid4(),
        name="Security Audit Org",
        slug="audit-org",
        plan_tier="pro",
    )
    m = OrganizationMember(
        id=uuid.uuid4(), org_id=org.id, user_id=user.id, role=OrgRole.owner
    )
    app = App(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Audit Target App",
        base_url="https://audit.example.com",
        environment="prod",
        last_up=True,
    )
    db_session.add_all([user, org, m, app])
    await db_session.flush()

    # Add findings
    f1 = Finding(
        id=uuid.uuid4(),
        app_id=app.id,
        source=FindingSource.nuclei,
        severity=FindingSeverity.critical,
        title="SQL Injection Vulnerability",
        fingerprint="fp-sqli",
        status=FindingStatus.open,
    )
    f2 = Finding(
        id=uuid.uuid4(),
        app_id=app.id,
        source=FindingSource.tls,
        severity=FindingSeverity.medium,
        title="Weak TLS Cipher Suite",
        fingerprint="fp-tls",
        status=FindingStatus.open,
    )
    db_session.add_all([f1, f2])
    await db_session.commit()

    token = create_session_token(settings, str(user.id), user.token_version)
    client.cookies.set(settings.straz_cookie_name, token)

    # 1. Get compliance JSON
    comp_resp = await client.get(
        f"/api/apps/{app.id}/compliance",
        headers={"X-Organization-Id": str(org.id)},
    )
    assert comp_resp.status_code == 200
    comp_data = comp_resp.json()
    assert comp_data["app_name"] == "Audit Target App"
    # 100 - 35 (crit) - 5 (med) = 60
    assert comp_data["scoring"]["score"] == 60
    assert comp_data["scoring"]["grade"] == "C"
    assert len(comp_data["nis2_readiness"]) == 4

    # 2. Get HTML report
    html_resp = await client.get(
        f"/api/apps/{app.id}/report/html",
        headers={"X-Organization-Id": str(org.id)},
    )
    assert html_resp.status_code == 200
    assert "text/html" in html_resp.headers["content-type"]
    assert "Executive Security Audit" in html_resp.text
    assert "SQL Injection Vulnerability" in html_resp.text
    assert "report-sha256" in html_resp.text


@pytest.mark.asyncio
async def test_branding_tier_gating(
    client: AsyncClient, db_session: AsyncSession
):
    settings = get_settings()

    # Free org user
    user = User(
        id=uuid.uuid4(),
        email="freebrand@example.com",
        password_hash=hash_password("Pass123!"),
        token_version=1,
    )
    org = Organization(
        id=uuid.uuid4(),
        name="Free Branding Org",
        slug="free-brand",
        plan_tier="free",
    )
    m = OrganizationMember(
        id=uuid.uuid4(), org_id=org.id, user_id=user.id, role=OrgRole.owner
    )
    db_session.add_all([user, org, m])
    await db_session.commit()

    token = create_session_token(settings, str(user.id), user.token_version)
    client.cookies.set(settings.straz_cookie_name, token)

    # Free tier cannot update branding -> 402 Payment Required
    resp = await client.patch(
        f"/api/orgs/{org.id}/branding",
        headers={"X-Organization-Id": str(org.id)},
        json={"brand_color": "#ff0000", "report_footer_text": "Agency footer"},
    )
    assert resp.status_code == 402
    assert resp.headers.get("x-upgrade-required") == "true"

    # Upgrade org to Pro
    org.plan_tier = "pro"
    await db_session.commit()

    # Now branding update succeeds
    resp_pro = await client.patch(
        f"/api/orgs/{org.id}/branding",
        headers={"X-Organization-Id": str(org.id)},
        json={"brand_color": "#ff0000", "report_footer_text": "Pro agency footer"},
    )
    assert resp_pro.status_code == 200
    assert resp_pro.json()["brand_color"] == "#ff0000"
    assert resp_pro.json()["report_footer_text"] == "Pro agency footer"
