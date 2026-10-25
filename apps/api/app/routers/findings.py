from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
import redis.asyncio as aioredis
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import OrgContext, get_current_org, get_current_user, require_org_role
from app.models import (
    App,
    Finding,
    FindingSeverity,
    FindingStatus,
    OrgRole,
    RunStatus,
    ScanRun,
    User,
)
from app.schemas import FindingOut, FindingUpdate, OverviewApp, OverviewOut
from app.services.audit import write_audit

logger = logging.getLogger("straz.findings")
router = APIRouter(tags=["findings"])

OVERVIEW_CACHE_KEY = "straz:cache:overview"
OVERVIEW_CACHE_TTL = 30


async def _invalidate_overview_cache(settings: Settings, org_id: uuid.UUID | None = None) -> None:
    if settings.straz_env in ("test", "testing"):
        return
    try:
        r = aioredis.from_url(settings.redis_url, socket_timeout=1.0)
        if org_id:
            await r.delete(f"{OVERVIEW_CACHE_KEY}:{org_id}")
        await r.delete(OVERVIEW_CACHE_KEY)
        await r.aclose()
    except Exception:
        pass


@router.get("/findings", response_model=list[FindingOut])
async def list_findings(
    response: Response,
    status_filter: FindingStatus | None = None,
    app_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.viewer)),
) -> list[Finding]:
    org_filter = or_(App.organization_id == org_ctx.org_id, App.organization_id.is_(None))
    count_stmt = (
        select(func.count())
        .select_from(Finding)
        .join(App, Finding.app_id == App.id)
        .where(org_filter)
    )
    stmt = (
        select(Finding)
        .join(App, Finding.app_id == App.id)
        .where(org_filter)
        .order_by(Finding.last_seen_at.desc())
    )

    if status_filter:
        count_stmt = count_stmt.where(Finding.status == status_filter)
        stmt = stmt.where(Finding.status == status_filter)
    if app_id:
        count_stmt = count_stmt.where(Finding.app_id == app_id)
        stmt = stmt.where(Finding.app_id == app_id)

    total = await db.scalar(count_stmt) or 0
    items = list(await db.scalars(stmt.offset(offset).limit(limit)))

    has_more = (offset + len(items)) < total
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Has-More"] = "true" if has_more else "false"
    response.headers["X-Next-Offset"] = str(offset + len(items)) if has_more else ""

    return items


@router.get("/findings/{finding_id}", response_model=FindingOut)
async def get_finding(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.viewer)),
) -> Finding:
    stmt = (
        select(Finding)
        .join(App, Finding.app_id == App.id)
        .where(
            Finding.id == finding_id,
            or_(App.organization_id == org_ctx.org_id, App.organization_id.is_(None)),
        )
    )
    finding = await db.scalar(stmt)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


@router.patch("/findings/{finding_id}", response_model=FindingOut)
async def update_finding(
    finding_id: uuid.UUID,
    body: FindingUpdate,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.member)),
    settings: Settings = Depends(get_settings),
) -> Finding:
    stmt = (
        select(Finding)
        .join(App, Finding.app_id == App.id)
        .where(
            Finding.id == finding_id,
            or_(App.organization_id == org_ctx.org_id, App.organization_id.is_(None)),
        )
    )
    finding = await db.scalar(stmt)
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
        user_id=org_ctx.user.id,
        entity_type="finding",
        entity_id=str(finding.id),
        detail=body.status.value,
    )
    await db.commit()
    await db.refresh(finding)
    await _invalidate_overview_cache(settings, org_ctx.org_id)
    return finding


@router.get("/overview", response_model=OverviewOut)
async def overview(
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.viewer)),
    settings: Settings = Depends(get_settings),
) -> OverviewOut:
    cache_key = f"{OVERVIEW_CACHE_KEY}:{org_ctx.org_id}"
    # 1. Check Redis cache
    try:
        r = aioredis.from_url(settings.redis_url, socket_timeout=1.0)
        cached = await r.get(cache_key)
        await r.aclose()
        if cached:
            return OverviewOut.model_validate_json(cached)
    except Exception:
        pass

    # 2. Optimized SQL aggregations scoped to this organization
    org_filter = or_(App.organization_id == org_ctx.org_id, App.organization_id.is_(None))
    apps = list(
        await db.scalars(
            select(App).where(org_filter).order_by(App.name)
        )
    )

    # Count open findings grouped by app_id
    app_finding_counts_rows = await db.execute(
        select(Finding.app_id, func.count(Finding.id))
        .join(App, Finding.app_id == App.id)
        .where(Finding.status == FindingStatus.open, org_filter)
        .group_by(Finding.app_id)
    )
    counts: dict[uuid.UUID, int] = {row[0]: row[1] for row in app_finding_counts_rows}

    # Count open findings grouped by severity
    by_sev = {s.value: 0 for s in FindingSeverity}
    sev_rows = await db.execute(
        select(Finding.severity, func.count(Finding.id))
        .join(App, Finding.app_id == App.id)
        .where(Finding.status == FindingStatus.open, org_filter)
        .group_by(Finding.severity)
    )
    for row in sev_rows:
        sev_val = row[0].value if hasattr(row[0], "value") else str(row[0])
        by_sev[sev_val] = row[1]

    # Certs expiring query
    certs = (
        await db.scalar(
            select(func.count(Finding.id))
            .join(App, Finding.app_id == App.id)
            .where(Finding.status == FindingStatus.open, org_filter)
            .where(
                or_(
                    Finding.title.ilike("%certificate%"),
                    Finding.title.ilike("%expires%"),
                )
            )
        )
        or 0
    )

    # Running / queued scans count
    running = (
        await db.scalar(
            select(func.count())
            .select_from(ScanRun)
            .join(App, ScanRun.app_id == App.id)
            .where(
                ScanRun.status.in_([RunStatus.queued, RunStatus.running]),
                org_filter,
            )
        )
        or 0
    )

    result = OverviewOut(
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
        running_scans=int(running),
    )

    # Cache overview response in Redis
    try:
        r = aioredis.from_url(settings.redis_url, socket_timeout=1.0)
        await r.setex(cache_key, OVERVIEW_CACHE_TTL, result.model_dump_json())
        await r.aclose()
    except Exception:
        pass

    return result
