from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import App, Organization, ScanProfile, ScanRun, ScanUsage

PLANS = {
    "free": {
        "name": "Free",
        "price_eur": 0,
        "max_apps": 1,
        "max_scans_per_month": 10,
        "allowed_profiles": [ScanProfile.heartbeat, ScanProfile.tls, ScanProfile.internetdb],
        "cron_schedule": None,
        "white_label": False,
        "custom_webhook_hmac": False,
        "max_alert_channels": 1,
    },
    "starter": {
        "name": "Starter",
        "price_eur": 29,
        "max_apps": 5,
        "max_scans_per_month": 100,
        "allowed_profiles": [
            ScanProfile.heartbeat,
            ScanProfile.tls,
            ScanProfile.http,
            ScanProfile.safe,
            ScanProfile.internetdb,
            ScanProfile.subdomain,
            ScanProfile.ports,
        ],
        "cron_schedule": "weekly",
        "white_label": False,
        "custom_webhook_hmac": False,
        "max_alert_channels": 3,
    },
    "pro": {
        "name": "Pro",
        "price_eur": 79,
        "max_apps": 25,
        "max_scans_per_month": 1000,
        "allowed_profiles": list(ScanProfile),
        "cron_schedule": "daily",
        "white_label": True,
        "custom_webhook_hmac": True,
        "max_alert_channels": 9999,
    },
    "agency": {
        "name": "Agency",
        "price_eur": 199,
        "max_apps": 999999,
        "max_scans_per_month": 999999,
        "allowed_profiles": list(ScanProfile),
        "cron_schedule": "hourly",
        "white_label": True,
        "custom_webhook_hmac": True,
        "max_alert_channels": 9999,
    },
}


def get_plan_tier(org: Organization) -> str:
    tier = (org.plan_tier or "free").lower()
    if tier not in PLANS:
        return "free"
    # If subscription is past_due or canceled, downgrade to free
    if org.subscription_status and org.subscription_status.lower() in ("canceled", "past_due"):
        return "free"
    return tier


def get_plan_config(org: Organization) -> dict[str, Any]:
    tier = get_plan_tier(org)
    return PLANS[tier]


def get_current_period_bounds(org: Organization) -> tuple[datetime, datetime]:
    if org.current_period_start and org.current_period_end:
        return org.current_period_start, org.current_period_end
    # Calendar month UTC
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return start, end


async def get_current_scan_usage(db: AsyncSession, org_id: uuid.UUID) -> int:
    org = await db.get(Organization, org_id)
    if not org:
        return 0
    start, end = get_current_period_bounds(org)

    stmt = select(func.coalesce(func.sum(ScanUsage.scans_count), 0)).where(
        ScanUsage.org_id == org_id,
        ScanUsage.period_start >= start,
        ScanUsage.period_end <= end,
    )
    recorded = await db.scalar(stmt) or 0

    # Also count queued/running/done runs in current period
    run_count_stmt = (
        select(func.count(ScanRun.id))
        .join(App, ScanRun.app_id == App.id)
        .where(
            App.organization_id == org_id,
            ScanRun.created_at >= start,
            ScanRun.created_at < end,
        )
    )
    runs_in_period = await db.scalar(run_count_stmt) or 0
    return max(int(recorded), int(runs_in_period))


async def check_app_limit(db: AsyncSession, org: Organization) -> tuple[bool, str | None]:
    plan = get_plan_config(org)
    max_apps = plan["max_apps"]

    app_count = (
        await db.scalar(
            select(func.count()).select_from(App).where(App.organization_id == org.id)
        )
        or 0
    )
    if app_count >= max_apps:
        return False, f"Limit {max_apps} aplikácií pre plán {plan['name']} bol dosiahnutý."
    return True, None


async def check_scan_quota(
    db: AsyncSession, org: Organization, profile: ScanProfile
) -> tuple[bool, str | None]:
    plan = get_plan_config(org)

    # 1. Check profile permission
    if profile not in plan["allowed_profiles"]:
        return (
            False,
            f"Profil skenu '{profile.value}' nie je povolený v pláne {plan['name']}. Vyžaduje sa upgrade.",
        )

    # 2. Check monthly scans limit
    max_scans = plan["max_scans_per_month"]
    current_scans = await get_current_scan_usage(db, org.id)
    if current_scans >= max_scans:
        return (
            False,
            f"Mesačný limit {max_scans} skenov pre plán {plan['name']} bol vyčerpaný.",
        )

    return True, None


async def record_scan_admission(db: AsyncSession, org_id: uuid.UUID) -> None:
    org = await db.get(Organization, org_id)
    if not org:
        return
    start, end = get_current_period_bounds(org)

    stmt = select(ScanUsage).where(
        ScanUsage.org_id == org_id,
        ScanUsage.period_start == start,
        ScanUsage.period_end == end,
    )
    usage = await db.scalar(stmt)
    if not usage:
        usage = ScanUsage(
            id=uuid.uuid4(),
            org_id=org_id,
            period_start=start,
            period_end=end,
            scans_count=1,
        )
        db.add(usage)
    else:
        usage.scans_count += 1
    await db.flush()


async def get_org_usage_stats(db: AsyncSession, org: Organization) -> dict[str, Any]:
    plan = get_plan_config(org)
    start, end = get_current_period_bounds(org)

    app_count = (
        await db.scalar(
            select(func.count()).select_from(App).where(App.organization_id == org.id)
        )
        or 0
    )
    scan_count = await get_current_scan_usage(db, org.id)

    return {
        "plan_tier": get_plan_tier(org),
        "plan_name": plan["name"],
        "price_eur": plan["price_eur"],
        "subscription_status": org.subscription_status or "active",
        "current_period_start": start,
        "current_period_end": end,
        "apps_used": app_count,
        "apps_limit": plan["max_apps"],
        "scans_used": scan_count,
        "scans_limit": plan["max_scans_per_month"],
        "allowed_profiles": [p.value for p in plan["allowed_profiles"]],
        "white_label": plan["white_label"],
    }
