from __future__ import annotations


from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RunStatus, ScanRun, ScanRunFinding


async def evaluate_ci_gate(
    db: AsyncSession,
    run: ScanRun,
    fail_on: str = "high",
) -> tuple[bool, dict[str, int], str | None]:
    """
    Evaluates findings associated with the given scan run or app.
    Returns (passed, summary_counts, failure_reason).
    """
    empty = {"critical": 0, "high": 0, "medium": 0, "total_new": 0}
    if run.status != RunStatus.done or not run.observations_complete:
        return False, empty, "Sken nemá úplné a overené výsledky"
    if fail_on not in {"critical", "high", "medium"}:
        return False, empty, "Neplatný prah zlyhania"
    # Only immutable per-run observations are evidence for a CI gate.
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

    critical = counts.get("critical", 0)
    high = counts.get("high", 0)
    medium = counts.get("medium", 0)
    total_new = await db.scalar(select(func.count()).select_from(ScanRunFinding).where(
        ScanRunFinding.scan_run_id == run.id, ScanRunFinding.is_new.is_(True)
    )) or 0

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
