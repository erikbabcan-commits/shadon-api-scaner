import logging
import secrets
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import SessionLocal
from app.logging import setup_logging
from app.models import (
    App,
    FindingSeverity,
    FindingSource,
    RunStatus,
    ScanProfile,
    ScanRun,
    Target,
    TargetStatus,
)
from app.routers.findings import _invalidate_overview_cache

logger = logging.getLogger("straz.worker")
from app.services.findings import make_fingerprint, mark_absent_fixed, upsert_finding
from app.services.internetdb import fetch_internetdb, resolve_public_ips
from app.services.ntfy import send_ntfy
from app.services.scanners import (
    git_clone,
    run_gitleaks,
    run_heartbeat,
    run_httpx_probe,
    run_naabu,
    run_nuclei_safe,
    run_subfinder,
    run_tlsx,
    run_trivy_fs,
    run_trivy_image,
)
from app.services.verify import extract_hostname


HEAVY_PROFILES = {
    ScanProfile.tls,
    ScanProfile.http,
    ScanProfile.safe,
    ScanProfile.subdomain,
    ScanProfile.ports,
    ScanProfile.trivy_fs,
    ScanProfile.trivy_image,
    ScanProfile.gitleaks,
}


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

        heavy = profile in HEAVY_PROFILES
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

        logger.info("Starting scan run %s (profile=%s, app=%s)", run_id, profile.value, app.name)
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
            elif profile == ScanProfile.internetdb:
                await _internetdb(db, app, verified, redis)
            elif profile == ScanProfile.subdomain:
                await _subdomain(db, app, verified)
            elif profile == ScanProfile.ports:
                await _ports(db, app, verified, settings.naabu_ports)
            elif profile == ScanProfile.trivy_fs:
                await _trivy_fs(db, app)
            elif profile == ScanProfile.trivy_image:
                await _trivy_image(db, app)
            elif profile == ScanProfile.gitleaks:
                await _gitleaks(db, app)
            else:
                await _set_run(db, rid, RunStatus.failed, f"unknown profile {profile}")
                await db.commit()
                return

            await _set_run(db, rid, RunStatus.done)
            await db.commit()
            await _invalidate_overview_cache(settings)
            logger.info("Scan run %s completed successfully (app=%s)", run_id, app.name)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Scan run %s failed: %s", run_id, exc)
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
                    logger.debug("Released heavy scan lock for run %s", run_id)


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
        host = extract_hostname(target.host)
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


async def _internetdb(db, app: App, targets, redis) -> None:
    settings = get_settings()
    seen: set[str] = set()
    for target in targets:
        ips = resolve_public_ips(target.host)
        if not ips:
            continue
        for ip in ips:
            for item in await fetch_internetdb(ip, settings=settings, redis=redis):
                fp = make_fingerprint(item.fingerprint_key)
                seen.add(fp)
                await upsert_finding(
                    db,
                    app_id=app.id,
                    target_id=target.id,
                    source=FindingSource.internetdb,
                    severity=_severity(item.severity),
                    title=item.title,
                    detail=item.detail,
                    fingerprint=fp,
                    notify=True,
                )
    await mark_absent_fixed(
        db, app_id=app.id, source=FindingSource.internetdb, seen_fingerprints=seen
    )


async def _subdomain(db, app: App, targets) -> None:
    seen: set[str] = set()
    existing_hosts = {extract_hostname(t.host).lower() for t in app.targets}
    for target in targets:
        domain = extract_hostname(target.host)
        # skip bare IPs
        try:
            import ipaddress

            ipaddress.ip_address(domain)
            continue
        except ValueError:
            pass
        for host in await run_subfinder(domain):
            host = host.lower().rstrip(".")
            if host in existing_hosts:
                continue
            existing_hosts.add(host)
            db.add(
                Target(
                    app_id=app.id,
                    host=host,
                    verify_token=secrets.token_urlsafe(24),
                    status=TargetStatus.pending,
                )
            )
            fp = make_fingerprint("subdomain-candidate", str(app.id), host)
            seen.add(fp)
            await upsert_finding(
                db,
                app_id=app.id,
                target_id=target.id,
                source=FindingSource.subdomain,
                severity=FindingSeverity.info,
                title=f"New subdomain candidate: {host}",
                detail="Pending ownership verify before scans",
                fingerprint=fp,
                notify=False,
            )
    await db.flush()
    await mark_absent_fixed(
        db, app_id=app.id, source=FindingSource.subdomain, seen_fingerprints=seen
    )


async def _ports(db, app: App, targets, ports: str) -> None:
    seen: set[str] = set()
    for target in targets:
        host = extract_hostname(target.host)
        for item in await run_naabu(host, ports):
            fp = make_fingerprint(item.fingerprint_key)
            seen.add(fp)
            await upsert_finding(
                db,
                app_id=app.id,
                target_id=target.id,
                source=FindingSource.naabu,
                severity=_severity(item.severity),
                title=item.title,
                detail=item.detail,
                fingerprint=fp,
                notify=False,
            )
    await mark_absent_fixed(db, app_id=app.id, source=FindingSource.naabu, seen_fingerprints=seen)


