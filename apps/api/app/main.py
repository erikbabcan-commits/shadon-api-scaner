from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select

from app.config import Settings, get_settings
from app.db import SessionLocal, get_db
from app.logging import setup_logging
from app.migrations import apply_migrations_async
from app.models import User
from app.routers import (
    api_keys,
    apps,
    audit,
    auth,
    billing,
    ci,
    findings,
    health,
    integrations,
    organizations,
    reports,
    runs,
)
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
            from app.services.organizations import ensure_user_has_org
            await ensure_user_has_org(db, existing)
            await db.commit()
            return
        user = User(
            email=settings.straz_admin_email.lower(),
            password_hash=hash_password(settings.straz_admin_password),
        )
        db.add(user)
        await db.flush()
        from app.services.organizations import ensure_user_has_org
        await ensure_user_has_org(db, user)
        await db.commit()
        logger.info("Bootstrapped initial administrator")


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


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic's input/ctx fields can contain submitted passwords and webhook URLs.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": error["loc"], "type": error["type"], "msg": "Invalid value"}
        for error in exc.errors()
    ]})

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
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    # Security check: CSRF protection on mutating requests if cross-origin
    # Custom headers like X-Requested-With or standard Origin validation
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        has_cookie = any(name in request.cookies for name in (
            settings.straz_cookie_name, f"__Host-{settings.straz_cookie_name}"
        ))
        public_webhook = request.url.path == "/api/billing/webhook"
        headless_ci = (
            request.url.path == "/api/ci/scan"
            and not has_cookie
            and request.headers.get("authorization", "").startswith("Bearer straz_live_")
        )
        if settings.is_production and not public_webhook and not headless_ci:
            # Check if origin is in allowed origins
            if origin not in settings.cors_origins_list and not (
                origin is None and request.headers.get("x-requested-with") == "XMLHttpRequest"
            ):
                logger.warning("Rejected mutating request with untrusted origin")
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Forbidden: untrusted origin"},
                )

    try:
        response: Response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.monotonic() - start_time) * 1000, 2)
        logger.error(
            "Unhandled exception during %s (%s) [%.2f ms] (request_id=%s)",
            request.method,
            type(exc).__name__,
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
    if "Content-Security-Policy" not in response.headers:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Cache-Control"] = "no-store"

    # Log request in structured format
    if not request.url.path.startswith("/api/health"):
        logger.info(
            "%s %s -> %s [%.2f ms] (request_id=%s)",
            request.method,
            getattr(request.scope.get("route"), "path", "unmatched-route"),
            response.status_code,
            duration_ms,
            request_id,
        )

    return response


# Include Routers
app.include_router(auth.router, prefix="/api")
app.include_router(organizations.router, prefix="/api")
app.include_router(billing.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(integrations.router, prefix="/api")
app.include_router(apps.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(findings.router, prefix="/api")
app.include_router(api_keys.router)
app.include_router(ci.router)
app.include_router(audit.router)
app.include_router(health.router)


@app.get("/api/health")
@app.get("/api/health/ready")
async def legacy_readiness(db = Depends(get_db)) -> JSONResponse:
    from app.routers.health import readiness_probe
    return await readiness_probe(db=db, settings=settings)


@app.post("/api/client-errors", status_code=status.HTTP_204_NO_CONTENT)
async def log_client_error(request: Request, user: User = Depends(auth.get_current_user)) -> None:
    """Receive and log unhandled frontend JavaScript errors."""
    # Never persist arbitrary client messages, stack traces, URLs or form contents.
    logger.warning("Frontend client error reported")
