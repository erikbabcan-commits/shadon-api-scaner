from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Finding, FindingSeverity, FindingStatus, ScanRun, ScanRunFinding


async def evaluate_ci_gate(
    db: AsyncSession,
    run: ScanRun,
    fail_on: str = "high",
) -> tuple[bool, dict[str, int], str | None]:
    """
    Evaluates findings associated with the given scan run or app.
    Returns (passed, summary_counts, failure_reason).
    """
    # 1. Check scan_run_findings first if populated
    stmt = (
        select(
            ScanRunFinding.observed_severity,
            func.count(ScanRunFinding.finding_id),
        )
        .where(ScanRunFinding.scan_run_id == run.id)
        .group_by(ScanRunFinding.observed_severity)
    )
    res = (await db.execute(stmt)).all()
    counts = {row[0].lower(): row[1] for row in res}

    # If scan_run_findings is empty, fallback to open findings for the app
    if not counts:
        stmt_findings = (
            select(Finding.severity, func.count(Finding.id))
            .where(
                Finding.app_id == run.app_id,
                Finding.status == FindingStatus.open,
            )
            .group_by(Finding.severity)
        )
        res_findings = (await db.execute(stmt_findings)).all()
        counts = {row[0].value.lower(): row[1] for row in res_findings}

    critical = counts.get("critical", 0)
    high = counts.get("high", 0)
    medium = counts.get("medium", 0)
    low = counts.get("low", 0)
    total_new = critical + high + medium + low

    summary = {
        "critical": critical,
        "high": high,
        "medium": medium,
        "total_new": total_new,
    }

    fail_on_lower = fail_on.lower()
    has_failed = False
    if fail_on_lower == "critical":
        has_failed = critical > 0
    elif fail_on_lower == "medium":
        has_failed = (critical > 0) or (high > 0) or (medium > 0)
    else:  # default 'high'
        has_failed = (critical > 0) or (high > 0)

    if has_failed:
        failure_reason = f"Nájdené zraniteľnosti prekračujúce prah '{fail_on_lower}'"
        return False, summary, failure_reason

    return True, summary, None
