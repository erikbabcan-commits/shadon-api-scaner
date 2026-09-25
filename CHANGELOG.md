# Changelog

All notable changes to the **Stráž** security monitoring project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-09-25

### Added
- **Split-Deploy Architecture:**
  - Added dynamic CORS configuration (`STRAZ_CORS_ORIGINS`) and cross-site cookie configuration (`STRAZ_COOKIE_SAMESITE`, `STRAZ_COOKIE_DOMAIN`) in `apps/api/app/config.py`.
  - Configured Vercel deployment with [vercel.json](file:///c:/Users/magic/Documents/Projekty/ShadonsAPIpwa/apps/web/vercel.json) (SPA URL rewrites, security HTTP headers, caching headers).
  - Dynamic API base URL resolution (`VITE_API_URL`) with automatic 401 redirect event dispatching in `apps/web/src/lib/api.ts`.
- **Database Migrations:**
  - Integrated Alembic migrations with async SQLAlchemy engine support ([alembic.ini](file:///c:/Users/magic/Documents/Projekty/ShadonsAPIpwa/apps/api/alembic.ini), `alembic/env.py`).
  - Added initial schema migration `001_initial_schema.py` covering all tables (`users`, `apps`, `targets`, `scan_runs`, `findings`, `audit_events`) and composite indexes.
  - Added programmatic startup migration runner in `apps/api/app/migrations.py`.
- **Security & Authentication Hardening:**
  - Added `token_version` on `User` model with automatic session revocation when passwords are changed.
  - Added `POST /api/auth/change-password` endpoint with Argon2 hashing and rate-limiting.
  - Added distributed Redis-backed rate limiter using `INCR` + `EXPIRE` pattern with in-memory fallback and `X-RateLimit-*` response headers.
  - Added SSRF validators for `base_url`, `git_url`, and `image_ref` to block private/loopback network exploitation.
  - Added startup secret validation rejecting default secrets (`change-me-now`) in production mode.
- **Comprehensive Automated Test Suite:**
  - Created Pytest testing framework with asynchronous test fixtures in `apps/api/tests/conftest.py`.
  - Added integration and unit tests covering authentication, application management, target verification, scan runs, findings pagination, and security validations (12 passing tests).
- **Frontend Modernization & UX:**
  - Created reusable UI primitives: `ErrorBoundary`, `Toast` notifications, `Skeleton` loaders, `ConfirmModal` for destructive actions, and `EmptyState`.
  - Decomposed and refactored `AppDetailPage` into clean, maintainable modular components (`AppHeader`, `AppScansSection`, `AppSupplyChainSection`, `AppTargetsSection`, `AppDangerZone`).
  - Added clipboard copy helper for DNS verification tokens (`straz-verify=<token>`).
  - Added PWA offline fallback page at `public/offline.html`.
  - Replaced Tailwind v3 gradient syntax with modern Tailwind v4 `bg-linear-to-br`.
- **API Performance & Caching:**
  - Refactored `GET /api/findings/overview` with SQL aggregations and Redis caching (`straz:cache:overview`).
  - Added pagination headers (`X-Total-Count`, `X-Has-More`, `X-Next-Offset`) across list endpoints.
  - Reused ARQ Redis connection pool across request lifecycles.
- **Production Infrastructure & CI/CD:**
  - Multi-stage production `Dockerfile` for `apps/api` with non-root user (`appuser`), healthcheck probe, and slim runtime image.
  - Automated PostgreSQL database backup script with gzip compression and 7-day retention in `deploy/backup-db.sh`.
  - Docker Compose production overlay with CPU/memory limits, JSON log rotation, and restart policies in `deploy/docker-compose.prod.yml`.
  - Automated GitHub Actions CI workflow in `.github/workflows/ci.yml` running backend pytest and frontend Vite production builds.
