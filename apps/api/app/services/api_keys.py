from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApiKey, Organization, User


def generate_raw_api_key() -> tuple[str, str, str]:
    """
    Generates a secure API key with prefix 'straz_live_' followed by 32 random urlsafe chars.
    Returns:
        (raw_token, key_prefix, key_hash)
    """
    random_part = secrets.token_urlsafe(24)[:32]
    raw_token = f"straz_live_{random_part}"
    key_prefix = raw_token[:16]
    key_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return raw_token, key_prefix, key_hash


async def create_api_key(
    db: AsyncSession,
    org: Organization,
    user: User,
    name: str,
    scopes: list[str] | None = None,
    expires_at: datetime | None = None,
) -> tuple[ApiKey, str]:
    """
    Creates an API key row and returns the model instance plus the plaintext raw key.
    Raw key is only available at creation time.
    """
    raw_token, key_prefix, key_hash = generate_raw_api_key()
    valid_scopes = ["ci:scan", "apps:read"] if scopes is None else scopes
    if not set(valid_scopes).issubset({"ci:scan", "apps:read", "findings:read", "reports:read"}):
        raise HTTPException(status_code=422, detail="Unknown API key scope")
    if expires_at:
        expires_at = expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at
        if expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=422, detail="API key expiry must be in the future")

    api_key = ApiKey(
        id=uuid.uuid4(),
        organization_id=org.id,
        user_id=user.id,
        name=name.strip(),
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=valid_scopes,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.flush()
    await db.refresh(api_key)
    return api_key, raw_token


async def list_org_api_keys(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> list[ApiKey]:
    stmt = (
        select(ApiKey)
        .where(ApiKey.organization_id == org_id)
        .order_by(ApiKey.created_at.desc())
    )
    res = await db.scalars(stmt)
    return list(res.all())


async def revoke_api_key(
    db: AsyncSession,
    org_id: uuid.UUID,
    key_id: uuid.UUID,
) -> bool:
    stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.organization_id == org_id)
    key = await db.scalar(stmt)
    if not key:
        return False
    await db.delete(key)
    await db.flush()
    return True
