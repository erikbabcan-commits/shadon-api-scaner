"""SARIF 2.1.0 output engine for Stráž vulnerability findings.

Ported from STRIX (strix/report/sarif.py).
Fully compatible with OASIS SARIF v2.1.0 and GitHub Code Scanning
(github/codeql-action/upload-sarif, GitLab Security, DefectDojo).
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Sequence

from app.models import Finding, App

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"
TOOL_NAME = "Stráž"
TOOL_INFORMATION_URI = "https://github.com/erikbabcan-commits/shadon-api-scaner"

# Severity mapping to SARIF levels (error, warning, note)
_SEVERITY_TO_LEVEL = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "note",
    "info": "note",
}

# Fallback security-severity string scores (0.0 - 10.0) used by GitHub Code Scanning
_SEVERITY_TO_SCORE = {
    "critical": "9.5",
    "high": "8.0",
    "medium": "5.5",
    "low": "3.0",
    "info": "1.0",
}


def _extract_cwe_id(title: str, detail: str | None) -> str | None:
    """Extract standard CWE-NNN identifier if present."""
    corpus = f"{title} {detail or ''}"
    match = re.search(r"\b(CWE-\d+)\b", corpus, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def _extract_cve_id(title: str, detail: str | None) -> str | None:
    """Extract standard CVE-YYYY-NNNN if present."""
    corpus = f"{title} {detail or ''}"
    match = re.search(r"\b(CVE-\d{4}-\d{4,})\b", corpus, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def _format_help_markdown(finding: Finding, app_name: str | None = None) -> str:
    """Format rich Markdown help description for GitHub Code Scanning UI."""
    lines: list[str] = [
        f"### {finding.title}",
        "",
        f"**Závažnosť (Severity):** {finding.severity.value.upper()}",
    ]
    if finding.cvss_score is not None:
        lines.append(f"**CVSS v3.1 Skóre:** {finding.cvss_score:.1f}")
    if finding.cvss_vector:
        lines.append(f"**CVSS Vektor:** `{finding.cvss_vector}`")
    if finding.source:
        lines.append(f"**Detegované skenerom:** {finding.source.value}")
    if app_name:
        lines.append(f"**Aplikácia:** {app_name}")

    if finding.detail:
        lines.extend(["", "#### Technická analýza & detail", "```", finding.detail.strip(), "```"])

    if finding.poc_command:
        lines.extend([
            "",
            "#### Proof of Concept (curl reprodukcia)",
            "```bash",
            finding.poc_command.strip(),
            "```",
        ])

    if finding.remediation_patch:
        lines.extend([
            "",
            "#### Odporúčaná oprava (Remediation Patch)",
            "```diff",
            finding.remediation_patch.strip(),
            "```",
        ])

    return "\n".join(lines)


def build_sarif_report(
    findings: Sequence[Finding],
    *,
    app: App | None = None,
    tool_version: str = "1.0.0",
) -> dict[str, Any]:
    """Build a complete SARIF 2.1.0 document from a list of Finding records."""
    rules: list[dict[str, Any]] = []
    rule_indices: dict[str, int] = {}
    results: list[dict[str, Any]] = []

    app_name = app.name if app else "Stráž Monitored Target"
    target_uri = (app.base_url if app else "https://straz-monitoring.vercel.app").rstrip("/")

    for finding in findings:
        cwe_id = _extract_cwe_id(finding.title, finding.detail)
        cve_id = _extract_cve_id(finding.title, finding.detail)
        rule_id = cwe_id or cve_id or f"STRAZ-{finding.fingerprint[:8].upper()}"

        # Register rule if not already added
        if rule_id not in rule_indices:
            rule_index = len(rules)
            rule_indices[rule_id] = rule_index

            score_str = (
                f"{finding.cvss_score:.1f}"
                if finding.cvss_score is not None
                else _SEVERITY_TO_SCORE.get(finding.severity.value, "5.0")
            )

            rule: dict[str, Any] = {
                "id": rule_id,
                "name": re.sub(r"[^a-zA-Z0-9_-]", "-", finding.title)[:64],
                "shortDescription": {"text": finding.title[:120]},
                "fullDescription": {"text": (finding.detail or finding.title)[:500]},
                "help": {
                    "text": f"{finding.title}\nSeverity: {finding.severity.value}",
                    "markdown": _format_help_markdown(finding, app_name),
                },
                "properties": {
                    "security-severity": score_str,
                    "tags": [
                        "security",
                        finding.severity.value,
                        finding.source.value if finding.source else "external",
                    ],
                },
            }
            if cwe_id:
                rule["properties"]["tags"].append(f"external/cwe/{cwe_id.lower()}")
            if finding.cvss_vector:
                rule["properties"]["cvssV3Vector"] = finding.cvss_vector

            rules.append(rule)
        else:
            rule_index = rule_indices[rule_id]

        level = _SEVERITY_TO_LEVEL.get(finding.severity.value, "warning")

        # Determine finding location
        location_uri = "SECURITY.md"
        locations: list[dict[str, Any]] = [
            {
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": location_uri,
                        "uriBaseId": "%SRCROOT%",
                    },
                    "region": {
                        "startLine": 1,
                        "startColumn": 1,
                    },
                },
                "logicalLocations": [
                    {
                        "name": app_name,
                        "fullyQualifiedName": f"{target_uri}#{finding.title}",
                        "kind": "endpoint",
                    }
                ],
            }
        ]

        # Deterministic partial fingerprint for alert tracking across commits
        fp_hash = hashlib.sha256(
            f"{finding.app_id}:{finding.fingerprint}:{rule_id}".encode("utf-8")
        ).hexdigest()[:32]

        result: dict[str, Any] = {
            "ruleId": rule_id,
            "ruleIndex": rule_index,
            "level": level,
            "message": {
                "text": f"[{finding.severity.value.upper()}] {finding.title}"
                + (f" (CVSS {finding.cvss_score:.1f})" if finding.cvss_score else "")
            },
            "locations": locations,
            "partialFingerprints": {
                "primaryLocationLineHash": fp_hash,
            },
            "properties": {
                "straz": {
                    "finding_id": str(finding.id),
                    "status": finding.status.value,
                    "source": finding.source.value,
                    "cvss_score": finding.cvss_score,
                    "cvss_vector": finding.cvss_vector,
                    "has_poc": bool(finding.poc_command),
                    "has_patch": bool(finding.remediation_patch),
                }
            },
        }

        # Embed suggested remediation fix if patch is available
        if finding.remediation_patch:
            result["fixes"] = [
                {
                    "description": {"text": "Aplikovať odporúčanú opravu nálezu"},
                    "artifactChanges": [
                        {
                            "artifactLocation": {"uri": location_uri},
                            "replacements": [
                                {
                                    "deletedRegion": {"startLine": 1},
                                    "insertedContent": {"text": finding.remediation_patch[:1000]},
                                }
                            ],
                        }
                    ],
                }
            ]

        results.append(result)

    run: dict[str, Any] = {
        "tool": {
            "driver": {
                "name": TOOL_NAME,
                "version": tool_version,
                "informationUri": TOOL_INFORMATION_URI,
                "rules": rules,
            }
        },
        "results": results,
    }

    if app and app.git_url:
        run["versionControlProvenance"] = [
            {
                "repositoryUri": app.git_url,
            }
        ]
        run["automationDetails"] = {
            "id": f"straz/{re.sub(r'[^a-zA-Z0-9_-]', '-', app.name)}"
        }

    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [run],
    }
