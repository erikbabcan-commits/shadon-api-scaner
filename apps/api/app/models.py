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
    String,
    Text,
    TypeDecorator,
    CHAR,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class App(Base):
    __tablename__ = "apps"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
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

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID, nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
