from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import OrgContext, get_current_org, get_current_user, require_org_role
from app.models import OrgRole, User
from app.services import organizations as org_service
from app.services.audit import write_audit

router = APIRouter(tags=["organizations"])


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str | None = Field(default=None, max_length=100)


class InvitationCreateRequest(BaseModel):
    email: EmailStr
    role: OrgRole = OrgRole.member


class RoleUpdateRequest(BaseModel):
    role: OrgRole


@router.get("/orgs")
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return await org_service.get_user_organizations(db, user.id)


@router.post("/orgs", status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: OrganizationCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    org = await org_service.create_organization(
        db, user_id=user.id, name=body.name, slug=body.slug
    )
    await write_audit(
        db,
        action="org.create",
        user_id=user.id,
        entity_type="organization",
        entity_id=str(org.id),
        detail=org.name,
    )
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "role": OrgRole.owner,
        "created_at": org.created_at,
    }


@router.get("/orgs/{org_id}/members")
async def list_members(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.viewer)),
) -> list[dict[str, Any]]:
    if org_ctx.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access members of another organization",
        )
    return await org_service.get_organization_members(db, org_id)


@router.post("/orgs/{org_id}/invitations", status_code=status.HTTP_201_CREATED)
async def invite_member(
    org_id: uuid.UUID,
    body: InvitationCreateRequest,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
) -> dict[str, Any]:
    if org_ctx.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot invite members to another organization",
        )
    invitation = await org_service.create_invitation(
        db,
        org_id=org_id,
        actor_role=org_ctx.role,
        email=body.email,
        role=body.role,
    )
    await write_audit(
        db,
        action="member.invite",
        user_id=org_ctx.user.id,
        entity_type="organization_invitation",
        entity_id=str(invitation.id),
        detail=f"Invited {body.email} as {body.role.value}",
    )
    return {
        "id": invitation.id,
        "org_id": invitation.org_id,
        "email": invitation.email,
        "role": invitation.role,
        "token": invitation.token,
        "expires_at": invitation.expires_at,
        "created_at": invitation.created_at,
    }


@router.delete("/orgs/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
) -> None:
    if org_ctx.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot remove members from another organization",
        )
    await org_service.remove_member(
        db,
        org_id=org_id,
        actor_role=org_ctx.role,
        user_id_to_remove=user_id,
    )
    await write_audit(
        db,
        action="member.remove",
        user_id=org_ctx.user.id,
        entity_type="user",
        entity_id=str(user_id),
        detail=f"Removed member {user_id}",
    )


@router.patch("/orgs/{org_id}/members/{user_id}")
async def update_member_role(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: RoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
) -> dict[str, Any]:
    if org_ctx.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify members of another organization",
        )
    member = await org_service.update_member_role(
        db,
        org_id=org_id,
        actor_role=org_ctx.role,
        user_id_to_update=user_id,
        new_role=body.role,
    )
    await write_audit(
        db,
        action="member.role_change",
        user_id=org_ctx.user.id,
        entity_type="user",
        entity_id=str(user_id),
        detail=f"Changed role to {body.role.value}",
    )
    return {
        "id": member.id,
        "user_id": member.user_id,
        "role": member.role,
    }


@router.post("/invitations/{token}/accept")
async def accept_invitation(
    token: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    member = await org_service.accept_invitation(db, user, token)
    await write_audit(
        db,
        action="member.accept_invitation",
        user_id=user.id,
        entity_type="organization",
        entity_id=str(member.org_id),
        detail=f"Joined organization with role {member.role.value}",
    )
    return {
        "status": "accepted",
        "org_id": member.org_id,
        "role": member.role,
    }
