from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlertChannel, Organization
from app.services.quota import get_plan_config, get_plan_tier


def mask_sensitive_url(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if not parsed.hostname:
        return "https://***"
    return f"{parsed.scheme}://{parsed.hostname}/***"


def mask_token(token: str | None) -> str | None:
    if not token:
        return None
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"


def validate_channel_for_plan(org: Organization, platform: str, has_secret: bool) -> None:
    plan = get_plan_config(org)
    tier = get_plan_tier(org)

    allowed_platforms = {
        "free": ["ntfy", "webhook"],
        "starter": ["slack", "discord", "ntfy", "webhook"],
        "pro": ["slack", "discord", "teams", "webhook", "ntfy"],
        "agency": ["slack", "discord", "teams", "webhook", "ntfy"],
    }.get(tier, ["ntfy", "webhook"])

    if platform.lower() not in allowed_platforms:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Platforma '{platform}' nie je dostupná v pláne {plan['name']}. Vyžaduje sa upgrade.",
            headers={"X-Upgrade-Required": "true"},
        )

    if platform.lower() == "webhook" and has_secret and not plan.get("custom_webhook_hmac"):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Podpisovanie webhookov (HMAC-SHA256) je dostupné iba v pláne Pro a Agency.",
            headers={"X-Upgrade-Required": "true"},
        )


async def check_channel_limit(db: AsyncSession, org: Organization) -> None:
    plan = get_plan_config(org)
    max_channels = plan.get("max_alert_channels", 1)

    count = (
        await db.scalar(
            select(func.count()).select_from(AlertChannel).where(AlertChannel.org_id == org.id)
        )
        or 0
    )
    if count >= max_channels:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Dosiahli ste maximálny počet kanálov ({max_channels}) pre plán {plan['name']}.",
            headers={"X-Upgrade-Required": "true"},
        )


async def list_org_channels(db: AsyncSession, org_id: uuid.UUID) -> list[dict[str, Any]]:
    stmt = (
        select(AlertChannel)
        .where(AlertChannel.org_id == org_id)
        .order_by(AlertChannel.created_at.desc())
    )
    channels = list(await db.scalars(stmt))
    return [
        {
            "id": c.id,
            "org_id": c.org_id,
            "app_id": c.app_id,
            "platform": c.platform,
            "name": c.name,
            "destination_url_masked": mask_sensitive_url(c.destination_url),
            "has_secret": bool(c.secret_token),
            "min_severity": c.min_severity,
            "events": json.loads(c.events) if c.events else [],
            "is_active": c.is_active,
            "created_at": c.created_at,
        }
        for c in channels
    ]
