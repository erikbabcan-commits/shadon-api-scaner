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
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError("invalid email")
        return email


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)

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


from typing import Generic, TypeVar

T = TypeVar("T")


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


def _validate_safe_url(url: str) -> str:
    from app.services.safe_http import validate_public_url
    cleaned = url.strip()
    validate_public_url(cleaned)
    return cleaned


def _validate_safe_git_url(url: str | None) -> str | None:
    if not url:
        return None
    from app.services.safe_http import validate_public_url
    cleaned = url.strip()
    validate_public_url(cleaned, https_only=True)
    return cleaned


def _validate_safe_image_ref(ref: str | None) -> str | None:
    if not ref:
        return None
    ref = ref.strip()
    if "://" in ref or not __import__("re").fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@-]*", ref):
        raise ValueError("image_ref contains unsafe characters")
    registry = ref.split("/", 1)[0]
    if "/" in ref and ("." in registry or ":" in registry or registry == "localhost"):
        from app.services.safe_http import validate_public_url
        validate_public_url(f"https://{registry}")
    return ref


class AppCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    environment: str = Field(default="prod", max_length=50)
    base_url: str = Field(min_length=1, max_length=500)
    heartbeat_enabled: bool = True
    tls_enabled: bool = True
    http_enabled: bool = True
    safe_enabled: bool = True
    internetdb_enabled: bool = True
    subdomain_enabled: bool = True
    ports_enabled: bool = True
    trivy_enabled: bool = True
    gitleaks_enabled: bool = True
    git_url: str | None = Field(default=None, max_length=500)
    image_ref: str | None = Field(default=None, max_length=500)

    @field_validator("base_url")
    @classmethod
    def check_base_url(cls, v: str) -> str:
        return _validate_safe_url(v)

    @field_validator("git_url")
    @classmethod
    def check_git_url(cls, v: str | None) -> str | None:
        return _validate_safe_git_url(v)

    @field_validator("image_ref")
    @classmethod
    def check_image_ref(cls, v: str | None) -> str | None:
        return _validate_safe_image_ref(v)


class AppUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    environment: str | None = Field(default=None, max_length=50)
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    heartbeat_enabled: bool | None = None
    tls_enabled: bool | None = None
    http_enabled: bool | None = None
    safe_enabled: bool | None = None
    internetdb_enabled: bool | None = None
    subdomain_enabled: bool | None = None
    ports_enabled: bool | None = None
    trivy_enabled: bool | None = None
    gitleaks_enabled: bool | None = None
    git_url: str | None = Field(default=None, max_length=500)
    image_ref: str | None = Field(default=None, max_length=500)

    @field_validator("base_url")
    @classmethod
    def check_base_url(cls, v: str | None) -> str | None:
        return _validate_safe_url(v) if v is not None else None

    @field_validator("git_url")
    @classmethod
    def check_git_url(cls, v: str | None) -> str | None:
        return _validate_safe_git_url(v)

    @field_validator("image_ref")
    @classmethod
    def check_image_ref(cls, v: str | None) -> str | None:
        return _validate_safe_image_ref(v)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None


class TargetCreate(BaseModel):
    host: str = Field(min_length=1, max_length=253)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        from app.services.safe_http import validate_public_url
        value = value.strip().lower().rstrip(".")
        parsed = validate_public_url(f"https://{value}")
        if parsed.host != value or parsed.port is not None or parsed.raw_path != b"/":
            raise ValueError("Target must be a hostname without a path or port")
        return value


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
    organization_id: uuid.UUID
    name: str
    environment: str
    base_url: str
    heartbeat_enabled: bool
    tls_enabled: bool
    http_enabled: bool
    safe_enabled: bool
    internetdb_enabled: bool
    subdomain_enabled: bool
    ports_enabled: bool
    trivy_enabled: bool
    gitleaks_enabled: bool
    git_url: str | None
    image_ref: str | None
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
