from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models import (
    FindingSeverity,
    FindingSource,
    FindingStatus,
    RunStatus,
    ScanProfile,
    TargetStatus,
)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError("invalid email")
        return email


class UserOut(BaseModel):
    id: uuid.UUID
    email: str

    model_config = {"from_attributes": True}


class AppCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    environment: str = Field(default="prod", max_length=50)
    base_url: str = Field(min_length=1, max_length=500)
    heartbeat_enabled: bool = True
    tls_enabled: bool = True
    http_enabled: bool = True
    safe_enabled: bool = True


class AppUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    environment: str | None = Field(default=None, max_length=50)
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    heartbeat_enabled: bool | None = None
    tls_enabled: bool | None = None
    http_enabled: bool | None = None
    safe_enabled: bool | None = None


class TargetCreate(BaseModel):
    host: str = Field(min_length=1, max_length=500)


class TargetOut(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    host: str
    status: TargetStatus
    verify_token: str
    verify_method: str | None
    trusted_private: bool
    created_at: datetime
    verified_at: datetime | None

    model_config = {"from_attributes": True}


class AppOut(BaseModel):
    id: uuid.UUID
    name: str
    environment: str
    base_url: str
    heartbeat_enabled: bool
    tls_enabled: bool
    http_enabled: bool
    safe_enabled: bool
    last_status_code: int | None
    last_latency_ms: float | None
    last_title: str | None
    last_up: bool | None
    last_checked_at: datetime | None
    created_at: datetime
    targets: list[TargetOut] = []

    model_config = {"from_attributes": True}


class TrustPrivateRequest(BaseModel):
    confirm: bool = True


class RunCreate(BaseModel):
    profile: ScanProfile


class RunOut(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    profile: ScanProfile
    status: RunStatus
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FindingOut(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    target_id: uuid.UUID | None
    source: FindingSource
    severity: FindingSeverity
    title: str
    detail: str | None
    fingerprint: str
    status: FindingStatus
    first_seen_at: datetime
    last_seen_at: datetime
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class FindingUpdate(BaseModel):
    status: FindingStatus


class OverviewApp(BaseModel):
    id: uuid.UUID
    name: str
    environment: str
    last_up: bool | None
    last_status_code: int | None
    last_latency_ms: float | None
    last_checked_at: datetime | None
    open_findings: int


class OverviewOut(BaseModel):
    apps: list[OverviewApp]
    open_by_severity: dict[str, int]
    certs_expiring_soon: int
    running_scans: int
