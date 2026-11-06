"""Plan scheduling fixtures: no scanner, external DNS, HTTP or real accounts."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import worker
from app.db import Base
from app.models import App, AuditEvent, CLI_SCANNER_PROFILES, Organization, RunStatus, ScanProfile, ScanRun, ScanUsage, Target, TargetStatus
from app.services import scheduling


class Queue:
    def __init__(self, unavailable=False):
        self.unavailable = unavailable
        self.calls = []
        self.ids = set()

    async def enqueue_job(self, name, run_id, **kwargs):
        assert name == "execute_scan_run"
        self.calls.append((run_id, kwargs))
        if self.unavailable:
            raise ConnectionError("Synthetic queue outage")
        job_id = kwargs["_job_id"]
        if job_id in self.ids:
            return None
        self.ids.add(job_id)
        return object()


async def seed(db, tier="pro", *, heartbeat=True, internetdb=False, verified=False, status="active"):
    org = Organization(id=uuid.uuid4(), name="Scheduler fixture", slug=uuid.uuid4().hex,
                       plan_tier=tier, subscription_status=status)
    app = App(id=uuid.uuid4(), organization_id=org.id, name="Scheduled fixture", base_url="https://example.invalid",
              heartbeat_enabled=heartbeat, internetdb_enabled=internetdb,
              tls_enabled=False, http_enabled=False, safe_enabled=False, subdomain_enabled=False,
              ports_enabled=False, trivy_enabled=False, gitleaks_enabled=False)
    db.add_all([org, app])
    if verified:
        db.add(Target(id=uuid.uuid4(), app_id=app.id, host="example.invalid", verify_token="fixture-only",
                      status=TargetStatus.verified))
    await db.commit()
    return org.id, app.id


async def dispatch(db, monkeypatch, queue, now, **kwargs):
    monkeypatch.setattr(worker, "SessionLocal", async_sessionmaker(db.bind, expire_on_commit=False))
    await worker.scheduled_scans_all({"redis": queue}, now=now, **kwargs)
    # The worker uses independent sessions, as it does with PostgreSQL.
    db.expire_all()


@pytest.mark.parametrize("cadence,now,start", [
    (None, "2026-11-08T23:59:00+00:00", None),
    ("hourly", "2026-11-08T23:59:00+02:00", "2026-11-08T21:00:00+00:00"),
    ("daily", "2026-11-08T23:59:00-02:00", "2026-11-09T00:00:00+00:00"),
    ("weekly", "2026-11-08T23:59:00+00:00", "2026-11-02T00:00:00+00:00"),
    ("weekly", "2026-11-09T00:00:00+00:00", "2026-11-09T00:00:00+00:00"),
    ("unknown", "2026-11-09T00:00:00+00:00", None),
])
def test_cadence_windows_are_utc_and_week_starts_monday(cadence, now, start):
    result = scheduling.cadence_window(cadence, datetime.fromisoformat(now))
    assert result == (datetime.fromisoformat(start) if start else None)


@pytest.mark.parametrize("tier", ["free", "unknown"])
async def test_free_has_no_implicit_scan_or_quota_consumption(db_session, monkeypatch, tier):
    await seed(db_session, tier)
    queue = Queue()
    await dispatch(db_session, monkeypatch, queue, scheduling.utc_now())
    assert not queue.calls
    assert await db_session.scalar(select(func.count()).select_from(ScanRun)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ScanUsage)) == 0


@pytest.mark.parametrize("tier,cadence,step", [
    ("starter", "weekly", timedelta(days=7)),
    ("pro", "daily", timedelta(days=1)),
    ("agency", "hourly", timedelta(hours=1)),
])
async def test_paid_cadence_once_per_window_no_backfill(db_session, monkeypatch, tier, cadence, step):
    org_id, app_id = await seed(db_session, tier)
    now = scheduling.cadence_window(cadence, scheduling.utc_now()) + timedelta(minutes=10)
    queue = Queue()
    await dispatch(db_session, monkeypatch, queue, now)
    first = await db_session.scalar(select(ScanRun).where(ScanRun.app_id == app_id))
    first.status = RunStatus.done
    await db_session.commit()
    first_id = first.id
    await dispatch(db_session, monkeypatch, queue, now + timedelta(minutes=1))
    assert await db_session.scalar(select(func.count()).select_from(ScanRun)) == 1
    # A long outage catches up only the current window, never every missed slot.
    await dispatch(db_session, monkeypatch, queue, now + step * 4)
    assert await db_session.scalar(select(func.count()).select_from(ScanRun)) == 2
    assert len(queue.ids) == 2
    audit = await db_session.scalar(select(AuditEvent).where(AuditEvent.entity_id == str(first_id)))
    assert audit.organization_id == org_id
    assert audit.details["cadence"] == cadence
    assert audit.details["window_start"] == scheduling.cadence_window(cadence, now).isoformat()


@pytest.mark.parametrize("case", ["disabled", "unverified", "past_due", "expired", "quota", "cli"])
async def test_schedule_keeps_flags_verification_entitlements_and_quota(db_session, monkeypatch, case):
    org_id, app_id = await seed(db_session, "starter", heartbeat=case != "disabled",
                               internetdb=case == "unverified", status="past_due" if case == "past_due" else "active")
    org = await db_session.get(Organization, org_id)
    app = await db_session.get(App, app_id)
    profile = ScanProfile.heartbeat
    if case == "unverified":
        app.heartbeat_enabled = False
    if case == "expired":
        org.current_period_end = scheduling.utc_now() - timedelta(days=1)
    if case == "quota":
        # Recorded admission survives application/run deletion and still limits cron.
        from app.services.quota import get_current_period_bounds
        start, end = get_current_period_bounds(org)
        db_session.add(ScanUsage(id=uuid.uuid4(), org_id=org_id, period_start=start, period_end=end, scans_count=100))
    if case == "cli":
        app.heartbeat_enabled = False
        app.http_enabled = True
        profile = ScanProfile.http
    await db_session.commit()
    queue = Queue()
    await dispatch(db_session, monkeypatch, queue, scheduling.utc_now())
    assert not queue.calls
    assert await db_session.scalar(select(func.count()).select_from(ScanRun)) == 0


async def test_verified_enabled_internetdb_is_scheduled_with_tenant_audit(db_session, monkeypatch):
    org_id, app_id = await seed(db_session, "pro", heartbeat=False, internetdb=True, verified=True)
    queue = Queue()
    await dispatch(db_session, monkeypatch, queue, scheduling.utc_now())
    run = await db_session.scalar(select(ScanRun))
    assert run.app_id == app_id and run.profile == ScanProfile.internetdb
    assert len(queue.calls) == 1
    assert (await db_session.scalar(select(AuditEvent))).organization_id == org_id


@pytest.mark.parametrize("profile", [ScanProfile.heartbeat, ScanProfile.internetdb])
async def test_production_private_target_is_not_admitted(db_session, profile):
    _, app_id = await seed(db_session, "pro", internetdb=True, verified=True)
    target = await db_session.scalar(select(Target))
    target.trusted_private = True
    await db_session.commit()
    app = await db_session.get(App, app_id)
    run = await scheduling.admit_scheduled_profile(db_session, app, profile,
        now=scheduling.utc_now(), blocked_profiles=CLI_SCANNER_PROFILES, production=True)
    assert run is None
    assert await db_session.scalar(select(func.count()).select_from(ScanUsage)) == 0


@pytest.mark.parametrize("status", [RunStatus.queued, RunStatus.running])
async def test_active_manual_scan_blocks_scheduler_and_is_never_reclaimed(db_session, monkeypatch, status):
    _, app_id = await seed(db_session, "agency")
    old = scheduling.utc_now() - timedelta(days=2)
    run = ScanRun(id=uuid.uuid4(), app_id=app_id, profile=ScanProfile.heartbeat,
                  status=status, created_at=old, created_by=uuid.uuid4())
    db_session.add(run)
    await db_session.commit()
    run_id = run.id
    queue = Queue()
    await dispatch(db_session, monkeypatch, queue, scheduling.utc_now())
    assert not queue.calls
    assert (await db_session.get(ScanRun, run_id)).status == status
    assert await db_session.scalar(select(func.count()).select_from(ScanRun)) == 1


async def test_commit_before_enqueue_recovers_same_run_and_quota_once(db_session, monkeypatch):
    _, app_id = await seed(db_session, "pro")
    now = scheduling.utc_now()
    app = await db_session.get(App, app_id)
    # Simulate a process dying immediately after the database commit.
    run = await scheduling.admit_scheduled_profile(db_session, app, ScanProfile.heartbeat,
        now=now, blocked_profiles=CLI_SCANNER_PROFILES, production=True)
    run_id = run.id
    queue = Queue()
    await dispatch(db_session, monkeypatch, queue, now + timedelta(minutes=1))
    await dispatch(db_session, monkeypatch, queue, now + timedelta(minutes=2))
    assert {call[0] for call in queue.calls} == {str(run_id)}
    assert {call[1]["_job_id"] for call in queue.calls} == {f"scheduled-scan:{run_id}"}
    assert len(queue.ids) == 1
    assert await db_session.scalar(select(func.sum(ScanUsage.scans_count))) == 1
    assert await db_session.scalar(select(func.count()).select_from(ScanRun)) == 1


async def test_queue_outage_remains_recoverable_without_second_admission(db_session, monkeypatch):
    await seed(db_session, "pro")
    queue = Queue(unavailable=True)
    now = scheduling.utc_now()
    await dispatch(db_session, monkeypatch, queue, now)
    assert (await db_session.scalar(select(ScanRun))).status == RunStatus.queued
    await dispatch(db_session, monkeypatch, queue, now + timedelta(minutes=1))
    assert (await db_session.scalar(select(ScanRun))).error == "Scan queue unavailable"
    queue.unavailable = False
    await dispatch(db_session, monkeypatch, queue, now + timedelta(minutes=2))
    assert (await db_session.scalar(select(ScanRun))).error is None
    assert len(queue.ids) == 1
    assert await db_session.scalar(select(func.sum(ScanUsage.scans_count))) == 1


async def test_only_audit_proven_scheduler_queue_expires_and_failure_consumes_window(db_session, monkeypatch):
    _, app_id = await seed(db_session, "pro")
    now = scheduling.cadence_window("daily", scheduling.utc_now()) + timedelta(hours=2)
    app = await db_session.get(App, app_id)
    run = await scheduling.admit_scheduled_profile(db_session, app, ScanProfile.heartbeat,
        now=now, blocked_profiles=CLI_SCANNER_PROFILES, production=True)
    run_id = run.id
    # A historical system-created run without scheduler audit proof is unrelated.
    manual = ScanRun(id=uuid.uuid4(), app_id=app_id, profile=ScanProfile.internetdb,
        status=RunStatus.queued, created_at=now - timedelta(days=2))
    db_session.add(manual)
    await db_session.commit()
    manual_id = manual.id
    queue = Queue()
    await dispatch(db_session, monkeypatch, queue, now + scheduling.MAX_QUEUED_AGE)
    expired = await db_session.get(ScanRun, run_id)
    assert expired.status == RunStatus.failed and expired.finished_at is not None
    assert expired.error == "Scheduled scan expired before execution"
    assert (await db_session.get(ScanRun, manual_id)).status == RunStatus.queued
    assert not queue.calls
    assert await db_session.scalar(select(func.count()).select_from(ScanRun)) == 2
    assert await db_session.scalar(select(func.sum(ScanUsage.scans_count))) == 1


async def test_disabled_profile_cancels_only_its_unstarted_scheduled_run(db_session, monkeypatch):
    _, app_id = await seed(db_session, "pro")
    now = scheduling.utc_now()
    app = await db_session.get(App, app_id)
    run = await scheduling.admit_scheduled_profile(db_session, app, ScanProfile.heartbeat,
        now=now, blocked_profiles=CLI_SCANNER_PROFILES, production=True)
    run_id = run.id
    app.heartbeat_enabled = False
    await db_session.commit()
    queue = Queue()
    await dispatch(db_session, monkeypatch, queue, now + timedelta(minutes=1))
    assert not queue.calls
    stopped = await db_session.get(ScanRun, run_id)
    assert stopped.status == RunStatus.failed
    assert stopped.error == "Scheduled scan is no longer eligible"
    assert stopped.finished_at is not None


@pytest.mark.parametrize("details", [None, {}, {"trigger": "manual"}, "not-json", '{"trigger":"scheduler"}', ["scheduler"], {"trigger": ["scheduler"]}])
async def test_recovery_requires_object_scheduler_trigger_not_similar_audit(db_session, details):
    org_id, app_id = await seed(db_session, "pro")
    now = scheduling.utc_now()
    run = ScanRun(id=uuid.uuid4(), app_id=app_id, profile=ScanProfile.heartbeat,
                  status=RunStatus.queued, created_at=now - timedelta(days=2))
    db_session.add(run)
    await db_session.flush()
    db_session.add(AuditEvent(id=uuid.uuid4(), organization_id=org_id, actor_email="system",
        action="scan.trigger", entity_type="scan_run", entity_id=str(run.id), details=details))
    await db_session.commit()
    run_id = run.id
    queue = Queue()
    await scheduling.recover_scheduled_queue(db_session, queue, now=now,
        blocked_profiles=CLI_SCANNER_PROFILES, production=True)
    assert not queue.calls
    assert (await db_session.get(ScanRun, run_id)).status == RunStatus.queued


async def test_unrelated_old_audits_do_not_starve_recoverable_batch(db_session):
    org_id, app_id = await seed(db_session, "pro")
    now = scheduling.utc_now()
    for _ in range(101):
        run = ScanRun(id=uuid.uuid4(), app_id=app_id, profile=ScanProfile.heartbeat,
                      status=RunStatus.queued, created_at=now - timedelta(days=2))
        db_session.add(run)
        await db_session.flush()
        db_session.add(AuditEvent(id=uuid.uuid4(), organization_id=org_id, actor_email="system",
            action="scan.trigger", entity_type="scan_run", entity_id=str(run.id), details={"trigger": "manual"}))
    owned = ScanRun(id=uuid.uuid4(), app_id=app_id, profile=ScanProfile.heartbeat,
                    status=RunStatus.queued, created_at=now)
    db_session.add(owned)
    await db_session.flush()
    db_session.add(AuditEvent(id=uuid.uuid4(), organization_id=org_id, actor_email="system",
        action="scan.trigger", entity_type="scan_run", entity_id=str(owned.id), details={"trigger": "scheduler"}))
    await db_session.commit()
    owned_id = owned.id
    queue = Queue()
    await scheduling.recover_scheduled_queue(db_session, queue, now=now,
        blocked_profiles=CLI_SCANNER_PROFILES, production=True)
    assert [call[0] for call in queue.calls] == [str(owned_id)]
    assert await db_session.scalar(select(func.count()).select_from(ScanRun).where(ScanRun.status == RunStatus.queued)) == 102


async def test_legacy_jobs_share_dispatcher_and_cannot_duplicate_admission(db_session, monkeypatch):
    await seed(db_session, "pro")
    queue = Queue()
    monkeypatch.setattr(worker, "SessionLocal", async_sessionmaker(db_session.bind, expire_on_commit=False))
    await worker.heartbeat_all({"redis": queue})
    await worker.heartbeat_all({"redis": queue})
    await worker.nuclei_weekly_all({"redis": queue})
    await worker.supply_chain_weekly_all({"redis": queue})
    assert await db_session.scalar(select(func.count()).select_from(ScanRun)) == 1
    assert len(queue.ids) == 1
    jobs = worker.WorkerSettings.cron_jobs
    assert {job.coroutine for job in jobs} == {worker.scheduled_scans_all, worker.process_alert_outbox}
    assert worker.WorkerSettings.timezone == timezone.utc


PG = os.environ.get("STRAZ_TEST_PG_URL")


@pytest.mark.skipif(not PG, reason="STRAZ_TEST_PG_URL not set")
async def test_postgres_concurrent_schedulers_create_exactly_one_admission(monkeypatch):
    target = make_url(PG)
    assert target.host in {"127.0.0.1", "localhost", "::1"}, "Loopback test PostgreSQL required"
    database = "straz_scheduler_" + uuid.uuid4().hex
    admin = create_async_engine(target, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    engine = create_async_engine(target.set(database=database), poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    first_locked = asyncio.Event()
    release_first = asyncio.Event()
    original_lock = scheduling.lock_organization
    calls = 0

    async def controlled_lock(db, org):
        nonlocal calls
        await original_lock(db, org)
        calls += 1
        if calls == 1:
            first_locked.set()
            await release_first.wait()

    async def admit(app_id, now):
        async with factory() as db:
            app = await db.get(App, app_id)
            result = await scheduling.admit_scheduled_profile(db, app, ScanProfile.heartbeat,
                now=now, blocked_profiles=CLI_SCANNER_PROFILES, production=True)
            return result.id if result else None

    tasks = []
    created = False
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database}" TEMPLATE template0'))
        created = True
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as db:
            _, app_id = await seed(db, "agency")
        monkeypatch.setattr(scheduling, "lock_organization", controlled_lock)
        now = scheduling.utc_now()
        first = asyncio.create_task(admit(app_id, now))
        tasks.append(first)
        await asyncio.wait_for(first_locked.wait(), timeout=5)
        second = asyncio.create_task(admit(app_id, now))
        tasks.append(second)
        await asyncio.sleep(0.05)
        assert not second.done(), "Second admission must wait for the real PostgreSQL row lock"
        release_first.set()
        ids = await asyncio.wait_for(asyncio.gather(first, second), timeout=10)
        assert sum(value is not None for value in ids) == 1
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(ScanRun)) == 1
            assert await db.scalar(select(func.sum(ScanUsage.scans_count))) == 1
            assert await db.scalar(select(func.count()).select_from(AuditEvent)) == 1
        # Exercise the UUID -> audit-string correlation and SKIP LOCKED query
        # against PostgreSQL too, not merely the SQLite test dialect.
        queue = Queue()
        for _ in range(2):
            async with factory() as db:
                await scheduling.recover_scheduled_queue(db, queue, now=now + timedelta(minutes=1),
                    blocked_profiles=CLI_SCANNER_PROFILES, production=True)
        assert len(queue.calls) == 2 and len(queue.ids) == 1
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(ScanRun)) == 1
            assert await db.scalar(select(func.sum(ScanUsage.scans_count))) == 1
    finally:
        release_first.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()
        if created:
            async with admin.connect() as connection:
                await connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
        await admin.dispose()
