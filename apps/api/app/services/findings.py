from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import App, Finding, FindingSeverity, FindingSource, FindingStatus, ScanRunFinding
from app.services.notifications import dispatch_alert


def make_fingerprint(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


async def upsert_finding(
    db: AsyncSession,
    *,
    app_id: uuid.UUID,
    target_id: uuid.UUID | None,
    source: FindingSource,
    severity: FindingSeverity,
    title: str,
    detail: str | None,
    fingerprint: str,
    cvss_score: float | None = None,
    cvss_vector: str | None = None,
    poc_command: str | None = None,
    remediation_patch: str | None = None,
    notify: bool = False,
) -> Finding:
    existing = await db.scalar(
        select(Finding).where(Finding.app_id == app_id, Finding.fingerprint == fingerprint)
    )
    now = datetime.now(timezone.utc)
    if existing:
        existing.last_seen_at = now
        existing.severity = severity
        existing.title = title
        existing.detail = detail
        if cvss_score is not None:
            existing.cvss_score = cvss_score
        if cvss_vector is not None:
            existing.cvss_vector = cvss_vector
        if poc_command is not None:
            existing.poc_command = poc_command
        if remediation_patch is not None:
            existing.remediation_patch = remediation_patch
        await _record_observation(db, existing, False)
        if existing.status == FindingStatus.fixed:
            existing.status = FindingStatus.open
            existing.closed_at = None
            if notify:
                await _enqueue_finding_alert(db, existing)
        return existing

    finding = Finding(
        app_id=app_id,
        target_id=target_id,
        source=source,
        severity=severity,
        title=title,
        detail=detail,
        fingerprint=fingerprint,
        status=FindingStatus.open,
        cvss_score=cvss_score,
        cvss_vector=cvss_vector,
        poc_command=poc_command,
        remediation_patch=remediation_patch,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(finding)
    await db.flush()
    await _record_observation(db, finding, True)
    if notify:
        await _enqueue_finding_alert(db, finding)
    return finding


async def _enqueue_finding_alert(db: AsyncSession, finding: Finding) -> None:
    app = await db.get(App, finding.app_id)
    if app is None or app.organization_id is None:
        return
    event_type = "cert.expiring" if finding.source == FindingSource.tls and "expir" in finding.title.lower() else "finding.created"
    await dispatch_alert(db, app.organization_id, event_type, finding.severity.value, finding.title, finding.detail, app)


async def _record_observation(db: AsyncSession, finding: Finding, is_new: bool) -> None:
    run_id = db.info.get("scan_run_id")
    if run_id is None:
        return
    observation = await db.get(ScanRunFinding, (run_id, finding.id))
    if observation is None:
        db.add(ScanRunFinding(scan_run_id=run_id, finding_id=finding.id,
            observed_severity=finding.severity.value, is_new=is_new))
    else:
        observation.observed_severity = finding.severity.value


async def mark_absent_fixed(
    db: AsyncSession,
    *,
    app_id: uuid.UUID,
    source: FindingSource,
    seen_fingerprints: set[str],
) -> None:
    rows = (
        await db.scalars(
            select(Finding).where(
                Finding.app_id == app_id,
                Finding.source == source,
                Finding.status == FindingStatus.open,
            )
        )
    ).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        if row.fingerprint not in seen_fingerprints:
            row.status = FindingStatus.fixed
            row.closed_at = now
