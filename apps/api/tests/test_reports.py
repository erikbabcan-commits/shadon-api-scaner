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
    # Stored findings are observations, not coverage or an overall security grade.
    assert comp_data["scoring"]["score"] is None
    assert comp_data["scoring"]["grade"] is None
    assert comp_data["compliance_claimed"] is False
    assert comp_data["coverage"] == "not_verified"
    assert comp_data["scoring"]["open_counts"]["critical"] == 1
    assert comp_data["scoring"]["open_counts"]["medium"] == 1
    assert comp_data["scoring"]["open_counts"]["total"] == 2
    assert comp_data["evidence_limits"]
    assert len(comp_data["nis2_readiness"]) == 4
    assert all(area["compliance_claimed"] is False for area in comp_data["nis2_readiness"])

    # 2. Get HTML report
    html_resp = await client.get(
        f"/api/apps/{app.id}/report/html",
        headers={"X-Organization-Id": str(org.id)},
    )
    assert html_resp.status_code == 200
    assert "text/html" in html_resp.headers["content-type"]
    assert "Technický bezpečnostný prehľad" in html_resp.text
    assert "Zhoda neposúdená" in html_resp.text
    assert "posúdenie zhody NIS2" not in html_resp.text
    assert "Celkový bezpečnostný index" not in html_resp.text
    assert "SQL Injection Vulnerability" in html_resp.text
    assert "report-sha256" in html_resp.text


@pytest.mark.parametrize("last_up", [None, True, False])
def test_empty_findings_and_heartbeat_never_produce_security_grade(last_up):
    from app.services.compliance import calculate_security_score, evaluate_nis2_areas

    app = App(last_up=last_up)
    scoring = calculate_security_score([], app)
    assert scoring["score"] is None and scoring["grade"] is None
    assert scoring["open_counts"]["total"] == 0
    assert scoring["status"] == "not_assessed"
    areas = evaluate_nis2_areas([], app)
    assert all(area["status"] not in ("COMPLIANT", "NON-COMPLIANT") for area in areas)
    assert all(area["compliance_claimed"] is False for area in areas)
    assert areas[-1]["issues_count"] == int(last_up is False)
    if last_up is not None:
        assert "bodové pozorovanie" in areas[-1]["evidence_note"]


def test_resolved_findings_do_not_create_perfect_score_or_open_observations():
    from app.services.compliance import calculate_security_score, evaluate_nis2_areas

    finding = Finding(
        source=FindingSource.tls,
        severity=FindingSeverity.critical,
        title="TLS certificate expired",
        status=FindingStatus.fixed,
    )
    scoring = calculate_security_score([finding], App(last_up=True))
    assert scoring["score"] is None and scoring["grade"] is None
    assert scoring["open_counts"]["total"] == 0
    assert all(area["issues_count"] == 0 for area in evaluate_nis2_areas([finding]))


def test_white_label_report_cannot_hide_evidence_limits_or_claim_empty_scan_success():
    from app.services.reporting import generate_html_report

    app = App(id=uuid.uuid4(), name="Unscanned <application>", base_url="https://example.invalid", environment="prod", last_up=True)
    org = Organization(id=uuid.uuid4(), name="Custom org", plan_tier="pro", report_footer_text="Custom agency footer")
    report = generate_html_report(app, org, [])
    assert "Custom agency footer" in report
    assert "Zhoda neposúdená" in report
    assert "Tento prehľad neposudzuje zhodu s NIS2 alebo ISO 27001" in report
    assert "Technický report nie je certifikáciou ani právnym posúdením zhody." in report
    assert "Neznamená to, že kontroly prebehli" in report
    assert "Unscanned &lt;application&gt;" in report
    assert "A+" not in report
    assert "100 %" not in report
    assert "NON-COMPLIANT" not in report and "COMPLIANT" not in report
    assert "Hash metadát reportu (nie podpis ani hash celého obsahu)" in report


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
