from __future__ import annotations

import ipaddress
import logging
from urllib.parse import urlparse

import httpx

from app.models import AlertChannel
from app.services.notifications import formatters

logger = logging.getLogger("straz.notifications")


def validate_destination_url(url: str, is_test_env: bool = False) -> None:
    parsed = urlparse(url.strip())
    if not is_test_env and parsed.scheme != "https":
        raise ValueError("Iba zabezpečené HTTPS adresy sú povolené pre notifikačné kanály.")
    host = parsed.hostname or ""
    if not is_test_env:
        blocked = {"localhost", "127.0.0.1", "::1", "169.254.169.254", "metadata.google.internal"}
        if host.lower() in blocked:
            raise ValueError(f"Adresa '{host}' je blokovaná z bezpečnostných dôvodov.")
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_loopback or ip.is_private or ip.is_link_local:
                raise ValueError(f"Privátna IP adresa '{host}' nie je povolená.")
        except ValueError:
            pass


async def send_to_channel(
    channel: AlertChannel,
    event_type: str,
    severity: str,
    title: str,
    detail: str | None,
    app_name: str | None,
    is_test_env: bool = False,
) -> bool:
    validate_destination_url(channel.destination_url, is_test_env)

    platform = channel.platform.lower()

    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
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
                res = await client.post(channel.destination_url, json=payload, headers=headers)
            elif platform == "ntfy":
                body, headers = formatters.format_ntfy(channel, event_type, severity, title, detail, app_name)
                res = await client.post(channel.destination_url, content=body.encode("utf-8"), headers=headers)
            else:
                logger.error("Unknown notification platform: %s", platform)
                return False

            return 200 <= res.status_code < 300
    except Exception as exc:
        logger.warning("Notification delivery to %s failed: %s", channel.destination_url, exc)
        return False
