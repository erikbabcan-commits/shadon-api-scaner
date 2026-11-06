from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import uuid
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import AlertChannel, AlertEvent, App

from app.services.notifications.transport import send_to_channel

logger = logging.getLogger("straz.notifications")

SEVERITY_LEVELS = {
    "info": 1,
    "low": 2,
    "medium": 3,
    "high": 4,
    "critical": 5,
}


async def test_channel_delivery(
    channel: AlertChannel,
    settings: Settings,
) -> bool:
    is_test_env = settings.straz_env in ("test", "testing", "development")
    return await send_to_channel(
        channel=channel,
        event_type="test.alert",
        severity="info",
        title="Testovacia správa zo systému Stráž",
        detail="Overenie spojenia a doručenia upozornení do tohto kanála prebehlo úspešne.",
        app_name="Testovacia aplikácia",
        is_test_env=is_test_env,
    )


async def dispatch_alert(
    db: AsyncSession,
    org_id: uuid.UUID,
    event_type: str,
    severity: str,
    title: str,
    detail: str | None = None,
    app: App | None = None,
    settings: Settings | None = None,
) -> None:
    # 1. Find matching active channels for this organization
    stmt = select(AlertChannel).where(
        AlertChannel.org_id == org_id,
        AlertChannel.is_active == True,
    )
    if app:
        if app.organization_id != org_id:
            raise ValueError("Alert tenant mismatch")
        # channel is either global (app_id is None) or specifically for this app
        stmt = stmt.where((AlertChannel.app_id == None) | (AlertChannel.app_id == app.id))
    else:
        stmt = stmt.where(AlertChannel.app_id == None)

    channels = list(await db.scalars(stmt))
    if not channels:
        return

    current_sev_level = SEVERITY_LEVELS.get(severity.lower(), 1)

    for ch in channels:
        ch_min_level = SEVERITY_LEVELS.get(ch.min_severity.lower(), 4)
        if event_type == "finding.created" and current_sev_level < ch_min_level:
            continue

        events_list = json.loads(ch.events) if ch.events else ["finding.created"]
        if event_type not in events_list and "all" not in events_list:
            continue

        # Record alert event
        alert_event = AlertEvent(
            id=uuid.uuid4(),
            org_id=org_id,
            app_id=app.id if app else None,
            channel_id=ch.id,
            event_type=event_type,
            severity=severity,
            title=title,
            detail=detail,
            status="pending",
        )
        db.add(alert_event)
        await db.flush()

        # Committed together with findings; delivery is performed after commit.


OUTBOX_MAX_ATTEMPTS = 5
OUTBOX_LEASE = timedelta(minutes=2)
OUTBOX_RETRY_BASE_SECONDS = 30
OUTBOX_RETRY_MAX_SECONDS = 15 * 60
OUTBOX_MAX_AGE = timedelta(hours=24)
OUTBOX_BATCH_SIZE = 25
OUTBOX_CONCURRENCY = 8
OUTBOX_DELIVERY_TIMEOUT_SECONDS = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _due(now: datetime):
    return or_(
        and_(AlertEvent.status == "pending", or_(AlertEvent.next_attempt_at.is_(None), AlertEvent.next_attempt_at <= now)),
        and_(AlertEvent.status == "processing", or_(AlertEvent.lease_expires_at.is_(None), AlertEvent.lease_expires_at <= now)),
    )


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def _channel_for_event(db: AsyncSession, row: AlertEvent):
    channel = await db.get(AlertChannel, row.channel_id) if row.channel_id else None
    app = await db.get(App, row.app_id) if row.app_id else None
    if (
        channel is None or not channel.is_active or channel.org_id != row.org_id
        or (row.app_id is not None and (app is None or app.organization_id != row.org_id))
        or (channel.app_id is not None and channel.app_id != row.app_id)
    ):
        return None
    try:
        events = json.loads(channel.events) if channel.events else ["finding.created"]
        if not isinstance(events, list) or (row.event_type not in events and "all" not in events):
            return None
    except (TypeError, ValueError):
        return None
    if row.event_type == "finding.created" and SEVERITY_LEVELS.get(row.severity.lower(), 1) < SEVERITY_LEVELS.get(channel.min_severity.lower(), 4):
        return None
    return channel, app.name if app else None


@dataclass(frozen=True)
class AlertClaim:
    event_id: uuid.UUID
    token: uuid.UUID
    attempt: int


