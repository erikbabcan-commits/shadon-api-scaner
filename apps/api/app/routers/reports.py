from __future__ import annotations

import uuid
import base64
import hashlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import OrgContext, require_org_role
from app.models import App, Finding, OrgRole
from app.services.audit import write_audit
from app.services.compliance import (
    calculate_security_score,
    evaluate_nis2_areas,
    map_owasp_top_10,
)
from app.services.quota import get_plan_tier
from app.services.reporting import generate_html_report, PRINT_SCRIPT

router = APIRouter(tags=["reports"])


class BrandingUpdateRequest(BaseModel):
    custom_logo_url: str | None = Field(default=None, max_length=500)
    brand_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    report_footer_text: str | None = Field(default=None, max_length=255)

    @field_validator("custom_logo_url")
    @classmethod
    def validate_logo(cls, value: str | None) -> str | None:
        if value:
            from app.services.safe_http import validate_public_url
            validate_public_url(value, https_only=True)
        return value


@router.get("/apps/{app_id}/compliance")
async def get_app_compliance(
    app_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.viewer)),
) -> dict[str, Any]:
    app = await db.scalar(
        select(App).where(
            App.id == app_id,
            App.organization_id == org_ctx.org_id,
        )
    )
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    findings = list(
        await db.scalars(select(Finding).where(Finding.app_id == app.id))
    )

    scoring = calculate_security_score(findings, app)
    nis2 = evaluate_nis2_areas(findings, app)
    owasp = map_owasp_top_10(findings)

    return {
        "assessment_type": "technical_indicators_not_legal_certification",
        "coverage": "not_verified",
        "app_id": app.id,
        "app_name": app.name,
        "base_url": app.base_url,
        "scoring": scoring,
        "nis2_readiness": nis2,
        "owasp_distribution": owasp,
    }


@router.get("/apps/{app_id}/report/html", response_class=HTMLResponse)
async def get_app_html_report(
    app_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.viewer)),
) -> HTMLResponse:
    app = await db.scalar(
        select(App).where(
            App.id == app_id,
            App.organization_id == org_ctx.org_id,
        )
    )
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    findings = list(
        await db.scalars(select(Finding).where(Finding.app_id == app.id))
    )

    html_text = generate_html_report(app, org_ctx.organization, findings)
    script_hash = base64.b64encode(hashlib.sha256(PRINT_SCRIPT.encode()).digest()).decode()
    return HTMLResponse(content=html_text, status_code=200, headers={
        "Content-Security-Policy": f"default-src 'none'; script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'; img-src https:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        "Cache-Control": "no-store",
    })


@router.get("/orgs/{org_id}/branding")
async def get_org_branding(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.viewer)),
) -> dict[str, Any]:
    if org_ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot access branding of another organization")
    org = org_ctx.organization
    tier = get_plan_tier(org)
    return {
        "custom_logo_url": org.custom_logo_url,
        "brand_color": org.brand_color or "#0284c7",
        "report_footer_text": org.report_footer_text,
        "white_label_enabled": tier in ("pro", "agency"),
    }


@router.patch("/orgs/{org_id}/branding")
async def update_org_branding(
    org_id: uuid.UUID,
    body: BrandingUpdateRequest,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(require_org_role(OrgRole.admin)),
) -> dict[str, Any]:
    if org_ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot update branding of another organization")
    org = org_ctx.organization
    tier = get_plan_tier(org)
    if tier not in ("pro", "agency"):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="White-label branding vyžaduje plán Pro alebo Agency.",
            headers={"X-Upgrade-Required": "true"},
        )

    if body.custom_logo_url is not None:
        org.custom_logo_url = body.custom_logo_url.strip() if body.custom_logo_url else None
    if body.brand_color is not None:
        color = body.brand_color.strip()
        if not color.startswith("#") or len(color) not in (4, 7):
            raise HTTPException(status_code=400, detail="Invalid hex color format (e.g. #0284c7)")
        org.brand_color = color
    if body.report_footer_text is not None:
        org.report_footer_text = body.report_footer_text.strip() if body.report_footer_text else None

    await write_audit(
        db,
        action="branding.update",
        user_id=org_ctx.user.id,
        entity_type="organization",
        entity_id=str(org.id),
        detail="Updated custom branding settings",
    )
    await db.commit()
    return {
        "custom_logo_url": org.custom_logo_url,
        "brand_color": org.brand_color,
        "report_footer_text": org.report_footer_text,
    }
