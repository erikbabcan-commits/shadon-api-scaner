from __future__ import annotations

from typing import Any


from app.models import App, Finding, FindingSeverity, FindingStatus


EVIDENCE_LIMITS = (
    "Počty nálezov opisujú iba uložené technické pozorovania; nulový počet nepreukazuje bezpečnosť.",
    "Úplnosť, aktuálnosť a úspešné vykonanie všetkých potrebných kontrol nie sú overené.",
    "Dostupnosť URL v jednom okamihu nepreukazuje kontinuitu, pripravenosť na incidenty ani účinnosť procesov.",
    "Tento prehľad neposudzuje zhodu s NIS2 alebo ISO 27001 a nie je certifikáciou.",
)


def calculate_security_score(findings: list[Finding], app: App | None = None) -> dict[str, Any]:
    """Return observations without inventing an overall security grade.

    Persisted findings and the latest heartbeat do not establish scan coverage,
    freshness, or organizational controls. Keep the legacy score/grade keys
    nullable so callers can distinguish missing assessment from a perfect score.
    """
    open_findings = [f for f in findings if f.status == FindingStatus.open]
    counts = {
        severity.value: sum(f.severity == severity for f in open_findings)
        for severity in FindingSeverity
    }
    counts["total"] = len(open_findings)
    availability = "unknown"
    if app is not None and app.last_up is not None:
        availability = "reachable" if app.last_up else "unreachable"

    return {
        "score": None,
        "grade": None,
        "color": "#64748b",
        "forced_f": False,
        "status": "not_assessed",
        "coverage": "not_verified",
        "compliance_claimed": False,
        "open_counts": counts,
        "availability_observation": availability,
        "evidence_limits": list(EVIDENCE_LIMITS),
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
    """Group technical observations by topic; never infer legal compliance.

    The legacy endpoint/field names are retained for API compatibility. Keyword
    mapping is only a navigation aid, not evidence that a control was assessed.
    """
    open_findings = [f for f in findings if f.status == FindingStatus.open]
    topics = (
        (
            "nis2_net_crypto",
            "Sieťové a kryptografické pozorovania",
            ("tls", "ssl", "certificate", "rdap", "dns", "crypto", "https"),
        ),
        (
            "nis2_vuln_mgmt",
            "Pozorovania zraniteľností a expozícií",
            ("nuclei", "port", "internetdb", "shodan", "injection", "xss"),
        ),
        (
            "nis2_supply_chain",
            "Pozorovania dodávateľského reťazca a kódu",
            ("trivy", "cve", "gitleaks", "secret", "sast", "package"),
        ),
    )
    areas = []
    for area_id, name, keywords in topics:
        related = [
            finding for finding in open_findings
            if any(word in (
                f"{finding.title or ''} {finding.detail or ''} "
                f"{getattr(finding.source, 'value', finding.source)}"
            ).lower() for word in keywords)
        ]
        areas.append({
            "id": area_id,
            "name": name,
            "iso_ref": "NIS2 / ISO 27001: orientačná tematická súvislosť",
            "status": "OBSERVATIONS_PRESENT" if related else "NOT_ASSESSED",
            "issues_count": len(related),
            "compliance_claimed": False,
            "evidence_note": (
                "Orientačné zaradenie uložených otvorených nálezov podľa textu a zdroja; "
                "nejde o posúdenie požiadaviek ani úplnosti kontrol."
            ),
        })

    unavailable = app is not None and app.last_up is False
    availability_note = "Nie je uložené pozorovanie dostupnosti."
    if app is not None and app.last_up is not None:
        availability_note = (
            "Posledné bodové pozorovanie URL: "
            + ("dostupná." if app.last_up else "nedostupná.")
            + " Neoveruje kontinuitu, incidentné procesy ani aktuálny stav služby."
        )
    areas.append({
        "id": "nis2_availability",
        "name": "Bodové pozorovanie dostupnosti",
        "iso_ref": "NIS2 / ISO 27001: orientačná tematická súvislosť",
        "status": "OBSERVATIONS_PRESENT" if unavailable else "NOT_ASSESSED",
        "issues_count": int(unavailable),
        "compliance_claimed": False,
        "evidence_note": availability_note,
    })
    return areas
