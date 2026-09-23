from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Finding, FindingSeverity, FindingSource, FindingStatus
from app.services.ntfy import send_ntfy


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
    notify: bool = False,
) -> Finding:
    existing = await db.scalar(
        select(Finding).where(Finding.app_id == app_id, Finding.fingerprint == fingerprint)
    )
    now = datetime.now(timezone.utc)
    if existing:
        existing.last_seen_at = now
        if existing.status == FindingStatus.fixed:
            existing.status = FindingStatus.open
            existing.closed_at = None
            if notify and severity in (FindingSeverity.high, FindingSeverity.critical):
                await send_ntfy(
                    f"Stráž: {severity.value} nález",
                    f"{title}\n{detail or ''}",
                    priority=5 if severity == FindingSeverity.critical else 4,
                    tags="rotating_light",
                )
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
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(finding)
    if notify and severity in (FindingSeverity.high, FindingSeverity.critical):
        await send_ntfy(
            f"Stráž: {severity.value} nález",
            f"{title}\n{detail or ''}",
            priority=5 if severity == FindingSeverity.critical else 4,
            tags="rotating_light",
        )
    return finding


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
