from __future__ import annotations

import httpx

from app.config import Settings, get_settings


async def send_ntfy(title: str, message: str, *, priority: int = 3, tags: str = "warning") -> None:
    settings = get_settings()
    if not settings.ntfy_topic:
        return
    url = f"{settings.ntfy_url.rstrip('/')}/{settings.ntfy_topic}"
    headers = {
        "Title": title,
        "Priority": str(priority),
        "Tags": tags,
    }
    if settings.ntfy_token:
        headers["Authorization"] = f"Bearer {settings.ntfy_token}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, content=message.encode("utf-8"), headers=headers)
    except httpx.HTTPError:
        return
