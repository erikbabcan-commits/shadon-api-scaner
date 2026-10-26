from __future__ import annotations

import asyncio
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import OrgContext, get_current_user, get_current_org, require_scope, ROLE_HIERARCHY
from app.models import (
    App,
    RunStatus,
    ScanProfile,
    ScanRun,
    OrgRole,
    Target,
    TargetStatus,
)
from app.routers.runs import get_arq_redis
from app.services.audit import write_audit
from app.services.ci import evaluate_ci_gate
from app.services.quota import check_scan_quota, record_scan_admission

router = APIRouter(prefix="/api/ci", tags=["ci-cd"])


class CiScanRequest(BaseModel):
    app_id: uuid.UUID
    profile: ScanProfile = ScanProfile.safe
    fail_on: Literal["critical", "high", "medium"] = "high"
    wait: bool = True
    timeout_seconds: int = Field(default=180, ge=1, le=600)


class CiGateSummary(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    total_new: int = 0


class CiScanResponse(BaseModel):
    passed: bool
    run_id: str
    status: str
    summary: CiGateSummary
    failure_reason: str | None = None
    report_url: str
    status_url: str


@router.post("/scan", response_model=CiScanResponse)
async def ci_scan(
    body: CiScanRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_scope("ci:scan")),
    settings: Settings = Depends(get_settings),
) -> Response:
    # 1. Fetch app belonging to tenant
    app = await db.scalar(
        select(App).where(
            App.id == body.app_id,
            App.organization_id == org_ctx.org_id,
        )
    )
    if not app:
        raise HTTPException(status_code=404, detail="App not found in organization")

    # 2. Strict target verification for CI (even for heartbeat)
    verified_target = await db.scalar(
        select(Target.id)
        .where(Target.app_id == app.id, Target.status == TargetStatus.verified)
        .limit(1)
    )
    if not verified_target:
        raise HTTPException(
            status_code=400,
            detail="No verified targets found for app — domain verification required for CI gate",
        )

    # 3. Check quota & profile
    allowed, reason = await check_scan_quota(db, org_ctx.organization, body.profile)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=reason,
            headers={"X-Upgrade-Required": "true"},
        )

    # 4. Create and persist ScanRun
    run = ScanRun(
        id=uuid.uuid4(),
        app_id=app.id,
        profile=body.profile,
        status=RunStatus.queued,
        ci_fail_on=body.fail_on,
        created_by=org_ctx.user.id,
    )
    db.add(run)
    await db.flush()
    await record_scan_admission(db, org_ctx.org_id)
    await write_audit(
        db,
        action="ci.scan",
        user_id=org_ctx.user.id,
        entity_type="scan_run",
        entity_id=str(run.id),
        detail=f"profile={body.profile.value}, fail_on={body.fail_on}",
    )
    await db.commit()
    await db.refresh(run)

    # 5. Enqueue to worker
    try:
        redis = await get_arq_redis(settings)
        await redis.enqueue_job("execute_scan_run", str(run.id))
    except Exception:
        run.status = RunStatus.failed
        run.error = "Scan queue unavailable"
        await db.commit()
        raise HTTPException(status_code=503, detail="Scan queue unavailable") from None

    report_url = f"/apps/{app.id}/compliance"
    status_url = f"/api/ci/runs/{run.id}"

    # If wait is False, return 202 Accepted immediately
    if not body.wait:
        resp_data = {
            "passed": False,
            "run_id": str(run.id),
            "status": run.status.value,
            "summary": {"critical": 0, "high": 0, "medium": 0, "total_new": 0},
            "failure_reason": None,
            "report_url": report_url,
            "status_url": status_url,
        }
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=resp_data)

    # 6. Polling loop with timeout
    start_time = time.monotonic()
    deadline = start_time + min(body.timeout_seconds, 600)

    while time.monotonic() < deadline:
        user = await get_current_user(request, db=db, settings=settings)
        current = await get_current_org(request, user=user, db=db)
        if ROLE_HIERARCHY[current.role] < ROLE_HIERARCHY[OrgRole.member]:
            raise HTTPException(status_code=403, detail="CI scans require member role")
        await db.refresh(run)
        if run.status in (RunStatus.done, RunStatus.failed):
            break
        await db.commit()  # Do not retain an idle DB transaction during polling.
        await asyncio.sleep(1)

    if run.status == RunStatus.queued or run.status == RunStatus.running:
        # Timeout occurred
        resp_data = {
            "passed": False,
            "run_id": str(run.id),
            "status": run.status.value,
            "summary": {"critical": 0, "high": 0, "medium": 0, "total_new": 0},
            "failure_reason": f"Časový limit skenu vypršal po {body.timeout_seconds}s",
            "report_url": report_url,
            "status_url": status_url,
        }
        return JSONResponse(status_code=status.HTTP_504_GATEWAY_TIMEOUT, content=resp_data)

    if run.status == RunStatus.failed:
        resp_data = {
            "passed": False,
            "run_id": str(run.id),
            "status": "failed",
            "summary": {"critical": 0, "high": 0, "medium": 0, "total_new": 0},
            "failure_reason": run.error or "Sken zlyhal pri vykonávaní",
            "report_url": report_url,
            "status_url": status_url,
        }
        return JSONResponse(status_code=status.HTTP_424_FAILED_DEPENDENCY, content=resp_data)

    # run.status == RunStatus.done
    passed, summary, failure_reason = await evaluate_ci_gate(db, run, body.fail_on)

    resp_data = {
        "passed": passed,
        "run_id": str(run.id),
        "status": "done",
        "summary": summary,
        "failure_reason": failure_reason,
        "report_url": report_url,
        "status_url": status_url,
    }

    if not passed:
        return JSONResponse(status_code=status.HTTP_424_FAILED_DEPENDENCY, content=resp_data)

    return JSONResponse(status_code=status.HTTP_200_OK, content=resp_data)


@router.get("/runs/{run_id}", response_model=CiScanResponse)
async def get_ci_run_status(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_scope("ci:scan")),
) -> Response:
    stmt = (
        select(ScanRun)
        .join(App, ScanRun.app_id == App.id)
        .where(
            ScanRun.id == run_id,
            App.organization_id == org_ctx.org_id,
        )
    )
    run = await db.scalar(stmt)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found in organization")

    fail_on = run.ci_fail_on or "high"
    passed, summary, failure_reason = await evaluate_ci_gate(db, run, fail_on)

    report_url = f"/apps/{run.app_id}/compliance"
    status_url = f"/api/ci/runs/{run.id}"

    resp_data = {
        "passed": passed if run.status == RunStatus.done else False,
        "run_id": str(run.id),
        "status": run.status.value,
        "summary": summary,
        "failure_reason": failure_reason if run.status == RunStatus.done else None,
        "report_url": report_url,
        "status_url": status_url,
    }

    if run.status == RunStatus.failed or (run.status == RunStatus.done and not passed):
        return JSONResponse(status_code=status.HTTP_424_FAILED_DEPENDENCY, content=resp_data)

    if run.status in (RunStatus.queued, RunStatus.running):
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=resp_data)

    return JSONResponse(status_code=status.HTTP_200_OK, content=resp_data)
