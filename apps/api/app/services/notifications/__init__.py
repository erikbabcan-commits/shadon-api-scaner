from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import AlertChannel, AlertEvent, App
from app.services.notifications.channels import (
    check_channel_limit,
    list_org_channels,
    mask_sensitive_url,
    validate_channel_for_plan,
)
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
        # channel is either global (app_id is None) or specifically for this app
        stmt = stmt.where((AlertChannel.app_id == None) | (AlertChannel.app_id == app.id))
    else:
        stmt = stmt.where(AlertChannel.app_id == None)

    channels = list(await db.scalars(stmt))
    if not channels:
        return

    current_sev_level = SEVERITY_LEVELS.get(severity.lower(), 1)
    is_test_env = settings.straz_env in ("test", "testing", "development") if settings else True

    for ch in channels:
        ch_min_level = SEVERITY_LEVELS.get(ch.min_severity.lower(), 4)
        if current_sev_level < ch_min_level:
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

        # Send asynchronously
        success = await send_to_channel(
            channel=ch,
            event_type=event_type,
            severity=severity,
            title=title,
            detail=detail,
            app_name=app.name if app else None,
            is_test_env=is_test_env,
        )
        alert_event.status = "sent" if success else "failed"
        await db.commit()
