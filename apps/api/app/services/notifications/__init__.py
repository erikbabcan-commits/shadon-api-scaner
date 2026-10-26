from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
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


async def process_alert_outbox(ctx: dict[str, Any]) -> None:
    import asyncio
    from datetime import datetime, timezone
    from app.db import SessionLocal
    pending: list[tuple[AlertEvent, AlertChannel, str | None]] = []
    async with SessionLocal() as db:
        rows = list(await db.scalars(select(AlertEvent).where(AlertEvent.status == "pending")
            .order_by(AlertEvent.created_at).limit(25).with_for_update(skip_locked=True)))
        for row in rows:
            channel = await db.get(AlertChannel, row.channel_id)
            app = await db.get(App, row.app_id) if row.app_id else None
            if channel is None or not channel.is_active or channel.org_id != row.org_id or (app and app.organization_id != row.org_id):
                row.status = "failed"
                continue
            row.status = "processing"
            pending.append((row, channel, app.name if app else None))
        await db.commit()
    semaphore = asyncio.Semaphore(8)
    async def deliver(item: tuple[AlertEvent, AlertChannel, str | None]) -> tuple[uuid.UUID, bool]:
        row, channel, app_name = item
        async with semaphore:
            success = await send_to_channel(channel, row.event_type, row.severity, row.title, row.detail, app_name)
        return row.id, success
    results = await asyncio.gather(*(deliver(item) for item in pending))
    async with SessionLocal() as db:
        for event_id, success in results:
            processed_event = await db.get(AlertEvent, event_id)
            if processed_event and processed_event.status == "processing":
                processed_event.status = "sent" if success else "failed"
                processed_event.processed_at = datetime.now(timezone.utc)
        await db.commit()
