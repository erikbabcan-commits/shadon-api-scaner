from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db
from app.services.health import check_database_latency, check_redis_latency

router = APIRouter(tags=["observability"])

_START_TIME = time.time()


@router.get("/healthz/liveness", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict[str, Any]:
    """
    Kubernetes / Cloud provider liveness probe.
    Returns 200 OK if the process is alive.
    """
    uptime = int(time.time() - _START_TIME)
    return {
        "status": "ok",
        "service": "straz-api",
        "uptime_seconds": uptime,
    }


@router.get("/healthz/readiness")
async def readiness_probe(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """
    Kubernetes / Cloud provider readiness probe.
    Verifies live connectivity and latencies for PostgreSQL / SQLite and Redis.
    """
    db_ok, db_latency_ms, db_err = await check_database_latency(db)
    redis_ok, redis_latency_ms, redis_err = await check_redis_latency(settings.redis_url)

    checks: dict[str, Any] = {
        "database": {
            "status": "ok" if db_ok else "error",
            "latency_ms": db_latency_ms,
            "error": db_err,
        },
        "redis": {
            "status": "ok" if redis_ok else "unreachable",
            "latency_ms": redis_latency_ms,
            "error": redis_err,
        },
    }

    if not db_ok:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "ready": False,
                "checks": checks,
            },
        )

    overall_status = "healthy" if (db_ok and redis_ok) else "degraded"
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": overall_status,
            "ready": True,
            "checks": checks,
        },
    )
