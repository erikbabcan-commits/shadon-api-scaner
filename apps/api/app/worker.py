from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    App,
    FindingSeverity,
    FindingSource,
    RunStatus,
    ScanProfile,
    ScanRun,
    TargetStatus,
)
from app.services.findings import make_fingerprint, mark_absent_fixed, upsert_finding
from app.services.ntfy import send_ntfy
from app.services.scanners import run_heartbeat, run_httpx_probe, run_nuclei_safe, run_tlsx


def _severity(value: str) -> FindingSeverity:
    try:
        return FindingSeverity(value)
    except ValueError:
        return FindingSeverity.info


async def _set_run(db, run_id: uuid.UUID, status: RunStatus, error: str | None = None) -> ScanRun | None:
    run = await db.get(ScanRun, run_id)
    if not run:
        return None
    run.status = status
    if status == RunStatus.running:
        run.started_at = datetime.now(timezone.utc)
    if status in (RunStatus.done, RunStatus.failed):
        run.finished_at = datetime.now(timezone.utc)
        run.error = error
    return run


async def execute_scan_run(ctx, run_id: str) -> None:
    settings = get_settings()
    redis = ctx["redis"]
    rid = uuid.UUID(run_id)

    async with SessionLocal() as db:
        run = await db.get(ScanRun, rid)
        if not run:
            return
        profile = run.profile
        app = await db.scalar(
            select(App).where(App.id == run.app_id).options(selectinload(App.targets))
        )
        if not app:
            await _set_run(db, rid, RunStatus.failed, "app not found")
            await db.commit()
            return

        verified = [t for t in app.targets if t.status == TargetStatus.verified]
        if not verified and profile != ScanProfile.heartbeat:
            await _set_run(db, rid, RunStatus.failed, "no verified targets")
            await db.commit()
            return

        heavy = profile in (ScanProfile.tls, ScanProfile.http, ScanProfile.safe)
        lock_token = None
        if heavy:
            lock_token = await redis.set(
                settings.heavy_scan_lock_key,
                run_id,
                nx=True,
                ex=settings.heavy_scan_lock_ttl,
            )
            if not lock_token:
                await _set_run(db, rid, RunStatus.failed, "heavy scan already running")
                await db.commit()
                return

        await _set_run(db, rid, RunStatus.running)
        await db.commit()

        try:
            if profile == ScanProfile.heartbeat:
                await _heartbeat(db, app)
            elif profile == ScanProfile.tls:
                await _tls(db, app, verified)
            elif profile == ScanProfile.http:
                await _http(db, app, verified)
            elif profile == ScanProfile.safe:
                await _nuclei(db, app, verified)
            await _set_run(db, rid, RunStatus.done)
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            async with SessionLocal() as db2:
                await _set_run(db2, rid, RunStatus.failed, str(exc)[:2000])
                await db2.commit()
        finally:
            if heavy and lock_token:
                current = await redis.get(settings.heavy_scan_lock_key)
                if isinstance(current, bytes):
                    current = current.decode()
                if current == run_id:
                    await redis.delete(settings.heavy_scan_lock_key)


async def _heartbeat(db, app: App) -> None:
    prev_up = app.last_up
    result = await run_heartbeat(app.base_url)
    app.last_status_code = result.status_code
    app.last_latency_ms = result.latency_ms
    app.last_title = result.title
    app.last_up = result.ok
    app.last_checked_at = datetime.now(timezone.utc)
    if not result.ok:
        await upsert_finding(
            db,
            app_id=app.id,
            target_id=None,
            source=FindingSource.heartbeat,
            severity=FindingSeverity.high,
            title=f"App down: {app.name}",
            detail=result.error or f"status={result.status_code}",
            fingerprint=make_fingerprint("heartbeat-down", str(app.id)),
            notify=True,
        )
        if prev_up is True:
            await send_ntfy(
                f"Stráž: {app.name} down",
                result.error or f"HTTP {result.status_code}",
                priority=5,
                tags="x",
            )
    else:
        await mark_absent_fixed(
            db,
            app_id=app.id,
            source=FindingSource.heartbeat,
            seen_fingerprints=set(),
        )