async def _claim_alerts(session_factory) -> list[AlertClaim]:
    """Commit ownership before I/O; SKIP LOCKED permits parallel PG consumers.

    Conditional UPDATE also fences stale candidate rows on dialects without
    SKIP LOCKED. Existing sent/failed rows are never automatically retried.
    Legacy processing rows without a lease can be recovered after migration.
    """
    now = _utcnow()
    claims = []
    async with session_factory() as db:
        rows = list(await db.scalars(
            select(AlertEvent).where(_due(now)).order_by(AlertEvent.created_at, AlertEvent.id)
            .limit(OUTBOX_BATCH_SIZE).with_for_update(skip_locked=True)
        ))
        for row in rows:
            ownership = (
                AlertEvent.lease_token.is_(None) if row.lease_token is None
                else AlertEvent.lease_token == row.lease_token
            )
            criteria = (AlertEvent.id == row.id, AlertEvent.status == row.status,
                        AlertEvent.attempt_count == row.attempt_count, ownership, _due(now))
            valid_channel = await _channel_for_event(db, row)
            exhausted = row.attempt_count >= OUTBOX_MAX_ATTEMPTS or _aware(row.created_at) + OUTBOX_MAX_AGE <= now
            if valid_channel is None or exhausted:
                await db.execute(update(AlertEvent).where(*criteria).values(
                    status="failed", processed_at=now, next_attempt_at=None,
                    lease_token=None, lease_expires_at=None,
                ).execution_options(synchronize_session=False))
                continue
            token = uuid.uuid4()
            updated = await db.scalar(update(AlertEvent).where(*criteria).values(
                status="processing", attempt_count=row.attempt_count + 1,
                lease_token=token, lease_expires_at=now + OUTBOX_LEASE,
                next_attempt_at=None, processed_at=None,
            ).returning(AlertEvent.id).execution_options(synchronize_session=False))
            if updated is not None:
                claims.append(AlertClaim(row.id, token, row.attempt_count + 1))
        await db.commit()
    return claims


async def _finish_claim(session_factory, claim: AlertClaim, *, success: bool, terminal: bool = False) -> bool:
    """A worker whose lease expired/replaced must never acknowledge a new claim."""
    now = _utcnow()
    failed = terminal or claim.attempt >= OUTBOX_MAX_ATTEMPTS
    delay = min(OUTBOX_RETRY_MAX_SECONDS, OUTBOX_RETRY_BASE_SECONDS * 2 ** (claim.attempt - 1))
    values = dict(
        status="sent" if success else ("failed" if failed else "pending"),
        processed_at=now if success or failed else None,
        next_attempt_at=None if success or failed else now + timedelta(seconds=delay),
        lease_token=None, lease_expires_at=None,
    )
    async with session_factory() as db:
        changed = await db.scalar(update(AlertEvent).where(
            AlertEvent.id == claim.event_id, AlertEvent.status == "processing",
            AlertEvent.lease_token == claim.token, AlertEvent.lease_expires_at > now,
        ).values(**values).returning(AlertEvent.id))
        await db.commit()
        return changed is not None


async def _deliver_claim(session_factory, claim: AlertClaim) -> None:
    async with session_factory() as db:
        row = await db.scalar(select(AlertEvent).where(
            AlertEvent.id == claim.event_id, AlertEvent.status == "processing",
            AlertEvent.lease_token == claim.token, AlertEvent.lease_expires_at > _utcnow(),
        ))
        if row is None:
            return
        destination = await _channel_for_event(db, row)
        if destination is None:
            await db.rollback()
            await _finish_claim(session_factory, claim, success=False, terminal=True)
            return
        channel, app_name = destination
    try:
        async with asyncio.timeout(OUTBOX_DELIVERY_TIMEOUT_SECONDS):
            success = await send_to_channel(
                channel, row.event_type, row.severity, row.title, row.detail, app_name,
                event_id=claim.event_id,
            )
    except Exception as exc:
        # Never log channel URLs, payloads or exception text (webhook secrets).
        logger.warning("Outbox delivery failed (event_id=%s, error_type=%s)", claim.event_id, type(exc).__name__)
        success = False
    await _finish_claim(session_factory, claim, success=success)


async def process_alert_outbox(ctx: dict[str, Any]) -> None:
    """At-least-once bounded delivery, not an exactly-once external transaction.

    If a process dies after the receiver accepts bytes but before DB ack, its
    expired lease is retried and the receiver may see a duplicate. Webhook
    event IDs are stable across retries so capable receivers can deduplicate.
    Cancellation leaves the lease recoverable; one destination's exception
    does not strand the rest of a committed batch.
    Exhausted/expired events become failed: external receipt is not guaranteed.
    """
    from app.db import SessionLocal
    claims = await _claim_alerts(SessionLocal)
    semaphore = asyncio.Semaphore(OUTBOX_CONCURRENCY)

    async def deliver(claim):
        async with semaphore:
            await _deliver_claim(SessionLocal, claim)

    await asyncio.gather(*(deliver(claim) for claim in claims))
