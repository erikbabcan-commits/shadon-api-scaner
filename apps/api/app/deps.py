from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.db import get_db
from app.models import ApiKey, Organization, OrganizationMember, OrgRole, User
from app.security import read_session_token
from app.services.organizations import ensure_user_has_org


@dataclass
class OrgContext:
    organization: Organization
    membership: OrganizationMember
    user: User
    api_key: ApiKey | None = None

    @property
    def org_id(self) -> uuid.UUID:
        return self.organization.id

    @property
    def role(self) -> OrgRole:
        return self.membership.role


ROLE_HIERARCHY = {
    OrgRole.viewer: 1,
    OrgRole.member: 2,
    OrgRole.admin: 3,
    OrgRole.owner: 4,
}


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    cookie_name = (
        f"__Host-{settings.straz_cookie_name}"
        if settings.straz_cookie_secure
        else settings.straz_cookie_name
    )
    token = request.cookies.get(cookie_name) or request.cookies.get(settings.straz_cookie_name)
    if not token:
        auth_hdr = request.headers.get("authorization")
        if auth_hdr and auth_hdr.lower().startswith("bearer "):
            token = auth_hdr[7:].strip()
        elif not token and request.headers.get("x-api-key"):
            token = request.headers.get("x-api-key", "").strip()

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    # 1. Bearer API key authentication
    if token.startswith("straz_live_"):
        key_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        stmt = (
            select(ApiKey)
            .options(selectinload(ApiKey.organization), selectinload(ApiKey.user))
            .where(ApiKey.key_hash == key_hash)
        )
        api_key = await db.scalar(stmt)
        if not api_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

        now = datetime.now(timezone.utc)
        if api_key.expires_at and api_key.expires_at < now:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key expired")

        if api_key.organization.plan_tier == "free":
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="API kľúče nie sú dostupné pre bezplatný plán. Vyžaduje sa upgrade na Starter alebo vyšší.",
            )

        api_key.last_used_at = now
        await db.commit()

        request.state.api_key = api_key
        return api_key.user

    # 2. Session cookie / JWT authentication
    token_data = read_session_token(settings, token)
    if not token_data or "uid" not in token_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    try:
        uid = uuid.UUID(token_data["uid"])
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc

    user = await db.scalar(select(User).where(User.id == uid))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if user.token_version != token_data.get("ver", 1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked")

    return user


async def get_current_org(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgContext:
    api_key: ApiKey | None = getattr(request.state, "api_key", None)
    if api_key:
        org_header = request.headers.get("x-organization-id")
        if org_header:
            try:
                target_org_id = uuid.UUID(org_header.strip())
                if target_org_id != api_key.organization_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="API key is not valid for the requested organization",
                    )
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid X-Organization-Id header format",
                )

        stmt = (
            select(OrganizationMember)
            .options(selectinload(OrganizationMember.organization))
            .where(
                OrganizationMember.user_id == api_key.user_id,
                OrganizationMember.org_id == api_key.organization_id,
            )
        )
        membership = await db.scalar(stmt)
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key creator is no longer a member of this organization",
            )
        return OrgContext(
            organization=membership.organization,
            membership=membership,
            user=user,
            api_key=api_key,
        )

    org_header = request.headers.get("x-organization-id")
    if org_header:
        try:
            target_org_id = uuid.UUID(org_header.strip())
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Organization-Id header format",
            )
        stmt = (
            select(OrganizationMember)
            .options(selectinload(OrganizationMember.organization))
            .where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.org_id == target_org_id,
            )
        )
        membership = await db.scalar(stmt)
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of the requested organization",
            )
        return OrgContext(
            organization=membership.organization,
            membership=membership,
            user=user,
        )

    # If no header provided, find earliest or bootstrap default org
    org, membership = await ensure_user_has_org(db, user)
    return OrgContext(
        organization=org,
        membership=membership,
        user=user,
    )


def require_org_role(min_role: OrgRole):
    async def role_checker(
        org_context: OrgContext = Depends(get_current_org),
    ) -> OrgContext:
        user_level = ROLE_HIERARCHY.get(org_context.role, 0)
        required_level = ROLE_HIERARCHY.get(min_role, 0)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action requires at least '{min_role.value}' role in organization",
            )
        return org_context

    return role_checker


def require_scope(scope: str):
    async def scope_checker(
        org_context: OrgContext = Depends(get_current_org),
    ) -> OrgContext:
        if org_context.api_key:
            scopes = org_context.api_key.scopes or []
            if scope not in scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Nedostatočné oprávnenia API kľúča",
                )
        return org_context

    return scope_checker