async def _tls(db, app: App, targets) -> None:
    seen: set[str] = set()
    for target in targets:
        host = target.host
        if "://" in host:
            from urllib.parse import urlparse

            host = urlparse(host).hostname or host
        for item in await run_tlsx(host):
            fp = make_fingerprint(item.fingerprint_key)
            seen.add(fp)
            await upsert_finding(
                db,
                app_id=app.id,
                target_id=target.id,
                source=FindingSource.tls,
                severity=_severity(item.severity),
                title=item.title,
                detail=item.detail,
                fingerprint=fp,
                notify=True,
            )
    await mark_absent_fixed(db, app_id=app.id, source=FindingSource.tls, seen_fingerprints=seen)


async def _http(db, app: App, targets) -> None:
    seen: set[str] = set()
    urls = {app.base_url}
    for target in targets:
        h = target.host
        if not h.startswith("http"):
            h = f"https://{h}"
        urls.add(h)
    for url in urls:
        for item in await run_httpx_probe(url):
            fp = make_fingerprint(item.fingerprint_key)
            seen.add(fp)
            notify = not (
                item.severity == "info" and item.fingerprint_key.startswith("httpx-tech|")
            )
            await upsert_finding(
                db,
                app_id=app.id,
                target_id=None,
                source=FindingSource.httpx,
                severity=_severity(item.severity),
                title=item.title,
                detail=item.detail,
                fingerprint=fp,
                notify=notify,
            )
    await mark_absent_fixed(db, app_id=app.id, source=FindingSource.httpx, seen_fingerprints=seen)


async def _nuclei(db, app: App, targets) -> None:
    seen: set[str] = set()
    urls = {app.base_url}
    for target in targets:
        h = target.host
        if not h.startswith("http"):
            h = f"https://{h}"
        urls.add(h)
    work = Path("/tmp/straz-nuclei")
    work.mkdir(parents=True, exist_ok=True)
    for url in urls:
        for item in await run_nuclei_safe(url, work):
            fp = make_fingerprint(item.fingerprint_key)
            seen.add(fp)
            await upsert_finding(
                db,
                app_id=app.id,
                target_id=None,
                source=FindingSource.nuclei,
                severity=_severity(item.severity),
                title=item.title,
                detail=item.detail,
                fingerprint=fp,
                notify=True,
            )
    await mark_absent_fixed(db, app_id=app.id, source=FindingSource.nuclei, seen_fingerprints=seen)


async def heartbeat_all(ctx) -> None:
    async with SessionLocal() as db:
        apps = (await db.scalars(select(App).where(App.heartbeat_enabled.is_(True)))).all()
        for app in apps:
            run = ScanRun(app_id=app.id, profile=ScanProfile.heartbeat, status=RunStatus.queued)
            db.add(run)
            await db.flush()
            await ctx["redis"].enqueue_job("execute_scan_run", str(run.id))
        await db.commit()


async def nuclei_weekly_all(ctx) -> None:
    async with SessionLocal() as db:
        apps = (await db.scalars(select(App).where(App.safe_enabled.is_(True)))).all()
        for app in apps:
            run = ScanRun(app_id=app.id, profile=ScanProfile.safe, status=RunStatus.queued)
            db.add(run)
            await db.flush()
            await ctx["redis"].enqueue_job("execute_scan_run", str(run.id))
        await db.commit()


def _parse_cron(expr: str):
    # "0 3 * * 1" -> minute hour day month weekday
    parts = expr.split()
    if len(parts) != 5:
        return cron(nuclei_weekly_all, hour=3, minute=0, weekday=0)
    minute, hour, _dom, _mon, dow = parts

    def _num(v: str, default: int = 0) -> int:
        return default if v == "*" else int(v)

    # arq weekday: 0=Mon ... 6=Sun; cron often 0/7=Sun 1=Mon
    wd = None if dow == "*" else (int(dow) + 6) % 7
    return cron(
        nuclei_weekly_all,
        hour=_num(hour, 3),
        minute=_num(minute, 0),
        weekday=wd if wd is not None else 0,
    )


async def startup(ctx) -> None:
    settings = get_settings()
    ctx["settings"] = settings


class WorkerSettings:
    settings = get_settings()
    functions = [execute_scan_run, heartbeat_all, nuclei_weekly_all]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    cron_jobs = [
        cron(heartbeat_all, minute={i for i in range(0, 60, max(1, settings.heartbeat_interval_minutes))}),
        _parse_cron(settings.nuclei_weekly_cron),
    ]
