from __future__ import annotations

import copy
import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent

SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|token|secret|api_key|raw_key|key_hash|authorization|private_key|auth)",
    re.IGNORECASE,
)


def sanitize_audit_details(data: Any) -> Any:
    """
    Recursively scrubs credentials, secrets, tokens and passwords from audit detail payloads.
    """
    if isinstance(data, dict):
        cleaned: dict[str, Any] = {}
        for k, v in data.items():
            if SENSITIVE_KEY_PATTERN.search(k):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = sanitize_audit_details(v)
        return cleaned
    elif isinstance(data, list):
        return [sanitize_audit_details(item) for item in data]
    elif isinstance(data, str):
        # Redact raw Bearer tokens or straz_live keys in free-form strings
        if "straz_live_" in data:
            data = re.sub(r"straz_live_[a-zA-Z0-9_\-]+", "straz_live_[REDACTED]", data)
        return data
    return data


async def write_audit_log(
    db: AsyncSession,
    *,
    action: str,
    org_id: uuid.UUID | None = None,
    actor_email: str = "system",
    user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    detail: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    """
    Persists an immutable audit log record for security, observability and M&A compliance.
    """
    sanitized_details = sanitize_audit_details(details) if details is not None else None
    sanitized_detail = sanitize_audit_details(detail) if detail is not None else None

    # Truncate user agent if necessary
    truncated_ua = user_agent[:500] if user_agent else None
    truncated_ip = ip_address[:45] if ip_address else None

    event = AuditEvent(
        id=uuid.uuid4(),
        organization_id=org_id,
        user_id=user_id,
        actor_email=actor_email,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        ip_address=truncated_ip,
        user_agent=truncated_ua,
        detail=sanitized_detail,
        details=sanitized_details,
    )
    db.add(event)
    return event


async def write_audit(
    db: AsyncSession,
    *,
    action: str,
    user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    detail: str | None = None,
    org_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Backwards-compatible wrapper for existing audit callers.
    """
    await write_audit_log(
        db,
        action=action,
        org_id=org_id,
        actor_email=actor_email or "system",
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=ip_address,
        user_agent=user_agent,
        detail=detail,
        details=details,
    )
