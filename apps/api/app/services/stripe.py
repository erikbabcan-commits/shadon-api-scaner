from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import BillingEvent, Organization

logger = logging.getLogger("straz.stripe")


def verify_stripe_signature(
    payload_bytes: bytes, sig_header: str | None, webhook_secret: str, tolerance: int = 300
) -> bool:
    if not sig_header or not webhook_secret:
        return False
    parts = {}
    for item in sig_header.split(","):
        if "=" in item:
            k, v = item.strip().split("=", 1)
            parts[k] = v

    timestamp = parts.get("t")
    signature = parts.get("v1")
    if not timestamp or not signature:
        return False

    try:
        t = int(timestamp)
        if abs(time.time() - t) > tolerance:
            return False
    except ValueError:
        return False

    signed_payload = f"{timestamp}.".encode("utf-8") + payload_bytes
    expected_sig = hmac.new(
        webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_sig, signature)


async def create_checkout_session(
    db: AsyncSession,
    org: Organization,
    tier: str,
    settings: Settings,
    return_url: str | None = None,
) -> dict[str, str]:
    tier = tier.lower()
    if tier not in ("starter", "pro", "agency"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan tier: '{tier}'. Must be starter, pro, or agency.",
        )

    base_return_url = return_url or f"{settings.app_frontend_url}/billing"

    # Simulation mode if no secret key configured
    if not settings.stripe_secret_key:
        return {
            "url": f"{base_return_url}?simulated_checkout=success&tier={tier}&org_id={org.id}",
            "mode": "simulation",
        }

    # Real Stripe checkout
    import httpx

    price_map = {
        "starter": settings.stripe_price_starter,
        "pro": settings.stripe_price_pro,
        "agency": settings.stripe_price_agency,
    }
    price_id = price_map[tier]

    headers = {
        "Authorization": f"Bearer {settings.stripe_secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "mode": "subscription",
        "payment_method_types[0]": "card",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "client_reference_id": str(org.id),
        "customer_email": org.billing_email or "",
        "success_url": f"{base_return_url}?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base_return_url}?canceled=true",
        "metadata[org_id]": str(org.id),
        "metadata[tier]": tier,
    }
    if org.stripe_customer_id:
        data["customer"] = org.stripe_customer_id
        data.pop("customer_email", None)

    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post("https://api.stripe.com/v1/checkout/sessions", headers=headers, data=data)
        if res.status_code != 200:
            logger.error("Stripe Checkout creation failed: %s", res.text)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not create Stripe checkout session",
            )
        session_data = res.json()
        return {"url": session_data["url"], "mode": "live"}


async def create_customer_portal_session(
    db: AsyncSession,
    org: Organization,
    settings: Settings,
    return_url: str | None = None,
) -> dict[str, str]:
    base_return_url = return_url or f"{settings.app_frontend_url}/billing"

    if not settings.stripe_secret_key:
        return {
            "url": f"{base_return_url}?simulated_portal=true&org_id={org.id}",
            "mode": "simulation",
        }

    if not org.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization has no Stripe customer record.",
        )

    import httpx

    headers = {
        "Authorization": f"Bearer {settings.stripe_secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "customer": org.stripe_customer_id,
        "return_url": base_return_url,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post("https://api.stripe.com/v1/billing_portal/sessions", headers=headers, data=data)
        if res.status_code != 200:
            logger.error("Stripe Portal creation failed: %s", res.text)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not create Stripe billing portal session",
            )
        session_data = res.json()
        return {"url": session_data["url"], "mode": "live"}


async def handle_stripe_webhook(
    db: AsyncSession,
    payload_bytes: bytes,
    sig_header: str | None,
    settings: Settings,
) -> dict[str, Any]:
    # 1. Verify signature if webhook secret is configured
    if settings.stripe_webhook_secret:
        if not verify_stripe_signature(payload_bytes, sig_header, settings.stripe_webhook_secret):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Stripe signature.",
            )

    try:
        event = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON body.",
        )

    event_id = event.get("id")
    event_type = event.get("type")
    if not event_id or not event_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing event ID or type.",
        )

    # 2. Idempotency check via billing_events
    existing = await db.scalar(
        select(BillingEvent).where(BillingEvent.stripe_event_id == event_id)
    )
    if existing:
        return {"status": "already_processed", "event_id": event_id}

    # Record event
    db.add(
        BillingEvent(
            stripe_event_id=event_id,
            event_type=event_type,
            payload=json.dumps(event),
        )
    )
    await db.flush()

    data_obj = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        org_id_str = data_obj.get("client_reference_id") or data_obj.get("metadata", {}).get("org_id")
        tier = data_obj.get("metadata", {}).get("tier", "pro")
        customer_id = data_obj.get("customer")
        subscription_id = data_obj.get("subscription")

        if org_id_str:
            try:
                org_id = uuid.UUID(org_id_str)
                org = await db.get(Organization, org_id)
                if org:
                    org.plan_tier = tier
                    org.subscription_status = "active"
                    if customer_id:
                        org.stripe_customer_id = str(customer_id)
                    if subscription_id:
                        org.stripe_subscription_id = str(subscription_id)
                    await db.commit()
            except Exception as e:
                logger.error("Error processing checkout.session.completed: %s", e)

    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub_id = data_obj.get("id")
        customer_id = data_obj.get("customer")
        sub_status = data_obj.get("status", "active")
        period_start = data_obj.get("current_period_start")
        period_end = data_obj.get("current_period_end")

        stmt = select(Organization).where(
            (Organization.stripe_subscription_id == sub_id)
            | (Organization.stripe_customer_id == customer_id)
        )
        org = await db.scalar(stmt)
        if org:
            org.subscription_status = sub_status
            if event_type == "customer.subscription.deleted" or sub_status == "canceled":
                org.plan_tier = "free"
            if period_start and period_end:
                org.current_period_start = datetime.fromtimestamp(period_start, tz=timezone.utc)
                org.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
            await db.commit()

    return {"status": "success", "event_type": event_type}
