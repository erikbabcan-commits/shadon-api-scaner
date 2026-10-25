from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    App,
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    OrgRole,
    User,
)


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "-", cleaned) or "org"


async def get_user_organizations(
    db: AsyncSession, user_id: uuid.UUID
) -> list[dict]:
    stmt = (
        select(OrganizationMember)
        .options(selectinload(OrganizationMember.organization))
        .where(OrganizationMember.user_id == user_id)
        .order_by(OrganizationMember.created_at.asc())
    )
    memberships = list(await db.scalars(stmt))
    result = []
    for m in memberships:
        org = m.organization
        result.append(
            {
                "id": org.id,
                "name": org.name,
                "slug": org.slug,
                "role": m.role,
                "billing_email": org.billing_email,
                "plan_tier": org.plan_tier,
                "created_at": org.created_at,
            }
        )
    return result


async def create_organization(
    db: AsyncSession, user_id: uuid.UUID, name: str, slug: str | None = None
) -> Organization:
    base_slug = slugify(slug or name)
    candidate_slug = base_slug
    suffix = 1
    while True:
        existing = await db.scalar(
            select(Organization).where(Organization.slug == candidate_slug)
        )
        if not existing:
            break
        candidate_slug = f"{base_slug}-{suffix}"
        suffix += 1

    org = Organization(
        id=uuid.uuid4(),
        name=name.strip(),
        slug=candidate_slug,
    )
    db.add(org)
    await db.flush()

    member = OrganizationMember(
        id=uuid.uuid4(),
        org_id=org.id,
        user_id=user_id,
        role=OrgRole.owner,
    )
    db.add(member)
    await db.flush()
    return org


async def ensure_user_has_org(db: AsyncSession, user: User) -> tuple[Organization, OrganizationMember]:
    stmt = (
        select(OrganizationMember)
        .options(selectinload(OrganizationMember.organization))
        .where(OrganizationMember.user_id == user.id)
        .order_by(OrganizationMember.created_at.asc())
    )
    membership = await db.scalar(stmt)
    if membership:
        return membership.organization, membership

    # Bootstrap default organization
    name = f"{user.email.split('@')[0]}'s Workspace"
    org = await create_organization(db, user.id, name=name)
    stmt = select(OrganizationMember).where(
        OrganizationMember.org_id == org.id, OrganizationMember.user_id == user.id
    )
    membership = await db.scalar(stmt)
    return org, membership


async def get_organization_members(
    db: AsyncSession, org_id: uuid.UUID
) -> list[dict]:
    stmt = (
        select(OrganizationMember)
        .options(selectinload(OrganizationMember.user))
        .where(OrganizationMember.org_id == org_id)
        .order_by(OrganizationMember.created_at.asc())
    )
    members = list(await db.scalars(stmt))
    return [
        {
            "id": m.id,
            "user_id": m.user_id,
            "email": m.user.email if m.user else "deleted-user",
            "role": m.role,
            "created_at": m.created_at,
        }
        for m in members
    ]


async def create_invitation(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor_role: OrgRole,
    email: str,
    role: OrgRole,
) -> OrganizationInvitation:
    normalized_email = email.strip().lower()

    if role == OrgRole.owner:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot invite an owner. Transfer ownership instead.",
        )
    if role == OrgRole.admin and actor_role != OrgRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can invite administrators.",
        )

    # Check if already a member
    member_stmt = (
        select(OrganizationMember)
        .join(User, OrganizationMember.user_id == User.id)
        .where(OrganizationMember.org_id == org_id, User.email == normalized_email)
    )
    if await db.scalar(member_stmt):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this organization.",
        )

    # Invalidate old invitations for same email & org
    old_stmt = select(OrganizationInvitation).where(
        OrganizationInvitation.org_id == org_id,
        OrganizationInvitation.email == normalized_email,
    )
    old_invites = list(await db.scalars(old_stmt))
    for oi in old_invites:
        await db.delete(oi)

    token = secrets.token_urlsafe(32)
    invitation = OrganizationInvitation(
        id=uuid.uuid4(),
        org_id=org_id,
        email=normalized_email,
        role=role,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invitation)
    await db.flush()
    return invitation


async def accept_invitation(
    db: AsyncSession, user: User, token: str
) -> OrganizationMember:
    stmt = (
        select(OrganizationInvitation)
        .options(selectinload(OrganizationInvitation.organization))
        .where(OrganizationInvitation.token == token)
    )
    invitation = await db.scalar(stmt)
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or invalid token.",
        )

    now = datetime.now(timezone.utc)
    # Handle both naive and aware datetimes
    exp = invitation.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now:
        await db.delete(invitation)
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Invitation has expired.",
        )

    if user.email.strip().lower() != invitation.email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This invitation was sent to {invitation.email}, but you are logged in as {user.email}.",
        )

    # Check if already member
    existing_stmt = select(OrganizationMember).where(
        OrganizationMember.org_id == invitation.org_id,
        OrganizationMember.user_id == user.id,
    )
    existing_member = await db.scalar(existing_stmt)
    if existing_member:
        await db.delete(invitation)
        await db.flush()
        return existing_member

    member = OrganizationMember(
        id=uuid.uuid4(),
        org_id=invitation.org_id,
        user_id=user.id,
        role=invitation.role,
    )
    db.add(member)
    await db.delete(invitation)
    await db.flush()
    return member


async def remove_member(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor_role: OrgRole,
    user_id_to_remove: uuid.UUID,
) -> None:
    stmt = select(OrganizationMember).where(
        OrganizationMember.org_id == org_id,
        OrganizationMember.user_id == user_id_to_remove,
    )
    member = await db.scalar(stmt)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found in organization.",
        )

    if member.role == OrgRole.owner:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the owner of an organization.",
        )

    if member.role == OrgRole.admin and actor_role != OrgRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can remove administrators.",
        )

    await db.delete(member)
    await db.flush()


async def update_member_role(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor_role: OrgRole,
    user_id_to_update: uuid.UUID,
    new_role: OrgRole,
) -> OrganizationMember:
    stmt = select(OrganizationMember).where(
        OrganizationMember.org_id == org_id,
        OrganizationMember.user_id == user_id_to_update,
    )
    member = await db.scalar(stmt)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found.",
        )

    if member.role == OrgRole.owner:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change role of organization owner.",
        )

    if (member.role == OrgRole.admin or new_role == OrgRole.admin) and actor_role != OrgRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can promote or demote administrators.",
        )

    member.role = new_role
    await db.flush()
    return member
