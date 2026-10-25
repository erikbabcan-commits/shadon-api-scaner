from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import App, Finding, FindingSeverity, FindingStatus


def calculate_security_score(findings: list[Finding], app: App | None = None) -> dict[str, Any]:
    score = 100
    forced_f = False
    open_findings = [f for f in findings if f.status == FindingStatus.open]

    crit_count = 0
    high_count = 0
    med_count = 0
    low_count = 0
    info_count = 0
    expiry_penalty = 0

    for f in open_findings:
        title_lower = (f.title or "").lower()
        detail_lower = (f.detail or "").lower()

        # Check for expired SSL or expired domain
        if "expired" in title_lower or "expired" in detail_lower:
            forced_f = True

        # Check for expiry within 21 days
        if "expir" in title_lower or "expir" in detail_lower:
            expiry_penalty += 10

        if f.severity == FindingSeverity.critical:
            crit_count += 1
            score -= 35
        elif f.severity == FindingSeverity.high:
            high_count += 1
            score -= 15
        elif f.severity == FindingSeverity.medium:
            med_count += 1
            score -= 5
        elif f.severity == FindingSeverity.low:
            low_count += 1
        elif f.severity == FindingSeverity.info:
            info_count += 1

    score -= expiry_penalty

    # Check if app is down
    if app and app.last_up is False:
        forced_f = True

    if forced_f:
        score = min(score, 39)

    score = max(0, min(100, score))

    if score >= 95:
        grade = "A+"
        color = "#10b981" # Emerald
    elif score >= 85:
        grade = "A"
        color = "#22c55e" # Green
    elif score >= 75:
        grade = "B"
        color = "#0ea5e9" # Sky
    elif score >= 60:
        grade = "C"
        color = "#eab308" # Yellow
    elif score >= 40:
        grade = "D"
        color = "#f97316" # Orange
    else:
        grade = "F"
        color = "#ef4444" # Red

    return {
        "score": score,
        "grade": grade,
        "color": color,
        "forced_f": forced_f,
        "open_counts": {
            "critical": crit_count,
            "high": high_count,
            "medium": med_count,
            "low": low_count,
            "info": info_count,
            "total": len(open_findings),
        },
    }


def map_owasp_top_10(findings: list[Finding]) -> dict[str, int]:
    categories = {
        "A01: Broken Access Control": 0,
        "A02: Cryptographic Failures": 0,
        "A03: Injection / Flaws": 0,
        "A05: Security Misconfiguration": 0,
        "A06: Vulnerable and Outdated Components": 0,
        "A07: Identification and Authentication Failures": 0,
        "Other / Unmapped": 0,
    }

    for f in findings:
        if f.status != FindingStatus.open:
            continue
        text = f"{f.title} {f.detail or ''} {f.source.value if hasattr(f.source, 'value') else f.source}".lower()

        if any(w in text for w in ["access", "unauthorized", "cors", "traversal", "authz"]):
            categories["A01: Broken Access Control"] += 1
        elif any(w in text for w in ["tls", "ssl", "certificate", "cipher", "crypto", "https"]):
            categories["A02: Cryptographic Failures"] += 1
        elif any(w in text for w in ["sqli", "injection", "xss", "rce", "command"]):
            categories["A03: Injection / Flaws"] += 1
        elif any(w in text for w in ["header", "misconfig", "port", "naabu", "internetdb", "exposure"]):
            categories["A05: Security Misconfiguration"] += 1
        elif any(w in text for w in ["cve", "trivy", "vulnerability", "outdated", "package"]):
            categories["A06: Vulnerable and Outdated Components"] += 1
        elif any(w in text for w in ["secret", "gitleaks", "token", "password", "key", "credential"]):
            categories["A07: Identification and Authentication Failures"] += 1
        else:
            categories["Other / Unmapped"] += 1

    return categories


def evaluate_nis2_areas(findings: list[Finding], app: App | None = None) -> list[dict[str, Any]]:
    open_findings = [f for f in findings if f.status == FindingStatus.open]

    # Area 1: Network & Cryptographic Security
    area1_findings = [
        f for f in open_findings
        if any(w in (f.title or "").lower() for w in ["tls", "ssl", "certificate", "rdap", "dns"])
    ]
    area1_status = "NON-COMPLIANT" if any(f.severity in (FindingSeverity.critical, FindingSeverity.high) for f in area1_findings) else ("WARNING" if area1_findings else "COMPLIANT")

    # Area 2: Vulnerability Management
    area2_findings = [
        f for f in open_findings
        if any(w in (f.title or "").lower() for w in ["nuclei", "port", "internetdb", "shodan"])
    ]
    area2_status = "NON-COMPLIANT" if any(f.severity in (FindingSeverity.critical, FindingSeverity.high) for f in area2_findings) else ("WARNING" if area2_findings else "COMPLIANT")

    # Area 3: Supply Chain Security
    area3_findings = [
        f for f in open_findings
        if any(w in (f.title or "").lower() for w in ["trivy", "cve", "gitleaks", "secret", "sast"])
    ]
    area3_status = "NON-COMPLIANT" if any(f.severity in (FindingSeverity.critical, FindingSeverity.high) for f in area3_findings) else ("WARNING" if area3_findings else "COMPLIANT")

    # Area 4: Availability & Incident Monitoring
    area4_status = "NON-COMPLIANT" if (app and app.last_up is False) else "COMPLIANT"

    return [
        {
            "id": "nis2_net_crypto",
            "name": "Sieťová a kryptografická bezpečnosť (Článok 21 ods. 2 písm. a)",
            "iso_ref": "ISO/IEC 27001:2022 A.8.20, A.8.24",
            "status": area1_status,
            "issues_count": len(area1_findings),
        },
        {
            "id": "nis2_vuln_mgmt",
            "name": "Riadenie zraniteľností a expozícií (Článok 21 ods. 2 písm. e)",
            "iso_ref": "ISO/IEC 27001:2022 A.8.8",
            "status": area2_status,
            "issues_count": len(area2_findings),
        },
        {
            "id": "nis2_supply_chain",
            "name": "Bezpečnosť dodávateľského reťazca a kódu (Článok 21 ods. 2 písm. d)",
            "iso_ref": "ISO/IEC 27001:2022 A.5.19, A.8.28",
            "status": area3_status,
            "issues_count": len(area3_findings),
        },
        {
            "id": "nis2_availability",
            "name": "Kontinuita činností a incident monitoring (Článok 21 ods. 2 písm. c)",
            "iso_ref": "ISO/IEC 27001:2022 A.8.16, A.8.26",
            "status": area4_status,
            "issues_count": 0 if area4_status == "COMPLIANT" else 1,
        },
    ]
