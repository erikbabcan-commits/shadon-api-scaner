# EPIC 4 — Enterprise Alerting Hub Report

## Overview
EPIC 4 delivers a multi-channel notification dispatcher supporting Slack, Discord, Microsoft Teams, ntfy.sh, and custom signed webhooks.

## Architecture & Providers
- **Providers (`app/services/notifications/formatters.py`)**:
  - **Slack**: Block Kit formatting with severity colors and Markdown fields.
  - **Discord**: Rich Embed cards with severity badges and timestamps.
  - **Microsoft Teams**: Adaptive Cards schema (v1.4) for modern Teams workflows.
  - **Custom Webhook**: Structured JSON payload with HMAC-SHA256 signature (`X-Straz-Signature: sha256=...`).
  - **ntfy.sh**: Native push notifications with priority tagging.
- **SSRF & Network Protection (`app/services/notifications/transport.py`)**:
  - Strict HTTPS validation, loopback/private IP blocking (`127.0.0.1`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, cloud metadata endpoints).
  - 5-second request timeouts.

## Plan Quotas
- **Free**: 1 channel max (ntfy, webhook without HMAC).
- **Starter**: 3 channels max (Slack, Discord, ntfy, webhook without HMAC).
- **Pro / Agency**: Unlimited channels, all 5 platforms, HMAC-SHA256 webhook signatures enabled.

## Database & Schema
- **Migration `005_integrations_and_alerting.py`**:
  - `alert_channels`: Tenant-isolated channel configs with masked destination URLs and severity thresholds.
  - `alert_events`: Transactional outbox logging delivery statuses (`pending`, `sent`, `failed`).

## Frontend
- `IntegrationsPage.tsx`: Interactive channel management, modal creation dialog, active/pause toggle, and live test delivery trigger.
