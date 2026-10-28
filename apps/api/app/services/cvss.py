"""CVSS v3.1 calculation, vector parsing, and validation service.

Ported from STRIX (strix/tools/reporting/ and strix/report/) with full
FIRST CVSS v3.1 specification compliance.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any

logger = logging.getLogger("straz.cvss")

# Valid values per metric according to CVSS v3.1
CVSS_VALID: dict[str, list[str]] = {
    "attack_vector": ["N", "A", "L", "P"],
    "attack_complexity": ["L", "H"],
    "privileges_required": ["N", "L", "H"],
    "user_interaction": ["N", "R"],
    "scope": ["U", "C"],
    "confidentiality": ["N", "L", "H"],
    "integrity": ["N", "L", "H"],
    "availability": ["N", "L", "H"],
}

# Mapping between long keys and standard vector metric codes
LONG_TO_SHORT: dict[str, str] = {
    "attack_vector": "AV",
    "attack_complexity": "AC",
    "privileges_required": "PR",
    "user_interaction": "UI",
    "scope": "S",
    "confidentiality": "C",
    "integrity": "I",
    "availability": "A",
}

SHORT_TO_LONG: dict[str, str] = {v: k for k, v in LONG_TO_SHORT.items()}

# Metric weights according to FIRST CVSS v3.1 specification
_WEIGHT_AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.20}
_WEIGHT_AC = {"L": 0.77, "H": 0.44}
_WEIGHT_PR_UNCHANGED = {"N": 0.85, "L": 0.62, "H": 0.27}
_WEIGHT_PR_CHANGED = {"N": 0.85, "L": 0.68, "H": 0.50}
_WEIGHT_UI = {"N": 0.85, "R": 0.62}
_WEIGHT_CIA = {"N": 0.0, "L": 0.22, "H": 0.56}

# Human-readable labels for frontend and documentation
CVSS_LABELS: dict[str, dict[str, str]] = {
    "AV": {
        "N": "Network",
        "A": "Adjacent Network",
        "L": "Local",
        "P": "Physical",
    },
    "AC": {
        "L": "Low",
        "H": "High",
    },
    "PR": {
        "N": "None",
        "L": "Low",
        "H": "High",
    },
    "UI": {
        "N": "None",
        "R": "Required",
    },
    "S": {
        "U": "Unchanged",
        "C": "Changed",
    },
    "C": {
        "N": "None",
        "L": "Low",
        "H": "High",
    },
    "I": {
        "N": "None",
        "L": "Low",
        "H": "High",
    },
    "A": {
        "N": "None",
        "L": "Low",
        "H": "High",
    },
}


def _round_up(val: float) -> float:
    """Official CVSS v3.1 Roundup function (Section 7.4)."""
    int_input = round(val * 100000)
    if (int_input % 10000) == 0:
        return int_input / 100000.0
    return (math.floor(int_input / 10000) + 1) / 10.0


def severity_from_score(score: float) -> str:
    """Map CVSS v3.1 score to severity string."""
    if score == 0.0:
        return "info"
    if score < 4.0:
        return "low"
    if score < 7.0:
        return "medium"
    if score < 9.0:
        return "high"
    return "critical"


def normalize_breakdown(breakdown: dict[str, str]) -> dict[str, str]:
    """Normalize input dict so it always has long keys with uppercase values."""
    normalized: dict[str, str] = {}
    for key, val in breakdown.items():
        k = key.lower().strip()
        v = str(val).upper().strip()
        if k in LONG_TO_SHORT:
            normalized[k] = v
        elif k.upper() in SHORT_TO_LONG:
            long_k = SHORT_TO_LONG[k.upper()]
            normalized[long_k] = v
        else:
            raise ValueError(f"Unknown CVSS metric key: '{key}'")

    # Verify all 8 required base metrics exist
    for long_key, valid_values in CVSS_VALID.items():
        if long_key not in normalized:
            raise ValueError(f"Missing required CVSS metric: '{long_key}'")
        val = normalized[long_key]
        if val not in valid_values:
            raise ValueError(
                f"Invalid value '{val}' for metric '{long_key}'. Valid values: {valid_values}"
            )

    return normalized


def build_vector_string(normalized_breakdown: dict[str, str]) -> str:
    """Format normalized breakdown into standard CVSS:3.1 vector string."""
    return (
        f"CVSS:3.1/AV:{normalized_breakdown['attack_vector']}/"
        f"AC:{normalized_breakdown['attack_complexity']}/"
        f"PR:{normalized_breakdown['privileges_required']}/"
        f"UI:{normalized_breakdown['user_interaction']}/"
        f"S:{normalized_breakdown['scope']}/"
        f"C:{normalized_breakdown['confidentiality']}/"
        f"I:{normalized_breakdown['integrity']}/"
        f"A:{normalized_breakdown['availability']}"
    )


def parse_cvss_vector(vector: str) -> dict[str, str]:
    """Parse CVSS 3.0 / 3.1 vector string into normalized breakdown dict."""
    cleaned = vector.strip()
    if not cleaned.startswith(("CVSS:3.1/", "CVSS:3.0/")):
        raise ValueError("Vector must start with 'CVSS:3.1/' or 'CVSS:3.0/'")

    parts = cleaned.split("/")[1:]  # skip 'CVSS:3.x'
    breakdown: dict[str, str] = {}
    for part in parts:
        if ":" not in part:
            continue
        key, val = part.split(":", 1)
        key = key.strip().upper()
        val = val.strip().upper()
        if key in SHORT_TO_LONG:
            breakdown[SHORT_TO_LONG[key]] = val

    return normalize_breakdown(breakdown)


def calculate_cvss_pure(breakdown: dict[str, str]) -> tuple[float, str, str]:
    """Pure Python calculation of CVSS v3.1 according to FIRST specification."""
    norm = normalize_breakdown(breakdown)
    vector = build_vector_string(norm)

    av = _WEIGHT_AV[norm["attack_vector"]]
    ac = _WEIGHT_AC[norm["attack_complexity"]]
    s_changed = norm["scope"] == "C"

    pr = (
        _WEIGHT_PR_CHANGED[norm["privileges_required"]]
        if s_changed
        else _WEIGHT_PR_UNCHANGED[norm["privileges_required"]]
    )
    ui = _WEIGHT_UI[norm["user_interaction"]]

    c = _WEIGHT_CIA[norm["confidentiality"]]
    i = _WEIGHT_CIA[norm["integrity"]]
    a = _WEIGHT_CIA[norm["availability"]]

    # Impact Sub-Score (ISS)
    iss = 1.0 - ((1.0 - c) * (1.0 - i) * (1.0 - a))

    # Impact
    if s_changed:
        impact = 7.52 * (iss - 0.029) - 3.25 * ((iss - 0.02) ** 15)
    else:
        impact = 6.42 * iss

    # Exploitability
    exploitability = 8.22 * av * ac * pr * ui

    # Base Score
    if impact <= 0:
        base_score = 0.0
    else:
        if not s_changed:
            base_score = _round_up(min(impact + exploitability, 10.0))
        else:
            base_score = _round_up(min(1.08 * (impact + exploitability), 10.0))

    severity = severity_from_score(base_score)
    return base_score, severity, vector


def calculate_cvss(breakdown_or_vector: dict[str, str] | str) -> tuple[float, str, str]:
    """Calculate CVSS v3.1 score, severity, and vector string.

    Uses the 'cvss' library when available, with pure-python fallback.
    Returns (score, severity, vector).
    """
    if isinstance(breakdown_or_vector, str):
        breakdown = parse_cvss_vector(breakdown_or_vector)
    else:
        breakdown = normalize_breakdown(breakdown_or_vector)

    vector = build_vector_string(breakdown)

    try:
        from cvss import CVSS3

        cvss = CVSS3(vector)
        score = float(cvss.scores()[0])
        base_severity = cvss.severities()[0].lower()
        severity = "info" if base_severity == "none" else base_severity
        return score, severity, vector
    except Exception as exc:
        logger.debug("Falling back to pure Python CVSS 3.1 calculator: %s", exc)
        return calculate_cvss_pure(breakdown)
