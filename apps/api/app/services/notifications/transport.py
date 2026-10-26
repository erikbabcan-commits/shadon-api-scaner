from __future__ import annotations

import logging
import asyncio
import json


from app.models import AlertChannel
from app.services.notifications import formatters
from app.services.safe_http import public_http_client, validate_public_url

logger = logging.getLogger("straz.notifications")


def validate_destination_url(url: str, is_test_env: bool = False) -> None:
    # Tests mock the transport; environment names must never bypass validation.
    validate_public_url(url.strip(), https_only=True)


async def send_to_channel(
    channel: AlertChannel,
    event_type: str,
    severity: str,
    title: str,
    detail: str | None,
    app_name: str | None,
    is_test_env: bool = False,
) -> bool:
    platform = channel.platform.lower()

    try:
        validate_destination_url(channel.destination_url)
        async with asyncio.timeout(5), public_http_client() as client:
            if platform == "slack":
                payload = formatters.format_slack(channel, event_type, severity, title, detail, app_name)
                res = await client.post(channel.destination_url, json=payload)
            elif platform == "discord":
                payload = formatters.format_discord(channel, event_type, severity, title, detail, app_name)
                res = await client.post(channel.destination_url, json=payload)
            elif platform == "teams":
                payload = formatters.format_teams(channel, event_type, severity, title, detail, app_name)
                res = await client.post(channel.destination_url, json=payload)
            elif platform == "webhook":
                payload, headers = formatters.format_webhook(channel, event_type, severity, title, detail, app_name)
                body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
                res = await client.post(channel.destination_url, content=body, headers=headers)
            elif platform == "ntfy":
                ntfy_body, headers = formatters.format_ntfy(channel, event_type, severity, title, detail, app_name)
                res = await client.post(channel.destination_url, content=ntfy_body.encode("utf-8"), headers=headers)
            else:
                logger.error("Unknown notification platform: %s", platform)
                return False

            return 200 <= res.status_code < 300
    except Exception as exc:
        logger.warning("Notification delivery failed (channel_id=%s, error_type=%s)", channel.id, type(exc).__name__)
        return False
