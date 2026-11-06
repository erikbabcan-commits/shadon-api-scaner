"""Durable, plan-aware scheduler admission; all time windows are UTC.

An organization's row lock serializes quota checks and scheduler admission.
Completed or failed runs consume their cadence window; retries of the dispatcher
never spend quota again. A committed queued run is an outbox entry, identified
by its immutable scheduler audit event, and is published with a stable ARQ id.
This does not provide a global execution mutex for separately admitted manual
runs, or reclaim running scans without an execution lease.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import uuid

from sqlalchemy import String, cast, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import App, AuditEvent, Organization, RunStatus, ScanProfile, ScanRun, Target, TargetStatus
from app.services.audit import write_audit_log
from app.services.quota import check_scan_quota, get_plan_config, lock_organization, record_scan_admission

logger = logging.getLogger("straz.scheduler")
MAX_QUEUED_AGE = timedelta(hours=1)

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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    # SQLAlchemy's SQLite test dialect returns naive datetimes for UTC columns.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def cadence_window(cadence: str | None, now: datetime) -> datetime | None:
    now = as_utc(now)
    if cadence == "hourly":
        return now.replace(minute=0, second=0, microsecond=0)
    if cadence in {"daily", "weekly"}:
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return day if cadence == "daily" else day - timedelta(days=day.weekday())
    return None


def profile_enabled(app: App, profile: ScanProfile) -> bool:
    if not getattr(app, PROFILE_FLAGS[profile], False):
        return False
    if profile in {ScanProfile.trivy_fs, ScanProfile.gitleaks} and not app.git_url:
        return False
    if profile == ScanProfile.trivy_image and not app.image_ref:
        return False
    return True


async def target_ready(db: AsyncSession, app_id: uuid.UUID, profile: ScanProfile, production: bool) -> bool:
    verified = select(Target).where(Target.app_id == app_id, Target.status == TargetStatus.verified)
    # The executor rejects an app with any trusted-private verified target in
    # production, including heartbeat. Do not consume quota for that known case.
    if production and await db.scalar(verified.where(Target.trusted_private.is_(True)).limit(1)):
        return False
    if profile == ScanProfile.heartbeat:
        # Heartbeat only uses the app URL; its actual transport still pins DNS.
        return True
    if not await db.scalar(verified.limit(1)):
        return False
    return True


async def admit_scheduled_profile(
    db: AsyncSession,
    app: App,
    profile: ScanProfile,
    *,
    now: datetime,
    blocked_profiles: frozenset[ScanProfile],
    production: bool,
) -> ScanRun | None:
    app_id, org_id = app.id, app.organization_id
    if org_id is None or profile in blocked_profiles or not profile_enabled(app, profile):
        return None
    org = await db.get(Organization, org_id)
    if org is None:
        return None
    await lock_organization(db, org)
    # Refresh the app under the admission lock: changes may have committed while
    # this dispatcher waited behind another request for the same organization.
    await db.refresh(app)
    if app.organization_id != org_id or not profile_enabled(app, profile):
        await db.rollback()
        return None
    plan = get_plan_config(org)
    start = cadence_window(plan["cron_schedule"], now)
    if start is None or profile not in plan["allowed_profiles"]:
        await db.rollback()
        return None
    if not await target_ready(db, app_id, profile, production):
        await db.rollback()
        return None
    # Never add a second scheduled scan while an earlier manual/CI/scheduled
    # run of this app/profile is queued or running. Do not kill running scans.
    previous = select(ScanRun.id).where(ScanRun.app_id == app_id, ScanRun.profile == profile)
    active = await db.scalar(previous.where(ScanRun.status.in_([RunStatus.queued, RunStatus.running])).limit(1))
    in_window = await db.scalar(previous.where(ScanRun.created_at >= start).limit(1))
    if active or in_window:
        await db.rollback()
        return None
    allowed, _ = await check_scan_quota(db, org, profile)
    if not allowed:
        await db.rollback()
        return None
    run = ScanRun(id=uuid.uuid4(), app_id=app_id, profile=profile, status=RunStatus.queued,
                  created_at=as_utc(now))
    db.add(run)
    await record_scan_admission(db, org_id)
    await write_audit_log(db, org_id=org_id, action="scan.trigger", entity_type="scan_run", entity_id=str(run.id),
                          details={"trigger": "scheduler", "profile": profile.value,
                                   "cadence": plan["cron_schedule"], "window_start": start.isoformat()})
    await db.commit()
    return run


async def publish_scheduled_run(redis, run: ScanRun) -> bool:
    try:
        # ARQ returns None for an already existing id. This is successful
        # idempotent publication, not a reason to create a new database run.
        await redis.enqueue_job("execute_scan_run", str(run.id), _job_id=f"scheduled-scan:{run.id}")
        return True
    except Exception:
        logger.warning("Scheduled scan queue unavailable; durable admission retained")
        return False


async def recover_scheduled_queue(
    db: AsyncSession,
    redis,
    *,
    now: datetime,
    blocked_profiles: frozenset[ScanProfile],
    production: bool,
) -> None:
    # Explicit immutable audit proof excludes manual and CI runs from this
    # publisher and its queue-age policy. No mass reset of queued/running jobs.
    scheduler_proof = exists(select(AuditEvent.id).where(
        AuditEvent.entity_id == cast(ScanRun.id, String),
        AuditEvent.entity_type == "scan_run",
        AuditEvent.action == "scan.trigger",
        AuditEvent.organization_id == App.organization_id,
        # Details are a JSON object written in the admission transaction.
        # A missing/manual trigger, null, array or legacy JSON-string scalar
        # is not proof of scheduler ownership. Filter before the batch limit
        # so unrelated audit rows cannot starve real recoverable jobs.
        AuditEvent.details["trigger"].as_string() == "scheduler",
    ))
    rows = list(await db.scalars(select(ScanRun).join(App, App.id == ScanRun.app_id).where(
        ScanRun.status == RunStatus.queued,
        ScanRun.created_by.is_(None), ScanRun.ci_fail_on.is_(None), scheduler_proof,
    ).order_by(ScanRun.created_at, ScanRun.id).limit(100).with_for_update(of=ScanRun, skip_locked=True)))
    for run in rows:
        app = await db.get(App, run.app_id)
        org = await db.get(Organization, app.organization_id) if app and app.organization_id else None
        expired = as_utc(run.created_at) + MAX_QUEUED_AGE <= as_utc(now)
        eligible = (app is not None and org is not None and
                    run.profile not in blocked_profiles and profile_enabled(app, run.profile) and
                    cadence_window(get_plan_config(org)["cron_schedule"], now) is not None and
                    run.profile in get_plan_config(org)["allowed_profiles"] and
                    await target_ready(db, app.id, run.profile, production))
        if expired or not eligible:
            run.status = RunStatus.failed
            run.error = "Scheduled scan expired before execution" if expired else "Scheduled scan is no longer eligible"
            run.finished_at = as_utc(now)
            continue
        run.error = None if await publish_scheduled_run(redis, run) else "Scan queue unavailable"
    await db.commit()
