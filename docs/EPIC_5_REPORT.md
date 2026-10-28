> Historický implementačný report; nie dôkaz aktuálneho nasadenia alebo dostupnosti profilov. Aktuálny rozsah a stav: [NOTION_NOTES.md](../NOTION_NOTES.md).

# EPIC 5 — Scoped API Keys & DevSecOps CI/CD Gate Report

## Overview
EPIC 5 equips Stráž with enterprise headless automation, enabling development teams to embed security gates directly into GitHub Actions, GitLab CI, and custom deployment pipelines.

## Architecture & Features
- **Scoped API Keys (`straz_live_...`)**:
  - Secure token generation: `straz_live_` prefix followed by 32 cryptographically random URL-safe characters (192-bit entropy).
  - SHA-256 hash storage: Plaintext token is shown strictly once upon creation; only SHA-256 hash and 16-character display prefix are stored in the database.
  - Granular scopes: `ci:scan`, `apps:read`, `findings:read`, `reports:read`.
- **Authentication & RBAC (`app/deps.py`)**:
  - Bearer API key authentication (`Authorization: Bearer straz_live_...` or `X-API-Key`).
  - Strict tenant scoping: API key forces organization context to the creator's workspace; cross-tenant headers are rejected.
  - Automatic `last_used_at` updating and expiration enforcement.
- **Headless CI/CD Engine (`app/routers/ci.py`, `app/services/ci.py`)**:
  - `POST /api/ci/scan`:
    - Strict domain ownership requirement (verified target mandatory for CI scans).
    - Threshold evaluation (`fail_on`: `critical`, `high`, `medium`).
    - Synchronous wait mode (`wait=True`) with configurable timeout (1–600 seconds) or immediate 202 Accepted.
    - Exit gate semantics: returns HTTP 200 with `passed: true` when below threshold; returns HTTP 424 Failed Dependency with `passed: false` when threshold is exceeded or scan execution fails.
  - `GET /api/ci/runs/{run_id}`: Polling and verification endpoint for pipeline status.

## Plan Quotas
- **Free**: 0 API keys (console access only).
- **Starter**: Maximum 2 API keys.
- **Pro / Agency**: Unlimited API keys, unlimited CI pipeline invocations (within scan limits).

## Database & Schema (`006_api_keys_and_ci.py`)
- `api_keys`: Tenant-bound API keys with SHA-256 hashes, prefixes, JSON scopes, and expiration timestamps.
- `scan_run_findings`: Composite table tracking run-specific observations and severities.
- `scan_runs`: Added `ci_fail_on` and `observations_complete`.

## Frontend
- `ApiKeysPage.tsx`:
  - Active key inventory, prefix and scopes badges, revocation controls.
  - Secure creation modal with one-time copy banner and warning.
  - Tier upgrade prompt for Free workspaces.
- `CiCodeGenerator.tsx`:
  - Tabbed pipeline generator for GitHub Actions, GitLab CI, and cURL scripts with live application and failure threshold selectors.
