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
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import BillingEvent, Organization

logger = logging.getLogger("straz.stripe")


def verify_stripe_signature(
    payload_bytes: bytes, sig_header: str | None, webhook_secret: str, tolerance: int = 300
) -> bool:
    if not sig_header or not webhook_secret:
        return False
    parts: dict[str, list[str]] = {}
    for item in sig_header.split(","):
        if "=" in item:
            k, v = item.strip().split("=", 1)
            parts.setdefault(k, []).append(v)

    timestamps = parts.get("t", [])
    signatures = parts.get("v1", [])
    if len(timestamps) != 1 or not signatures:
        return False

    timestamp = timestamps[0]
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
    return any(hmac.compare_digest(expected_sig, signature) for signature in signatures)


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

    base_return_url = billing_return_url(return_url, settings)
    if org.stripe_subscription_id and org.subscription_status in {"active", "trialing"}:
        raise HTTPException(status_code=409, detail="Manage the current subscription in the customer portal")

    # Simulation mode if no secret key configured
    if not settings.stripe_secret_key:
        if settings.is_production:
            raise HTTPException(status_code=503, detail="Stripe billing is not configured")
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
        "subscription_data[metadata][org_id]": str(org.id),
    }
    if org.stripe_customer_id:
        data["customer"] = org.stripe_customer_id
        data.pop("customer_email", None)

    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.post("https://api.stripe.com/v1/checkout/sessions", headers=headers, data=data)
        if res.status_code != 200:
            logger.error("Stripe Checkout creation failed (status=%s)", res.status_code)
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
    base_return_url = billing_return_url(return_url, settings)

    if not settings.stripe_secret_key:
        if settings.is_production:
            raise HTTPException(status_code=503, detail="Stripe billing is not configured")
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
            logger.error("Stripe Portal creation failed (status=%s)", res.status_code)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not create Stripe billing portal session",
            )
        session_data = res.json()
        return {"url": session_data["url"], "mode": "live"}


def billing_return_url(value: str | None, settings: Settings) -> str:
    from urllib.parse import urlsplit
    configured = urlsplit(settings.app_frontend_url)
    destination = urlsplit(value or f"{settings.app_frontend_url.rstrip('/')}/billing")
    if (destination.scheme, destination.hostname, destination.port) != (configured.scheme, configured.hostname, configured.port) or destination.username or destination.password:
        raise HTTPException(status_code=400, detail="Invalid billing return origin")
    return destination.geturl()


async def _current_subscription(subscription_id: str, settings: Settings) -> dict[str, Any]:
    import httpx
    if not subscription_id.startswith("sub_") or not all(c.isalnum() or c == "_" for c in subscription_id):
        raise HTTPException(status_code=400, detail="Invalid subscription identifier")
    async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False) as client:
        response = await client.get(
            f"https://api.stripe.com/v1/subscriptions/{subscription_id}",
            headers={"Authorization": f"Bearer {settings.stripe_secret_key}"},
        )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Subscription reconciliation unavailable")
    return response.json()


