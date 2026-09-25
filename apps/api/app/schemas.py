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


import ipaddress
from typing import Generic, TypeVar
from urllib.parse import urlparse

T = TypeVar("T")


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


def _validate_safe_url(url: str) -> str:
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must have http or https scheme")
    host = parsed.hostname
    if not host:
        raise ValueError("URL must contain a valid host")

    blocked_hosts = {"localhost", "127.0.0.1", "::1", "169.254.169.254", "metadata.google.internal"}
    if host.lower() in blocked_hosts:
        raise ValueError(f"Restricted host '{host}' not allowed")

    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise ValueError(f"Restricted IP address '{host}' not allowed")
    except ValueError:
        pass

    return cleaned


def _validate_safe_git_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if url.startswith("https://") or url.startswith("http://") or url.startswith("git@") or url.startswith("ssh://"):
        if any(c in url for c in [";", "&", "|", "`", "$", "\n", "\r"]):
            raise ValueError("git_url contains unsafe characters")
        return url
    raise ValueError("git_url must use https, http, git@, or ssh protocol")


def _validate_safe_image_ref(ref: str | None) -> str | None:
    if not ref:
        return None
    ref = ref.strip()
    if any(c in ref for c in [";", "&", "|", "`", "$", " ", "\n", "\r"]):
        raise ValueError("image_ref contains unsafe characters")
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
