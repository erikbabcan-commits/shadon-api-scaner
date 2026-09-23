from __future__ import annotations

import httpx

from app.config import Settings, get_settings


def _header_value(value: str) -> str:
    # HTTP headers must be latin-1; keep readable ASCII fallback for ntfy Title/Tags.
    return value.encode("ascii", "replace").decode("ascii")


async def send_ntfy(title: str, message: str, *, priority: int = 3, tags: str = "warning") -> None:
    settings = get_settings()
    if not settings.ntfy_topic:
        return
    url = f"{settings.ntfy_url.rstrip('/')}/{settings.ntfy_topic}"
    headers = {
        "Title": _header_value(title),
        "Priority": str(priority),
        "Tags": _header_value(tags),
    }
    if settings.ntfy_token:
        headers["Authorization"] = f"Bearer {settings.ntfy_token}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, content=message.encode("utf-8"), headers=headers)
    except httpx.HTTPError:
        return
