> Historický implementačný report; nie dôkaz aktuálneho nasadenia alebo dostupnosti profilov. Aktuálny rozsah a stav: [NOTION_NOTES.md](../NOTION_NOTES.md).

# EPIC 2 — Stripe Billing and Quota Engine Report

## Overview
EPIC 2 implements commercial monetization, plan enforcement, row-locked quota checks, and Stripe integration (Checkout, Customer Portal, Webhooks with signature verification and simulation mode).

## Pricing Plans & Quotas
- **Free (0 € / mes.)**: 1 app, 10 scans/month, heartbeat & Shodan InternetDB profiles, manual scans only.
- **Starter (29 € / mes.)**: 5 apps, 100 scans/month, network profiles, weekly scheduled scans.
- **Pro (79 € / mes.)**: 25 apps, 1000 scans/month, all scan profiles (Trivy supply chain, Gitleaks, Nuclei), daily scheduled scans, white-label PDF reports, unlimited alert channels.
- **Agency (199 € / mes.)**: Unlimited apps, unlimited scans, hourly cadence, full white-labeling.

## Database & Schema
- **Migration `003_billing_and_quotas.py`**:
  - `billing_events`: Idempotency tracking for processed Stripe webhook events (`stripe_event_id`, `event_type`, `payload`).
  - `scan_usage`: Transactional quota reservation records across billing periods.

## Services & Routers
- `app/services/quota.py`: Quota admission check before creating apps and queuing scans. Returns HTTP 402 with `X-Upgrade-Required: true` upon exhaustion.
- `app/services/stripe.py`: Checkout Session & Customer Portal creation, HMAC-SHA256 webhook signature verification with automatic simulation fallback for development/test environments.
- `app/routers/billing.py`: Public plans endpoint, usage statistics, checkout and portal redirects.

## Frontend
- `BillingPage.tsx`: Plan pricing grid, usage progress indicators, upgrade triggers.
- `UpgradeModal.tsx`: Native popup modal shown when user hits quota limit.
