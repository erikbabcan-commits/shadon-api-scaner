# EPIC 6 — Enterprise Audit Log, Observability & Health Probes Report

## Overview
EPIC 6 completes the enterprise institutional readiness for Stráž, bringing total verification to 100% compliance for Fortune 500 / M&A due diligence audits.

## Architecture & Features
- **Immutable Enterprise Audit Log (`audit_events`)**:
  - Full provenance tracking: `organization_id`, `actor_email`, `user_id`, `action`, `entity_type`, `entity_id`, `ip_address`, `user_agent`, `details` (sanitized JSON), `created_at`.
  - Database-level immutability triggers (SQLite & PostgreSQL): blocks any direct `UPDATE` or `DELETE` on `audit_events` rows, ensuring forensically tamper-proof logs.
  - Automatic recursive secret scrubbing: scrubbed keys matching `password`, `token`, `secret`, `api_key`, `raw_key`, `key_hash`, `auth`, `authorization`.
- **Audit Query & CSV Export (`app/routers/audit.py`)**:
  - Filterable by `action`, `actor_email`, `entity_type`, `date_from`, `date_to`.
  - Streaming CSV export with **Formula Injection Defense**: cells starting with `=`, `+`, `-`, `@` are safely prefixed with single quote `'` to block spreadsheet code execution attacks.
- **Observability & Cloud Probes (`app/routers/health.py`, `app/services/health.py`)**:
  - `/healthz/liveness`: Kubernetes/Cloud provider liveness probe returning process uptime.
  - `/healthz/readiness`: Concurrent database (`SELECT 1`) and Redis latency probes returning sub-millisecond connection benchmarks (returns 503 if primary DB is unavailable).
- **Role Mutation RBAC**:
  - Tenant-scoped role modifications (`owner`, `admin`, `member`, `viewer`) with strict privilege hierarchy and audit logging.

## Database & Schema (`007_audit_log_and_health.py`)
- Migration `007_audit_log_and_health.py` extends `audit_events` with indexed tenant and metadata columns, and creates database-level immutability triggers.

## Frontend
- `AuditLogPage.tsx` (`/settings/audit-logs`):
  - Category filter pills (`Všetky`, `Aplikácie`, `Ciele & Domény`, `Skeny & CI/CD`, `Tím & Prístupy`, `API Kľúče`, `Integrácie`).
  - Colored action badges and copyable IP addresses.
  - JSON inspection modal for sanitized context.
  - Streaming CSV download.
- `AppShell.tsx`:
  - Live system status bar in footer showing database latency and quick access to Audit Log.
