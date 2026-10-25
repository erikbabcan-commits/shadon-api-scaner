from __future__ import annotations

import time
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def check_database_latency(db: AsyncSession) -> tuple[bool, float, str | None]:
    start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return True, latency_ms, None
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return False, latency_ms, str(exc)


async def check_redis_latency(redis_url: str) -> tuple[bool, float, str | None]:
    start = time.perf_counter()
    try:
        r = aioredis.from_url(redis_url, socket_timeout=1.0)
        await r.ping()
        await r.aclose()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return True, latency_ms, None
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return False, latency_ms, str(exc)
