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
    CLI_SCANNER_PROFILES,
    CLI_SCANNER_UNAVAILABLE,
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
from app.services.internetdb import fetch_internetdb
from app.services.notifications import dispatch_alert, process_alert_outbox
from app.services.scanners import (
    git_clone,
    run_gitleaks,
    run_heartbeat,
    run_httpx_probe,
    run_naabu,
    run_nuclei_safe,
    run_secrets_sast,
    run_subfinder,
    run_tlsx,
    run_trivy_fs,
    run_trivy_image,
    run_whois_rdap,
)
from app.services.verify import extract_hostname
from app.services.safe_http import validate_public_url, resolve_public_addresses


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
        run = await db.scalar(select(ScanRun).where(ScanRun.id == rid).with_for_update())
        if not run or run.status != RunStatus.queued:
            return
        profile = run.profile
        if profile in CLI_SCANNER_PROFILES:
            await _set_run(db, rid, RunStatus.failed, CLI_SCANNER_UNAVAILABLE)
            await db.commit()
            return
        app = await db.scalar(
            select(App).where(App.id == run.app_id).options(selectinload(App.targets))
        )
        if not app:
            await _set_run(db, rid, RunStatus.failed, "app not found")
            await db.commit()
            return

        verified = [t for t in app.targets if t.status == TargetStatus.verified]
        if settings.is_production and any(t.trusted_private for t in verified):
            await _set_run(db, rid, RunStatus.failed, "Private targets require an isolated worker")
            await db.commit()
            return
        if not verified and profile != ScanProfile.heartbeat:
            await _set_run(db, rid, RunStatus.failed, "no verified targets")
            await db.commit()
            return

        try:
            for target in verified:
                value = target.host if "://" in target.host else f"https://{target.host}"
                url = validate_public_url(value)
                await resolve_public_addresses(url.host, url.port or 443)
        except (ValueError, OSError, TimeoutError):
            await _set_run(db, rid, RunStatus.failed, "Target is unavailable or non-public")
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
            db.info["scan_run_id"] = rid
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

            run.observations_complete = True
            await _set_run(db, rid, RunStatus.done)
            await db.commit()
            await _invalidate_overview_cache(settings, app.organization_id)
            logger.info("Scan run %s completed successfully (app=%s)", run_id, app.name)
        except Exception as exc:  # noqa: BLE001
            logger.error("Scan run %s failed (error_type=%s)", run_id, type(exc).__name__)
            await db.rollback()
            async with SessionLocal() as db2:
                await _set_run(db2, rid, RunStatus.failed, "Scanner execution failed")
                await db2.commit()
        finally:
            if heavy and lock_token:
                await redis.eval(
                    "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end",
                    1, settings.heavy_scan_lock_key, run_id,
                )


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
        if prev_up is not False and app.organization_id:
            await dispatch_alert(db, app.organization_id, "app.down", "critical", f"App down: {app.name}", result.error or "HTTP availability failure", app)

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
        for item in await run_whois_rdap(host):
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
    urls = {app.base_url} if extract_hostname(app.base_url) in {extract_hostname(t.host) for t in targets} else set()
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
    urls = {app.base_url} if extract_hostname(app.base_url) in {extract_hostname(t.host) for t in targets} else set()
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
        # A failed or non-public DNS lookup is incomplete coverage, not an
        # empty observation that may close existing vulnerability findings.
        ips = await resolve_public_addresses(extract_hostname(target.host), 443)
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
        for item in await run_secrets_sast(work):
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


async def _schedule_profile(ctx, db, app: App, profile: ScanProfile, *, now=None) -> None:
    from app.services.scheduling import admit_scheduled_profile, publish_scheduled_run, utc_now

    run = await admit_scheduled_profile(
        db, app, profile, now=now or utc_now(),
        blocked_profiles=CLI_SCANNER_PROFILES, production=get_settings().is_production,
    )
    if run is not None:
        # A crash here leaves a durable queued admission. The next dispatcher
        # republishes that same row/id, without consuming additional quota.
        await publish_scheduled_run(ctx["redis"], run)


async def scheduled_scans_all(ctx, *, now=None, profiles=None) -> None:
    from app.services.scheduling import recover_scheduled_queue, utc_now

    now = now or utc_now()
    profiles = tuple(ScanProfile) if profiles is None else profiles
    async with SessionLocal() as db:
        await recover_scheduled_queue(
            db, ctx["redis"], now=now,
            blocked_profiles=CLI_SCANNER_PROFILES, production=get_settings().is_production,
        )
        ids = list(await db.scalars(select(App.id).where(App.organization_id.is_not(None)).order_by(App.id)))
        for app_id in ids:
            for profile in profiles:
                app = await db.get(App, app_id)
                if app is not None:
                    await _schedule_profile(ctx, db, app, profile, now=now)


# Keep already-enqueued legacy job names executable during deployment. They
# use the same cadence/deduplication rules and have no independent cron jobs.
async def heartbeat_all(ctx) -> None:
    await scheduled_scans_all(ctx, profiles=(ScanProfile.heartbeat,))


async def nuclei_weekly_all(ctx) -> None:
    await scheduled_scans_all(ctx, profiles=(ScanProfile.safe,))


async def supply_chain_weekly_all(ctx) -> None:
    await scheduled_scans_all(ctx, profiles=(ScanProfile.trivy_fs, ScanProfile.trivy_image, ScanProfile.gitleaks))


async def startup(ctx) -> None:
    settings = get_settings()
    setup_logging(settings.is_production)
    ctx["settings"] = settings
    from app.migrations import assert_schema_at_head
    await assert_schema_at_head()
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
        scheduled_scans_all,
        heartbeat_all,
        nuclei_weekly_all,
        supply_chain_weekly_all,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    timezone = timezone.utc
    cron_jobs = [
        cron(process_alert_outbox, minute=set(range(60))),
        cron(scheduled_scans_all, minute=set(range(60)), run_at_startup=True),
    ]