async def _trivy_fs(db, app: App) -> None:
    if not app.git_url:
        raise RuntimeError("git_url not set on app")
    work = Path(f"/tmp/straz-git/{app.id}")
    ok, err = await git_clone(app.git_url, work)
    if not ok:
        raise RuntimeError(err)
    seen: set[str] = set()
    try:
        for item in await run_trivy_fs(work):
            fp = make_fingerprint(item.fingerprint_key)
            seen.add(fp)
            await upsert_finding(
                db,
                app_id=app.id,
                target_id=None,
                source=FindingSource.trivy,
                severity=_severity(item.severity),
                title=item.title,
                detail=item.detail,
                fingerprint=fp,
                notify=True,
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    await mark_absent_fixed(db, app_id=app.id, source=FindingSource.trivy, seen_fingerprints=seen)


async def _trivy_image(db, app: App) -> None:
    if not app.image_ref:
        raise RuntimeError("image_ref not set on app")
    seen: set[str] = set()
    for item in await run_trivy_image(app.image_ref):
        fp = make_fingerprint(item.fingerprint_key)
        seen.add(fp)
        await upsert_finding(
            db,
            app_id=app.id,
            target_id=None,
            source=FindingSource.trivy,
            severity=_severity(item.severity),
            title=item.title,
            detail=item.detail,
            fingerprint=fp,
            notify=True,
        )
    await mark_absent_fixed(db, app_id=app.id, source=FindingSource.trivy, seen_fingerprints=seen)


async def _gitleaks(db, app: App) -> None:
    if not app.git_url:
        raise RuntimeError("git_url not set on app")
    work = Path(f"/tmp/straz-git/{app.id}-gitleaks")
    ok, err = await git_clone(app.git_url, work)
    if not ok:
        raise RuntimeError(err)
    seen: set[str] = set()
    try:
        for item in await run_gitleaks(work):
            fp = make_fingerprint(item.fingerprint_key)
            seen.add(fp)
            await upsert_finding(
                db,
                app_id=app.id,
                target_id=None,
                source=FindingSource.gitleaks,
                severity=_severity(item.severity),
                title=item.title,
                detail=item.detail,
                fingerprint=fp,
                notify=True,
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    await mark_absent_fixed(
        db, app_id=app.id, source=FindingSource.gitleaks, seen_fingerprints=seen
    )


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


async def supply_chain_weekly_all(ctx) -> None:
    async with SessionLocal() as db:
        apps = (
            await db.scalars(
                select(App).where(
                    (App.trivy_enabled.is_(True) & App.git_url.is_not(None))
                    | (App.trivy_enabled.is_(True) & App.image_ref.is_not(None))
                    | (App.gitleaks_enabled.is_(True) & App.git_url.is_not(None))
                )
            )
        ).all()
        for app in apps:
            if app.trivy_enabled and app.git_url:
                run = ScanRun(app_id=app.id, profile=ScanProfile.trivy_fs, status=RunStatus.queued)
                db.add(run)
                await db.flush()
                await ctx["redis"].enqueue_job("execute_scan_run", str(run.id))
            if app.trivy_enabled and app.image_ref:
                run = ScanRun(app_id=app.id, profile=ScanProfile.trivy_image, status=RunStatus.queued)
                db.add(run)
                await db.flush()
                await ctx["redis"].enqueue_job("execute_scan_run", str(run.id))
            if app.gitleaks_enabled and app.git_url:
                run = ScanRun(app_id=app.id, profile=ScanProfile.gitleaks, status=RunStatus.queued)
                db.add(run)
                await db.flush()
                await ctx["redis"].enqueue_job("execute_scan_run", str(run.id))
        await db.commit()


def _parse_cron(expr: str, fn):
    parts = expr.split()
    if len(parts) != 5:
        return cron(fn, hour=3, minute=0, weekday=0)
    minute, hour, _dom, _mon, dow = parts

    def _num(v: str, default: int = 0) -> int:
        return default if v == "*" else int(v)

    wd = None if dow == "*" else (int(dow) + 6) % 7
    return cron(
        fn,
        hour=_num(hour, 3),
        minute=_num(minute, 0),
        weekday=wd if wd is not None else 0,
    )


async def startup(ctx) -> None:
    settings = get_settings()
    setup_logging(settings.is_production)
    ctx["settings"] = settings
    logger.info("ARQ Worker starting up...")

    binaries = ["nuclei", "tlsx", "httpx", "naabu", "subfinder", "trivy", "gitleaks"]
    status_map = {b: shutil.which(b) is not None for b in binaries}
    logger.info("Scanner binary status: %s", status_map)


async def shutdown(ctx) -> None:
    logger.info("ARQ Worker shutting down cleanly.")


class WorkerSettings:
    settings = get_settings()
    functions = [
        execute_scan_run,
        heartbeat_all,
        nuclei_weekly_all,
        supply_chain_weekly_all,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    cron_jobs = [
        cron(heartbeat_all, minute={i for i in range(0, 60, max(1, settings.heartbeat_interval_minutes))}),
        _parse_cron(settings.nuclei_weekly_cron, nuclei_weekly_all),
        _parse_cron(settings.supply_chain_weekly_cron, supply_chain_weekly_all),
    ]
