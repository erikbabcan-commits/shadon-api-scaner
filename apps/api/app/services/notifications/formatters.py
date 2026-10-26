from __future__ import annotations

import hashlib
import hmac
import json
import time
import base64
from typing import Any

from app.models import AlertChannel


def format_slack(channel: AlertChannel, event_type: str, severity: str, title: str, detail: str | None, app_name: str | None) -> dict[str, Any]:
    color = "#ef4444" if severity == "critical" else ("#f97316" if severity == "high" else "#eab308")
    app_text = f" na aplikácii *{app_name}*" if app_name else ""
    return {
        "text": f"🛡️ [Stráž Alert] {severity.upper()}: {title}{app_text}",
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Udalosť:* `{event_type}`\n*Závažnosť:* `{severity.upper()}`\n*Popis:* {title}",
                        },
                    },
                    *(
                        [
                            {
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": f"```{detail[:1000]}```"},
                            }
                        ]
                        if detail
                        else []
                    ),
                ],
            }
        ],
    }


def format_discord(channel: AlertChannel, event_type: str, severity: str, title: str, detail: str | None, app_name: str | None) -> dict[str, Any]:
    color_int = 0xEF4444 if severity == "critical" else (0xF97316 if severity == "high" else 0xEAB308)
    return {
        "content": None,
        "embeds": [
            {
                "title": f"🛡️ Stráž Alert: {title}",
                "description": detail[:2000] if detail else None,
                "color": color_int,
                "fields": [
                    {"name": "Závažnosť", "value": severity.upper(), "inline": True},
                    {"name": "Typ udalosti", "value": event_type, "inline": True},
                    *(
                        [{"name": "Aplikácia", "value": app_name, "inline": True}]
                        if app_name
                        else []
                    ),
                ],
                "footer": {"text": "Stráž Security Monitoring"},
            }
        ],
    }


def format_teams(channel: AlertChannel, event_type: str, severity: str, title: str, detail: str | None, app_name: str | None) -> dict[str, Any]:
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"🛡️ Stráž Bezpečnostné Upozornenie: {severity.upper()}",
                            "weight": "Bolder",
                            "size": "Medium",
                            "color": "Attention" if severity in ("critical", "high") else "Warning",
                        },
                        {
                            "type": "TextBlock",
                            "text": title,
                            "wrap": True,
                        },
                        *(
                            [
                                {
                                    "type": "TextBlock",
                                    "text": detail[:1000],
                                    "wrap": True,
                                    "fontType": "Monospace",
                                    "size": "Small",
                                }
                            ]
                            if detail
                            else []
                        ),
                    ],
                },
            }
        ],
    }


def format_webhook(
    channel: AlertChannel,
    event_type: str,
    severity: str,
    title: str,
    detail: str | None,
    app_name: str | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    payload = {
        "event_id": str(channel.id),
        "event_type": event_type,
        "severity": severity,
        "title": title,
        "detail": detail,
        "app_name": app_name,
        "timestamp": int(time.time()),
    }
    headers = {"Content-Type": "application/json"}
    if channel.secret_token:
        body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            channel.secret_token.encode("utf-8"), body_bytes, hashlib.sha256
        ).hexdigest()
        headers["X-Straz-Signature"] = f"sha256={signature}"
    return payload, headers


def format_ntfy(channel: AlertChannel, event_type: str, severity: str, title: str, detail: str | None, app_name: str | None) -> tuple[str, dict[str, str]]:
    priority = "5" if severity == "critical" else ("4" if severity == "high" else "3")
    headers = {
        "Title": "=?UTF-8?B?" + base64.b64encode(f"Stráž: {title[:180]}".encode("utf-8")).decode("ascii") + "?=",
        "Priority": priority,
        "Tags": "warning,shield" if severity in ("critical", "high") else "information",
    }
    if channel.secret_token:
        headers["Authorization"] = f"Bearer {channel.secret_token}"
    body = detail or f"Udalosť: {event_type} na {app_name or 'aplikácii'}"
    return body, headers
