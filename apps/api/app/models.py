from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    TypeDecorator,
    CHAR,
    UniqueConstraint,
    func,
    event,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import Mapper
from sqlalchemy.engine import Connection

from app.db import Base


class GUID(TypeDecorator):
    """Platform-independent GUID type: PG_UUID on PostgreSQL, CHAR(36) on SQLite."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value) if isinstance(value, uuid.UUID) else str(uuid.UUID(str(value)))

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class OrgRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    member = "member"
    viewer = "viewer"


class TargetStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    disabled = "disabled"


class ScanProfile(str, enum.Enum):
    heartbeat = "heartbeat"
    tls = "tls"
    http = "http"
    safe = "safe"
    internetdb = "internetdb"
    subdomain = "subdomain"
    ports = "ports"
    trivy_fs = "trivy_fs"
    trivy_image = "trivy_image"
    gitleaks = "gitleaks"


# External CLI scanners (tlsx/httpx/nuclei/subfinder/naabu/trivy/gitleaks/git)
# resolve DNS and connect on their own, so the Python SSRF pinning does not
# apply and no enforced, tested egress isolation exists yet (SECURITY_REVIEW
# H13). They stay blocked everywhere until that isolation is delivered.
CLI_SCANNER_PROFILES = frozenset(
    {
        ScanProfile.tls,
        ScanProfile.http,
        ScanProfile.safe,
        ScanProfile.subdomain,
        ScanProfile.ports,
        ScanProfile.trivy_fs,
        ScanProfile.trivy_image,
        ScanProfile.gitleaks,
    }
)
CLI_SCANNER_UNAVAILABLE = "Scan profile unavailable: external CLI scanners are disabled until network isolation is enforced"


class RunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class FindingSeverity(str, enum.Enum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class FindingSource(str, enum.Enum):
    heartbeat = "heartbeat"
    tls = "tls"
    httpx = "httpx"
    nuclei = "nuclei"
    internetdb = "internetdb"
    subdomain = "subdomain"
    naabu = "naabu"
    trivy = "trivy"
    gitleaks = "gitleaks"


class FindingStatus(str, enum.Enum):
    open = "open"
    accepted = "accepted"
    fixed = "fixed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    token_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    memberships: Mapped[list[OrganizationMember]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    billing_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    # Billing & quotas (EPIC 2)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plan_tier: Mapped[str] = mapped_column(String(50), default="free", server_default="free")
    subscription_status: Mapped[str] = mapped_column(String(50), default="active", server_default="active")
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # White-label branding (EPIC 3)
    custom_logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand_color: Mapped[str | None] = mapped_column(String(7), default="#0284c7", server_default="#0284c7", nullable=True)
    report_footer_text: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    members: Mapped[list[OrganizationMember]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    invitations: Mapped[list[OrganizationInvitation]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    apps: Mapped[list[App]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uq_org_member"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[OrgRole] = mapped_column(
        Enum(OrgRole, native_enum=False, length=16), default=OrgRole.member, server_default="member"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[OrgRole] = mapped_column(
        Enum(OrgRole, native_enum=False, length=16), default=OrgRole.member, server_default="member"
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="invitations")


class BillingEvent(Base):
    __tablename__ = "billing_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    stripe_event_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScanUsage(Base):
    __tablename__ = "scan_usage"
    __table_args__ = (
        Index("ix_scan_usage_org_period", "org_id", "period_start", "period_end"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scans_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlertChannel(Base):
    __tablename__ = "alert_channels"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    app_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("apps.id", ondelete="CASCADE"), nullable=True, index=True
    )
    platform: Mapped[str] = mapped_column(String(32))  # slack, discord, teams, webhook, ntfy
    name: Mapped[str] = mapped_column(String(100))
    destination_url: Mapped[str] = mapped_column(String(500))
    secret_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    min_severity: Mapped[str] = mapped_column(String(16), default="high", server_default="high")
    events: Mapped[str] = mapped_column(Text, default='["finding.created","app.down"]', server_default='["finding.created","app.down"]')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    app_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("apps.id", ondelete="CASCADE"), nullable=True, index=True
    )
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alert_channels.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class App(Base):
    __tablename__ = "apps"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    environment: Mapped[str] = mapped_column(String(50), default="prod")
    base_url: Mapped[str] = mapped_column(String(500))
    heartbeat_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    tls_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    http_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    safe_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    internetdb_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    subdomain_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    ports_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trivy_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    gitleaks_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    git_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_up: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization | None] = relationship(back_populates="apps")
    targets: Mapped[list[Target]] = relationship(back_populates="app", cascade="all, delete-orphan")
    runs: Mapped[list[ScanRun]] = relationship(back_populates="app", cascade="all, delete-orphan")
    findings: Mapped[list[Finding]] = relationship(back_populates="app", cascade="all, delete-orphan")


class Target(Base):
    __tablename__ = "targets"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    host: Mapped[str] = mapped_column(String(500))
    status: Mapped[TargetStatus] = mapped_column(
        Enum(TargetStatus, native_enum=False), default=TargetStatus.pending
    )
    verify_token: Mapped[str] = mapped_column(String(64))
    verify_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    trusted_private: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    app: Mapped[App] = relationship(back_populates="targets")


class ScanRun(Base):
    __tablename__ = "scan_runs"
    __table_args__ = (
        Index("ix_scan_runs_app_created", "app_id", "created_at"),
        Index("ix_scan_runs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    profile: Mapped[ScanProfile] = mapped_column(Enum(ScanProfile, native_enum=False, length=32))
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus, native_enum=False, length=16), default=RunStatus.queued)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID, nullable=True)
    ci_fail_on: Mapped[str | None] = mapped_column(String(20), nullable=True)
    observations_complete: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    app: Mapped[App] = relationship(back_populates="runs")


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("app_id", "fingerprint", name="uq_finding_fingerprint"),
        Index("ix_findings_app_status", "app_id", "status"),
        Index("ix_findings_status_last_seen", "status", "last_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("targets.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[FindingSource] = mapped_column(Enum(FindingSource, native_enum=False, length=32))
    severity: Mapped[FindingSeverity] = mapped_column(
        Enum(FindingSeverity, native_enum=False, length=16), default=FindingSeverity.info
    )
    title: Mapped[str] = mapped_column(String(500))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(128))
    status: Mapped[FindingStatus] = mapped_column(
        Enum(FindingStatus, native_enum=False), default=FindingStatus.open
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    app: Mapped[App] = relationship(back_populates="findings")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_org_created", "organization_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    organization: Mapped[Organization | None] = relationship()
    user: Mapped[User | None] = relationship()


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["ci:scan", "apps:read"], nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship()
    user: Mapped[User] = relationship()


@event.listens_for(AuditEvent, "before_update")
@event.listens_for(AuditEvent, "before_delete")
def prevent_audit_orm_mutation(mapper: Mapper[AuditEvent], connection: Connection, target: AuditEvent) -> None:
    # Defence in depth; DB triggers and DB role separation are still required.
    raise ValueError("Audit records are immutable")


class ScanRunFinding(Base):
    __tablename__ = "scan_run_findings"

    scan_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    finding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    observed_severity: Mapped[str] = mapped_column(String(20), nullable=False)
    is_new: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    scan_run: Mapped[ScanRun] = relationship()
    finding: Mapped[Finding] = relationship()
