from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import OrgContext, require_org_role
from app.models import AlertChannel, App, OrgRole
from app.services.audit import write_audit
from app.services.notifications import test_channel_delivery
from app.services.notifications.channels import (
    check_channel_limit,
    list_org_channels,
    validate_channel_for_plan,
)
from app.services.notifications.transport import validate_destination_url

router = APIRouter(tags=["integrations"])


class ChannelCreateRequest(BaseModel):
    app_id: uuid.UUID | None = None
    platform: str
    name: str = Field(min_length=1, max_length=100)
    destination_url: str = Field(min_length=1, max_length=500)
    secret_token: str | None = None
    min_severity: str = "high"
    events: list[str] = ["finding.created", "app.down"]
    is_active: bool = True


class ChannelUpdateRequest(BaseModel):
    name: str | None = None
    destination_url: str | None = None
    secret_token: str | None = None
    min_severity: str | None = None
    events: list[str] | None = None
    is_active: bool | None = None


@router.get("/orgs/{org_id}/channels")
async def list_channels(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.viewer)),
) -> list[dict[str, Any]]:
    if org_ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot access channels of another organization")
    return await list_org_channels(db, org_id)


@router.post("/orgs/{org_id}/channels", status_code=status.HTTP_201_CREATED)
async def create_channel(
    org_id: uuid.UUID,
    body: ChannelCreateRequest,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if org_ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot create channels for another organization")

    # 1. Quota check: plan limit and allowed platforms
    validate_channel_for_plan(org_ctx.organization, body.platform, bool(body.secret_token))
    await check_channel_limit(db, org_ctx.organization)

    # 2. SSRF check on destination URL
    is_test_env = settings.straz_env in ("test", "testing", "development")
    try:
        validate_destination_url(body.destination_url, is_test_env)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 3. If app_id specified, check it belongs to org
    if body.app_id:
        app = await db.scalar(
            select(App).where(App.id == body.app_id, App.organization_id == org_id)
        )
        if not app:
            raise HTTPException(status_code=404, detail="Specified application not found in organization")

    channel = AlertChannel(
        id=uuid.uuid4(),
        org_id=org_id,
        app_id=body.app_id,
        platform=body.platform.lower(),
        name=body.name.strip(),
        destination_url=body.destination_url.strip(),
        secret_token=body.secret_token.strip() if body.secret_token else None,
        min_severity=body.min_severity.lower(),
        events=json.dumps(body.events),
        is_active=body.is_active,
    )
    db.add(channel)
    await write_audit(
        db,
        action="channel.create",
        user_id=org_ctx.user.id,
        entity_type="alert_channel",
        entity_id=str(channel.id),
        detail=f"Created {body.platform} channel '{body.name}'",
    )
    await db.commit()
    await db.refresh(channel)

    return {
        "id": channel.id,
        "platform": channel.platform,
        "name": channel.name,
        "is_active": channel.is_active,
    }


@router.patch("/orgs/{org_id}/channels/{channel_id}")
async def update_channel(
    org_id: uuid.UUID,
    channel_id: uuid.UUID,
    body: ChannelUpdateRequest,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if org_ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot modify channels of another organization")
    channel = await db.scalar(
        select(AlertChannel).where(AlertChannel.id == channel_id, AlertChannel.org_id == org_id)
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    is_test_env = settings.straz_env in ("test", "testing", "development")
    if body.destination_url is not None:
        try:
            validate_destination_url(body.destination_url, is_test_env)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        channel.destination_url = body.destination_url.strip()

    if body.name is not None:
        channel.name = body.name.strip()
    if body.secret_token is not None:
        channel.secret_token = body.secret_token.strip() if body.secret_token else None
    if body.min_severity is not None:
        channel.min_severity = body.min_severity.lower()
    if body.events is not None:
        channel.events = json.dumps(body.events)
    if body.is_active is not None:
        channel.is_active = body.is_active

    await write_audit(
        db,
        action="channel.update",
        user_id=org_ctx.user.id,
        entity_type="alert_channel",
        entity_id=str(channel.id),
        detail=f"Updated channel '{channel.name}'",
    )
    await db.commit()
    return {"id": channel.id, "is_active": channel.is_active}


@router.delete("/orgs/{org_id}/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    org_id: uuid.UUID,
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
) -> None:
    if org_ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot delete channels of another organization")
    channel = await db.scalar(
        select(AlertChannel).where(AlertChannel.id == channel_id, AlertChannel.org_id == org_id)
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    await write_audit(
        db,
        action="channel.delete",
        user_id=org_ctx.user.id,
        entity_type="alert_channel",
        entity_id=str(channel.id),
        detail=channel.name,
    )
    await db.delete(channel)
    await db.commit()


@router.post("/orgs/{org_id}/channels/{channel_id}/test")
async def test_channel(
    org_id: uuid.UUID,
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if org_ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot test channels of another organization")
    channel = await db.scalar(
        select(AlertChannel).where(AlertChannel.id == channel_id, AlertChannel.org_id == org_id)
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    delivered = await test_channel_delivery(channel, settings)
    await write_audit(
        db,
        action="channel.test",
        user_id=org_ctx.user.id,
        entity_type="alert_channel",
        entity_id=str(channel.id),
        detail=f"Test delivery status: {delivered}",
    )
    return {"status": "ok" if delivered else "delivery_failed", "delivered": delivered}
