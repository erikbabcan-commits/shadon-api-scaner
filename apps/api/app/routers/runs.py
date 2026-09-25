from __future__ import annotations

import asyncio
import json
import logging
import uuid

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import App, RunStatus, ScanProfile, ScanRun, Target, TargetStatus, User
from app.rate_limit import client_ip, run_limiter
from app.schemas import RunCreate, RunOut
from app.services.audit import write_audit

logger = logging.getLogger("straz.runs")
router = APIRouter(tags=["runs"])

PROFILE_FLAGS = {
    ScanProfile.heartbeat: "heartbeat_enabled",
    ScanProfile.tls: "tls_enabled",
    ScanProfile.http: "http_enabled",
    ScanProfile.safe: "safe_enabled",
    ScanProfile.internetdb: "internetdb_enabled",
    ScanProfile.subdomain: "subdomain_enabled",
    ScanProfile.ports: "ports_enabled",
    ScanProfile.trivy_fs: "trivy_enabled",
    ScanProfile.trivy_image: "trivy_enabled",
    ScanProfile.gitleaks: "gitleaks_enabled",
}

_arq_pool: ArqRedis | None = None


async def get_arq_redis(settings: Settings) -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _arq_pool


@router.get("/runs", response_model=list[RunOut])
async def list_runs(
    response: Response,
    app_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ScanRun]:
    count_stmt = select(func.count()).select_from(ScanRun)
    stmt = select(ScanRun).order_by(ScanRun.created_at.desc())

    if app_id:
        count_stmt = count_stmt.where(ScanRun.app_id == app_id)
        stmt = stmt.where(ScanRun.app_id == app_id)

    total = await db.scalar(count_stmt) or 0
    items = list(await db.scalars(stmt.offset(offset).limit(limit)))

    has_more = (offset + len(items)) < total
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Has-More"] = "true" if has_more else "false"
    response.headers["X-Next-Offset"] = str(offset + len(items)) if has_more else ""

    return items


@router.get("/runs/stream")
async def stream_runs(
    request: Request,
    app_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> StreamingResponse:
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            stmt = select(ScanRun).order_by(ScanRun.created_at.desc()).limit(20)
            if app_id:
                stmt = stmt.where(ScanRun.app_id == app_id)
            items = list(await db.scalars(stmt))
            payload = [
                {
                    "id": str(r.id),
                    "app_id": str(r.app_id),
                    "profile": r.profile.value,
                    "status": r.status.value,
                    "error": r.error,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in items
            ]
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ScanRun:
    run = await db.get(ScanRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/apps/{app_id}/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
async def create_run(
    app_id: uuid.UUID,
    body: RunCreate,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ScanRun:
    await run_limiter.check(f"run:{client_ip(request)}:{user.id}", response=response)
    app = await db.get(App, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    profile = body.profile
    flag = PROFILE_FLAGS.get(profile)
    if flag and not getattr(app, flag, True):
        raise HTTPException(status_code=400, detail=f"Profile {profile.value} disabled for app")

    if profile in (ScanProfile.trivy_fs, ScanProfile.gitleaks) and not app.git_url:
        raise HTTPException(status_code=400, detail="Set git_url on the app first")
    if profile == ScanProfile.trivy_image and not app.image_ref:
        raise HTTPException(status_code=400, detail="Set image_ref on the app first")

    if profile != ScanProfile.heartbeat:
        verified_count = await db.scalar(
            select(Target.id).where(Target.app_id == app_id, Target.status == TargetStatus.verified).limit(1)
        )
        if not verified_count:
            raise HTTPException(status_code=400, detail="No verified targets — verify ownership first")

    run = ScanRun(
        app_id=app_id,
        profile=profile,
        status=RunStatus.queued,
        created_by=user.id,
    )
    db.add(run)
    await db.flush()
    await write_audit(
        db,
        action="run.create",
        user_id=user.id,
        entity_type="scan_run",
        entity_id=str(run.id),
        detail=profile.value,
    )
    await db.commit()
    await db.refresh(run)

    try:
        redis = await get_arq_redis(settings)
        await redis.enqueue_job("execute_scan_run", str(run.id))
    except Exception as exc:
        logger.error("Failed to enqueue scan run %s to ARQ: %s", run.id, exc)

    return run
