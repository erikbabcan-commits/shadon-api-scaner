from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import OrgContext, require_org_role
from app.models import AuditEvent, OrganizationMember, OrgRole
from app.services.audit import write_audit_log

router = APIRouter(prefix="/api/orgs/{org_id}", tags=["audit"])


class AuditEventOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID | None
    user_id: uuid.UUID | None
    actor_email: str
    action: str
    entity_type: str | None
    entity_id: str | None
    ip_address: str | None
    user_agent: str | None
    detail: str | None
    details: dict[str, Any] | None
    created_at: datetime


class AuditLogResponse(BaseModel):
    total: int
    items: list[AuditEventOut]
    limit: int
    offset: int


class RoleUpdatePayload(BaseModel):
    role: OrgRole


def sanitize_csv_cell(val: Any) -> str:
    """
    Prevents CSV / Formula Injection attacks in Microsoft Excel / Google Sheets.
    If a string starts with =, +, -, @, prepend a single quote '.
    """
    if val is None:
        return ""
    text_val = str(val)
    if text_val and text_val[0] in ("=", "+", "-", "@"):
        return f"'{text_val}"
    return text_val


@router.get("/audit-logs", response_model=AuditLogResponse)
async def list_audit_logs(
    org_id: uuid.UUID,
    action: str | None = None,
    actor_email: str | None = None,
    entity_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
) -> AuditLogResponse:
    if org_ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="Organization access mismatch")

    query = select(AuditEvent).where(AuditEvent.organization_id == org_id)

    if action:
        query = query.where(AuditEvent.action == action)
    if actor_email:
        query = query.where(AuditEvent.actor_email.ilike(f"%{actor_email}%"))
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if date_from:
        query = query.where(AuditEvent.created_at >= date_from)
    if date_to:
        query = query.where(AuditEvent.created_at <= date_to)

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0

    items_stmt = query.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit)
    res = await db.scalars(items_stmt)
    events = list(res.all())

    return AuditLogResponse(
        total=total,
        items=[
            AuditEventOut(
                id=e.id,
                organization_id=e.organization_id,
                user_id=e.user_id,
                actor_email=e.actor_email,
                action=e.action,
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                ip_address=e.ip_address,
                user_agent=e.user_agent,
                detail=e.detail,
                details=e.details,
                created_at=e.created_at,
            )
            for e in events
        ],
        limit=limit,
        offset=offset,
    )


@router.get("/audit-logs/export.csv")
async def export_audit_logs_csv(
    org_id: uuid.UUID,
    action: str | None = None,
    actor_email: str | None = None,
    entity_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
) -> Response:
    if org_ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="Organization access mismatch")

    query = select(AuditEvent).where(AuditEvent.organization_id == org_id)
    if action:
        query = query.where(AuditEvent.action == action)
    if actor_email:
        query = query.where(AuditEvent.actor_email.ilike(f"%{actor_email}%"))
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)

    query = query.order_by(AuditEvent.created_at.desc()).limit(10000)
    events = (await db.scalars(query)).all()

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Header
    writer.writerow(
        [
            "ID",
            "Timestamp (UTC)",
            "Actor Email",
            "Action",
            "Entity Type",
            "Entity ID",
            "IP Address",
            "User Agent",
            "Detail",
            "Details (JSON)",
        ]
    )

    for e in events:
        details_str = json.dumps(e.details) if e.details else ""
        writer.writerow(
            [
                sanitize_csv_cell(e.id),
                sanitize_csv_cell(e.created_at.isoformat() if e.created_at else ""),
                sanitize_csv_cell(e.actor_email),
                sanitize_csv_cell(e.action),
                sanitize_csv_cell(e.entity_type or ""),
                sanitize_csv_cell(e.entity_id or ""),
                sanitize_csv_cell(e.ip_address or ""),
                sanitize_csv_cell(e.user_agent or ""),
                sanitize_csv_cell(e.detail or ""),
                sanitize_csv_cell(details_str),
            ]
        )

    output.seek(0)
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"straz_audit_log_{org_ctx.organization.slug}_{now_str}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
        },
    )