async def handle_stripe_webhook(
    db: AsyncSession,
    payload_bytes: bytes,
    sig_header: str | None,
    settings: Settings,
) -> dict[str, Any]:
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Stripe webhook is not configured")
    if not verify_stripe_signature(payload_bytes, sig_header, settings.stripe_webhook_secret):
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    try:
        event = json.loads(payload_bytes)
        event_id, event_type = event["id"], event["type"]
        data = event["data"]["object"]
        if not isinstance(event_id, str) or not 1 <= len(event_id) <= 255 or not isinstance(event_type, str) or len(event_type) > 100 or not isinstance(data, dict):
            raise ValueError
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise HTTPException(status_code=400, detail="Malformed Stripe event") from None

    # Unique event admission and all business effects share the caller's transaction.
    # No raw payment payload, addresses, emails or secrets are retained.
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    admitted = await db.scalar(insert(BillingEvent).values(
        id=uuid.uuid4(), stripe_event_id=event_id, event_type=event_type,
        payload=None,
    ).on_conflict_do_nothing(index_elements=["stripe_event_id"]).returning(BillingEvent.id))
    if admitted is None:
        return {"status": "already_processed"}

    checkout = event_type == "checkout.session.completed"
    supported = {"customer.subscription.updated", "customer.subscription.deleted", "invoice.payment_failed", "invoice.paid"}
    org = None
    if checkout:
        try:
            oid = uuid.UUID(data.get("client_reference_id") or data.get("metadata", {}).get("org_id", ""))
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid checkout organization") from None
        org = await db.scalar(select(Organization).where(Organization.id == oid).with_for_update().execution_options(populate_existing=True))
        sub_id = data.get("subscription")
    elif event_type in supported:
        sub_id = data.get("id") if event_type.startswith("customer.subscription.") else (
            data.get("subscription") or data.get("parent", {}).get("subscription_details", {}).get("subscription")
        )
        if sub_id:
            org = await db.scalar(select(Organization).where(Organization.stripe_subscription_id == sub_id).with_for_update().execution_options(populate_existing=True))
    else:
        return {"status": "ignored"}
    if org is None or not sub_id:
        return {"status": "ignored"}
    if checkout and org.stripe_subscription_id and org.stripe_subscription_id != sub_id and org.subscription_status in {"active", "trialing"}:
        return {"status": "ignored"}
    customer = data.get("customer")
    if not customer or (org.stripe_customer_id and org.stripe_customer_id != customer):
        raise HTTPException(status_code=400, detail="Stripe customer mismatch")

    if settings.stripe_secret_key:
        # Stripe delivers out of order. Reconcile the current resource under the
        # org lock instead of trusting event timestamps or stale snapshots.
        subscription = await _current_subscription(str(sub_id), settings)
        if subscription.get("customer") != customer:
            raise HTTPException(status_code=400, detail="Subscription customer mismatch")
        prices = {settings.stripe_price_starter: "starter", settings.stripe_price_pro: "pro", settings.stripe_price_agency: "agency"}
        items = subscription.get("items", {}).get("data", [])
        tier = prices.get(items[0].get("price", {}).get("id")) if items else None
        sub_status = subscription.get("status", "incomplete")
        period = items[0] if items and items[0].get("current_period_end") else subscription
    else:
        # Signed local simulation only; never promote a production org via mock data.
        if settings.is_production:
            raise HTTPException(status_code=503, detail="Stripe reconciliation is not configured")
        if checkout and (data.get("mode") != "subscription" or data.get("payment_status") not in {"paid", "no_payment_required"}):
            return {"status": "ignored"}
        tier = data.get("metadata", {}).get("tier") if checkout else org.plan_tier
        sub_status = "active" if checkout else data.get("status", org.subscription_status)
        if event_type == "customer.subscription.deleted":
            sub_status = "canceled"
        if event_type == "invoice.payment_failed":
            sub_status = "past_due"
        period = data
    if tier not in {"free", "starter", "pro", "agency"}:
        raise HTTPException(status_code=400, detail="Unknown subscription plan")
    org.stripe_customer_id = str(customer)
    org.stripe_subscription_id = str(sub_id)
    org.subscription_status = str(sub_status)
    org.plan_tier = tier if sub_status in {"active", "trialing"} else "free"
    for attr in ("current_period_start", "current_period_end"):
        value = period.get(attr)
        if isinstance(value, (int, float)):
            setattr(org, attr, datetime.fromtimestamp(value, tz=timezone.utc))
    from app.services.audit import write_audit_log
    await write_audit_log(db, org_id=org.id, action="billing.webhook", entity_type="organization", entity_id=str(org.id), details={"event_type": event_type, "plan": org.plan_tier, "status": org.subscription_status})
    await db.flush()
    return {"status": "success", "event_type": event_type}
