import json
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import App, Finding, FindingSeverity, FindingSource, FindingStatus, User
from app.services.reporting import csv_safe, generate_csv_report
from app.services.sarif import build_sarif_report


def test_csv_safe_formula_neutralization():
    assert csv_safe("=1+1") == "'=1+1"
    assert csv_safe("+1+1") == "'+1+1"
    assert csv_safe("-1+1") == "'-1+1"
    assert csv_safe("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert csv_safe("\tcmd") == "'\tcmd"
    assert csv_safe("Safe text string") == "Safe text string"
    assert csv_safe(None) == ""


def test_sarif_builder_structure():
    app = App(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        name="Test Target",
        base_url="https://target.test",
        git_url="https://github.com/org/repo",
    )
    finding = Finding(
        id=uuid.uuid4(),
        app_id=app.id,
        source=FindingSource.nuclei,
        severity=FindingSeverity.critical,
        title="SQL Injection in /api/v1/users (CWE-89)",
        detail="Vulnerable param 'id'",
        fingerprint="fp-sqli-sarif-123",
        status=FindingStatus.open,
        cvss_score=9.8,
        cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        poc_command="curl -X POST https://target.test/api/v1/users -d 'id=1 OR 1=1'",
        remediation_patch="--- a/repo.py\n+++ b/repo.py\n- sql = f'SELECT * FROM u WHERE id={id}'\n+ sql = select(User).where(User.id == id)",
    )

    doc = build_sarif_report([finding], app=app)

    # 1. Root structure
    assert doc["version"] == "2.1.0"
    assert "$schema" in doc
    assert len(doc["runs"]) == 1

    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "Stráž"
    assert len(run["tool"]["driver"]["rules"]) == 1

    # 2. Rule validation
    rule = run["tool"]["driver"]["rules"][0]
    assert rule["id"] == "CWE-89"
    assert rule["properties"]["security-severity"] == "9.8"
    assert "external/cwe/cwe-89" in rule["properties"]["tags"]
    assert "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H" in rule["help"]["markdown"]
    assert "curl -X POST" in rule["help"]["markdown"]

    # 3. Result validation
    assert len(run["results"]) == 1
    result = run["results"][0]
    assert result["ruleId"] == "CWE-89"
    assert result["level"] == "error"
    assert "primaryLocationLineHash" in result["partialFingerprints"]
    assert result["properties"]["straz"]["cvss_score"] == 9.8
    assert result["properties"]["straz"]["has_poc"] is True
    assert result["properties"]["straz"]["has_patch"] is True
    assert len(result["fixes"]) == 1


@pytest.mark.asyncio
async def test_sarif_and_csv_export_endpoints(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    from sqlalchemy import select
    from app.models import OrganizationMember

    org_id = await db_session.scalar(
        select(OrganizationMember.org_id).where(OrganizationMember.user_id == test_user.id)
    )

    app_obj = App(
        organization_id=org_id,
        name="Export App",
        environment="production",
        base_url="https://export.test",
    )
    db_session.add(app_obj)
    await db_session.flush()

    finding = Finding(
        app_id=app_obj.id,
        source=FindingSource.nuclei,
        severity=FindingSeverity.high,
        title="Reflected XSS in search (CWE-79)",
        detail="q parameter not sanitized",
        fingerprint="fp-xss-export-999",
        status=FindingStatus.open,
        cvss_score=7.1,
        cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N",
        poc_command="curl 'https://export.test/search?q=<script>alert(1)</script>'",
        remediation_patch="--- a/views.py\n+++ b/views.py\n+ html.escape(query)",
    )
    db_session.add(finding)
    await db_session.commit()

    headers = {"X-Organization-Id": str(org_id)}

    # 1. Test app SARIF report endpoint
    resp = await auth_client.get(f"/api/apps/{app_obj.id}/report/sarif", headers=headers)
    assert resp.status_code == 200
    assert "application/sarif+json" in resp.headers.get("content-type", "")
    data = resp.json()
    assert data["version"] == "2.1.0"
    assert len(data["runs"][0]["results"]) == 1
    assert data["runs"][0]["results"][0]["ruleId"] == "CWE-79"

    # 2. Test app CSV report endpoint
    resp = await auth_client.get(f"/api/apps/{app_obj.id}/report/csv", headers=headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    csv_text = resp.text
    assert "Reflected XSS" in csv_text
    assert "7.1" in csv_text
    assert "CWE-79" in csv_text

    # 3. Test org-wide SARIF export
    resp = await auth_client.get("/api/findings/export/sarif", headers=headers)
    assert resp.status_code == 200
    sarif_org = resp.json()
    assert len(sarif_org["runs"][0]["results"]) >= 1

    # 4. Test org-wide CSV export
    resp = await auth_client.get("/api/findings/export/csv", headers=headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    assert "Reflected XSS" in resp.text
