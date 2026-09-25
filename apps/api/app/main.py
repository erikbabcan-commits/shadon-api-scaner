from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import redis.asyncio as aioredis
from sqlalchemy import select, text

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.logging import setup_logging
from app.migrations import apply_migrations_async
from app.models import User
from app.routers import apps, auth, findings, runs
from app.security import hash_password

logger = logging.getLogger("straz.api")
START_TIME = time.time()


def validate_environment_security(settings: Settings) -> None:
    """Ensure weak default secrets are strictly rejected in production."""
    if settings.is_production or settings.straz_cookie_secure:
        if (
            "change-me" in settings.straz_session_secret.lower()
            or len(settings.straz_session_secret) < 32
        ):
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: STRAZ_SESSION_SECRET contains "
                "default insecure placeholder or is shorter than 32 characters. "
                "Refusing to start in production."
            )
        if "change-me" in settings.straz_admin_password.lower():
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: STRAZ_ADMIN_PASSWORD contains "
                "default placeholder 'change-me-now'. Please set a strong admin password."
            )


async def bootstrap_admin() -> None:
    settings = get_settings()
    async with SessionLocal() as db:
        existing = await db.scalar(
            select(User).where(User.email == settings.straz_admin_email.lower())
        )
        if existing:
            return
        db.add(
            User(
                email=settings.straz_admin_email.lower(),
                password_hash=hash_password(settings.straz_admin_password),
            )
        )
        await db.commit()
        logger.info("Bootstrapped default admin user: %s", settings.straz_admin_email)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    setup_logging(settings.is_production)
    logger.info("Initializing Stráž API (env=%s)...", settings.straz_env)

    validate_environment_security(settings)
    await apply_migrations_async()
    await bootstrap_admin()

    yield
    logger.info("Stráž API shutting down...")


settings = get_settings()

app = FastAPI(
    title="Stráž API",
    description="Vlastná monitoring a bezpečnostná konzola",
    version="1.0.0",
    lifespan=lifespan,
)

# 1. CORS Middleware (allows Vercel frontend or custom origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Request-ID",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ],
)


# 2. Request ID, Security Headers & Structured Request Logging Middleware
@app.middleware("http")
async def security_and_tracing_middleware(request: Request, call_next):
    start_time = time.monotonic()
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id

    # Security check: CSRF protection on mutating requests if cross-origin
    # Custom headers like X-Requested-With or standard Origin validation
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin and settings.is_production:
            # Check if origin is in allowed origins
            if origin not in settings.cors_origins_list:
                logger.warning("Rejected mutating request with untrusted origin: %s", origin)
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Forbidden: untrusted origin"},
                )

    try:
        response: Response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.monotonic() - start_time) * 1000, 2)
        logger.exception(
            "Unhandled exception during %s %s [%.2f ms] (request_id=%s)",
            request.method,
            request.url.path,
            duration_ms,
            request_id,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Vyskytla sa interná chyba servera.",
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    duration_ms = round((time.monotonic() - start_time) * 1000, 2)

    # Attach response headers
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"

    # Log request in structured format
    if not request.url.path.startswith("/api/health"):
        logger.info(
            "%s %s -> %s [%.2f ms] (request_id=%s)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )

    return response


# Include Routers
app.include_router(auth.router, prefix="/api")
app.include_router(apps.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(findings.router, prefix="/api")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Comprehensive health check checking DB and Redis pings, version, and uptime."""
    db_ok = False
    redis_ok = False

    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
            db_ok = True
    except Exception as exc:
        logger.error("Health check DB failure: %s", exc)

    try:
        r = aioredis.from_url(settings.redis_url, socket_timeout=1.0)
        await r.ping()
        await r.aclose()
        redis_ok = True
    except Exception as exc:
        logger.warning("Health check Redis failure: %s", exc)

    uptime_seconds = int(time.time() - START_TIME)
    healthy = db_ok and redis_ok

    return {
        "status": "ok" if healthy else "degraded",
        "database": "connected" if db_ok else "unreachable",
        "redis": "connected" if redis_ok else "unreachable",
        "version": "1.0.0",
        "uptime_seconds": uptime_seconds,
    }


@app.get("/api/health/ready")
async def readiness() -> JSONResponse:
    """Readiness probe for container orchestrators (k8s / docker)."""
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return JSONResponse(status_code=200, content={"ready": True})
    except Exception:
        return JSONResponse(status_code=503, content={"ready": False, "reason": "Database unavailable"})


@app.post("/api/client-errors", status_code=status.HTTP_204_NO_CONTENT)
async def log_client_error(payload: dict[str, Any], request: Request) -> None:
    """Receive and log unhandled frontend JavaScript errors."""
    logger.warning("Frontend Client Error: %s (ip=%s)", payload, request.client.host if request.client else "unknown")
