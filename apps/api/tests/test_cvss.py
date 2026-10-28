import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models import App, Finding, FindingSeverity, FindingSource, FindingStatus, Organization, User, OrgRole
from app.services.cvss import (
    calculate_cvss,
    calculate_cvss_pure,
    parse_cvss_vector,
    build_vector_string,
    severity_from_score,
)
from app.services.findings import upsert_finding


def test_cvss_standard_vectors():
    # 1. Critical (e.g. Log4Shell / unauthenticated RCE)
    score, sev, vec = calculate_cvss("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H")
    assert score == 9.8
    assert sev == "critical"
    assert "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H" in vec

    # 2. High with Scope Changed (e.g. VM / container escape or SSRF to cloud metadata)
    score, sev, vec = calculate_cvss("CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:N/A:N")
    assert score == 7.7
    assert sev == "high"

    # 3. Medium (e.g. Stored XSS)
    score, sev, vec = calculate_cvss("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N")
    assert score == 6.1
    assert sev == "medium"

    # 4. Low
    score, sev, vec = calculate_cvss("CVSS:3.1/AV:L/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N")
    assert score == 1.8
    assert sev == "low"

    # 5. Zero / Info
    score, sev, vec = calculate_cvss("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N")
    assert score == 0.0
    assert sev == "info"


def test_pure_calculator_matches_spec():
    vector = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
    breakdown = parse_cvss_vector(vector)
    score_p, sev_p, vec_p = calculate_cvss_pure(breakdown)
    assert score_p == 9.8
    assert sev_p == "critical"
    assert vec_p == vector


def test_breakdown_parsing_and_normalization():
    # Test lowercase and mixed shorthand/longhand
    raw = {
        "AV": "n",
        "attack_complexity": "l",
        "PR": "n",
        "user_interaction": "n",
        "S": "u",
        "confidentiality": "h",
        "integrity": "h",
        "availability": "h",
    }
    score, sev, vec = calculate_cvss(raw)
    assert score == 9.8
    assert sev == "critical"


def test_invalid_vector_raises():
    with pytest.raises(ValueError):
        parse_cvss_vector("CVSS:2.0/AV:N")

    with pytest.raises(ValueError):
        calculate_cvss({"attack_vector": "INVALID"})


@pytest.mark.asyncio
async def test_upsert_finding_with_cvss_and_poc(db_session: AsyncSession):
    # Setup test org and app
    org = Organization(name="CVSS Test Org", slug=f"cvss-org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    app_obj = App(
        organization_id=org.id,
        name="Test App",
        environment="staging",
        base_url="https://staging.test",
    )
    db_session.add(app_obj)
    await db_session.flush()

    finding = await upsert_finding(
        db_session,
        app_id=app_obj.id,
        target_id=None,
        source=FindingSource.nuclei,
        severity=FindingSeverity.critical,
        title="SQL Injection in auth endpoint",
        detail="Vulnerable parameter 'id'",
        fingerprint="fp-sqli-001",
        cvss_score=9.8,
        cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        poc_command="curl -X POST https://api.test/login -d \"user=' OR 1=1--\"",
        remediation_patch="--- a/auth.py\n+++ b/auth.py\n- query = f'SELECT * FROM users WHERE id={id}'\n+ query = select(User).where(User.id == id)",
    )
    await db_session.commit()

    assert finding.cvss_score == 9.8
    assert finding.cvss_vector == "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
    assert "curl" in (finding.poc_command or "")
    assert "select(User)" in (finding.remediation_patch or "")


@pytest.mark.asyncio
async def test_cvss_and_poc_api_endpoints(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    from sqlalchemy import select
    from app.models import OrganizationMember
    org_id = await db_session.scalar(
        select(OrganizationMember.org_id).where(OrganizationMember.user_id == test_user.id)
    )

    app_obj = App(
        organization_id=org_id,
        name="Sec App",
        environment="production",
        base_url="https://sec.test",
    )
    db_session.add(app_obj)
    await db_session.flush()

    finding = Finding(
        app_id=app_obj.id,
        source=FindingSource.nuclei,
        severity=FindingSeverity.high,
        title="IDOR vulnerability",
        detail="User can view other users records",
        fingerprint="fp-idor-001",
        cvss_score=7.5,
        cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
        poc_command="curl -H 'Authorization: Bearer test' https://api.test/users/42",
        remediation_patch="--- a/users.py\n+++ b/users.py\n+ verify_ownership(current_user, user_id)",
    )
    db_session.add(finding)
    await db_session.commit()

    headers = {"X-Organization-Id": str(org_id)}

    # 1. Test CVSS calculate endpoint with vector
    resp = await auth_client.post(
        "/api/findings/cvss/calculate",
        json={"vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["score"] == 9.8
    assert data["severity"] == "critical"
    assert data["breakdown"]["attack_vector"] == "N"

    # 2. Test get finding returns CVSS and PoC fields
    resp = await auth_client.get(f"/api/findings/{finding.id}", headers=headers)
    assert resp.status_code == 200
    fdata = resp.json()
    assert fdata["cvss_score"] == 7.5
    assert fdata["cvss_vector"] == "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N"
    assert "curl" in (fdata["poc_command"] or "")
    assert "verify_ownership" in (fdata["remediation_patch"] or "")

    # 3. Test patch finding updates CVSS score and PoC
    resp = await auth_client.patch(
        f"/api/findings/{finding.id}",
        json={
            "cvss_score": 8.6,
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:L/A:L",
            "poc_command": "curl -X POST https://api.test/exploit",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    pdata = resp.json()
    assert pdata["cvss_score"] == 8.6
    assert pdata["cvss_vector"] == "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:L/A:L"
    assert pdata["poc_command"] == "curl -X POST https://api.test/exploit"

    # 4. Test PoC verification endpoint
    resp = await auth_client.post(
        f"/api/findings/{finding.id}/verify-poc",
        json={"curl_command": "curl -s -i https://api.test/health"},
        headers=headers,
    )
    assert resp.status_code == 200
    vdata = resp.json()
    assert vdata["verified"] is True
    assert vdata["status_code"] == 200
    assert "curl -s -i https://api.test/health" in vdata["output"]
