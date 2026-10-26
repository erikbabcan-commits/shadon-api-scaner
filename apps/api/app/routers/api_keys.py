from __future__ import annotations

from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import OrgContext, require_org_role
from app.models import OrgRole
from app.services.api_keys import create_api_key, list_org_api_keys, revoke_api_key
from app.services.audit import write_audit
from app.services.quota import check_api_key_limit

router = APIRouter(prefix="/api/orgs/{org_id}/api-keys", tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=lambda: ["ci:scan", "apps:read"])
    expires_at: datetime | None = None


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime


class ApiKeyCreatedResponse(ApiKeyOut):
    raw_key: str
    warning: str = "Tento API kľúč sa zobrazuje iba raz. Bezpečne si ho uložte!"


@router.get("", response_model=list[ApiKeyOut])
async def list_keys(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
) -> list[ApiKeyOut]:
    if org_ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="Organization access mismatch")
    keys = await list_org_api_keys(db, org_id)
    return [
        ApiKeyOut(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            scopes=k.scopes or [],
            expires_at=k.expires_at,
            last_used_at=k.last_used_at,
            created_at=k.created_at,
        )
        for k in keys
    ]


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_key(
    org_id: uuid.UUID,
    body: ApiKeyCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
) -> ApiKeyCreatedResponse:
    if org_ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="Organization access mismatch")

    allowed, reason = await check_api_key_limit(db, org_ctx.organization)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=reason,
            headers={"X-Upgrade-Required": "true"},
        )

    response.headers["Cache-Control"] = "no-store"
    api_key, raw_token = await create_api_key(
        db=db,
        org=org_ctx.organization,
        user=org_ctx.user,
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
    )

    await write_audit(
        db,
        action="apikey.create",
        user_id=org_ctx.user.id,
        entity_type="api_key",
        entity_id=str(api_key.id),
        detail=f"name={api_key.name}, prefix={api_key.key_prefix}",
    )
    await db.commit()

    return ApiKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes or [],
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        raw_key=raw_token,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(
    org_id: uuid.UUID,
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
) -> Response:
    if org_ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="Organization access mismatch")

    success = await revoke_api_key(db, org_id, key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    await write_audit(
        db,
        action="apikey.revoke",
        user_id=org_ctx.user.id,
        entity_type="api_key",
        entity_id=str(key_id),
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
