from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import OrgContext, require_org_role
from app.models import OrgRole
from app.services.audit import write_audit
from app.services.quota import PLANS, get_org_usage_stats
from app.services.stripe import (
    create_checkout_session,
    create_customer_portal_session,
    handle_stripe_webhook,
)

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    tier: str
    return_url: str | None = None


class PortalRequest(BaseModel):
    return_url: str | None = None


@router.get("/plans")
async def list_plans() -> dict[str, Any]:
    return {"plans": PLANS}


@router.get("/usage")
async def get_usage(
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.viewer)),
) -> dict[str, Any]:
    return await get_org_usage_stats(db, org_ctx.organization)


@router.post("/create-checkout-session")
async def checkout(
    body: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    session = await create_checkout_session(
        db,
        org=org_ctx.organization,
        tier=body.tier,
        settings=settings,
        return_url=body.return_url,
    )
    await write_audit(
        db,
        action="billing.checkout_created",
        user_id=org_ctx.user.id,
        entity_type="organization",
        entity_id=str(org_ctx.org_id),
        detail=f"Created checkout session for plan {body.tier}",
    )
    return session


@router.post("/customer-portal")
async def customer_portal(
    body: PortalRequest,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    session = await create_customer_portal_session(
        db,
        org=org_ctx.organization,
        settings=settings,
        return_url=body.return_url,
    )
    await write_audit(
        db,
        action="billing.portal_created",
        user_id=org_ctx.user.id,
        entity_type="organization",
        entity_id=str(org_ctx.org_id),
        detail="Opened customer billing portal",
    )
    return session


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    body_bytes = await request.body()
    return await handle_stripe_webhook(db, body_bytes, stripe_signature, settings)
