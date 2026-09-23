from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import (
    App,
    Finding,
    FindingSeverity,
    FindingStatus,
    RunStatus,
    ScanRun,
    User,
)
from app.schemas import FindingOut, FindingUpdate, OverviewApp, OverviewOut
from app.services.audit import write_audit

router = APIRouter(tags=["findings"])


@router.get("/findings", response_model=list[FindingOut])
async def list_findings(
    status_filter: FindingStatus | None = None,
    app_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Finding]:
    stmt = select(Finding).order_by(Finding.last_seen_at.desc()).limit(200)
    if status_filter:
        stmt = stmt.where(Finding.status == status_filter)
    if app_id:
        stmt = stmt.where(Finding.app_id == app_id)
    return list(await db.scalars(stmt))


@router.patch("/findings/{finding_id}", response_model=FindingOut)
async def update_finding(
    finding_id: uuid.UUID,
    body: FindingUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Finding:
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    finding.status = body.status
    if body.status in (FindingStatus.accepted, FindingStatus.fixed):
        finding.closed_at = datetime.now(timezone.utc)
    elif body.status == FindingStatus.open:
        finding.closed_at = None
    await write_audit(
        db,
        action="finding.update",
        user_id=user.id,
        entity_type="finding",
        entity_id=str(finding.id),
        detail=body.status.value,
    )
    await db.commit()
    await db.refresh(finding)
    return finding


@router.get("/overview", response_model=OverviewOut)
async def overview(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> OverviewOut:
    apps = list(await db.scalars(select(App).order_by(App.name)))
    open_findings = list(
        await db.scalars(select(Finding).where(Finding.status == FindingStatus.open))
    )
    by_sev = {s.value: 0 for s in FindingSeverity}
    certs = 0
    for f in open_findings:
        by_sev[f.severity.value] = by_sev.get(f.severity.value, 0) + 1
        if "certificate" in f.title.lower() or "expires" in f.title.lower():
            certs += 1

    counts: dict[uuid.UUID, int] = {}
    for f in open_findings:
        counts[f.app_id] = counts.get(f.app_id, 0) + 1

    running = await db.scalar(
        select(func.count()).select_from(ScanRun).where(ScanRun.status.in_([RunStatus.queued, RunStatus.running]))
    )

    return OverviewOut(
        apps=[
            OverviewApp(
                id=a.id,
                name=a.name,
                environment=a.environment,
                last_up=a.last_up,
                last_status_code=a.last_status_code,
                last_latency_ms=a.last_latency_ms,
                last_checked_at=a.last_checked_at,
                open_findings=counts.get(a.id, 0),
            )
            for a in apps
        ],
        open_by_severity=by_sev,
        certs_expiring_soon=certs,
        running_scans=int(running or 0),
    )
