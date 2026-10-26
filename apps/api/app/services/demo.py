"""Idempotent, explicitly synthetic demo fixtures. Never scan their domains."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (App, AuditEvent, Finding, FindingSeverity, FindingSource,
    Organization, OrganizationMember, OrgRole, RunStatus, ScanProfile, ScanRun,
    Target, TargetStatus, User)

NAMESPACE = uuid.UUID("a95c7f67-01c0-4ef8-a2b1-86e18fb91740")


def demo_id(name: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, name)


async def seed_demo(db: AsyncSession, user: User) -> dict[str, int]:
    """Caller owns transaction. Existing non-demo objects are never modified."""
    org_id = demo_id("organization")
    org = await db.get(Organization, org_id)
    if org is None:
        if await db.scalar(select(Organization.id).where(Organization.slug == "straz-golden-demo")):
            raise ValueError("Demo slug is occupied; refusing to modify an existing workspace")
        org = Organization(id=org_id, name="[DEMO] Stráž Workspace", slug="straz-golden-demo", plan_tier="pro")
        db.add(org)
        await db.flush()
        db.add(OrganizationMember(id=demo_id("owner"), org_id=org_id, user_id=user.id, role=OrgRole.owner))
    else:
        owner = await db.scalar(select(OrganizationMember).where(
            OrganizationMember.org_id == org_id, OrganizationMember.user_id == user.id,
            OrganizationMember.role == OrgRole.owner))
        if owner is None:
            raise ValueError("Only the existing demo owner may seed this workspace")

    fixtures = (
        ("E-Shop Produkcia", "https://eshop-demo.sk", 42.0, "99.98%"),
        ("Klient Portál API", "https://api.klient-portal.sk", 18.0, "100%"),
        ("Interný Auth Server", "https://auth.straz.sk", 24.0, "99.85%"),
    )
    now = datetime.now(timezone.utc)
    for index, (name, url, latency, uptime) in enumerate(fixtures):
        app_id = demo_id(f"app:{index}")
        if await db.get(App, app_id) is None:
            db.add(App(id=app_id, organization_id=org_id, name=f"[DEMO] {name}", environment="demo",
                base_url=url, heartbeat_enabled=False, tls_enabled=False, http_enabled=False,
                safe_enabled=False, internetdb_enabled=False, subdomain_enabled=False,
                ports_enabled=False, trivy_enabled=False, gitleaks_enabled=False,
                last_status_code=200, last_latency_ms=latency, last_up=True,
                last_checked_at=now, last_title=f"SYNTHETIC demo; illustrative uptime {uptime}; not a measurement"))
            await db.flush()
            db.add(Target(id=demo_id(f"target:{index}"), app_id=app_id,
                host=url.split("://", 1)[1], status=TargetStatus.pending,
                verify_token=uuid.uuid4().hex))
    examples = (
        ("critical", "nuclei", "Log4j RCE exposure — illustrative fixture"),
        ("high", "tls", "TLS certificate expires in 5 days — illustrative fixture"),
        ("high", "httpx", "Missing HSTS and CSP headers"),
        ("medium", "trivy", "Outdated OpenSSL library"),
        ("medium", "httpx", "Permissive CORS wildcard"),
        ("medium", "nuclei", "Exposed Swagger UI"),
        ("medium", "nuclei", "Missing authentication rate limiting"),
        ("low", "httpx", "Server information header"),
        ("low", "tls", "Weak cipher suite"),
        ("info", "naabu", "Illustrative development port exposure"),
    )
    for index, (severity, source, title) in enumerate(examples):
        finding_id = demo_id(f"finding:{index}")
        if await db.get(Finding, finding_id) is None:
            db.add(Finding(id=finding_id, app_id=demo_id(f"app:{index % 3}"),
                source=FindingSource(source), severity=FindingSeverity(severity),
                title=f"[DEMO] {title}", detail="SYNTHETIC DEMO DATA. No scan or vulnerability verification was performed.",
                fingerprint=f"demo:{index}"))
    for index, profile in enumerate(("tls", "heartbeat", "safe", "ports", "tls")):
        run_id = demo_id(f"run:{index}")
        if await db.get(ScanRun, run_id) is None:
            db.add(ScanRun(id=run_id, app_id=demo_id(f"app:{index % 3}"), profile=ScanProfile(profile),
                status=RunStatus.done, observations_complete=False, started_at=now, finished_at=now,
                error="SYNTHETIC demo history; not usable as CI scan evidence"))
    for index in range(10):
        audit_id = demo_id(f"audit:{index}")
        if await db.get(AuditEvent, audit_id) is None:
            db.add(AuditEvent(id=audit_id, organization_id=org_id, actor_email="DEMO fixture",
                action="demo.example", entity_type="organization", entity_id=str(org_id),
                details={"synthetic": True, "example_index": index,
                    "description": "Illustrative audit history; not an actual login or security action"}))
    await db.flush()
    return {"apps": 3, "findings": 10, "runs": 5, "audit_examples": 10}
