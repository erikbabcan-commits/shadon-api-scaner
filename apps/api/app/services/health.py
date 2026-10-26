from __future__ import annotations

import time
import asyncio

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def check_database_latency(db: AsyncSession) -> tuple[bool, float, str | None]:
    start = time.perf_counter()
    try:
        async with asyncio.timeout(2):
            await db.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return True, latency_ms, None
    except Exception:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return False, latency_ms, "Database unavailable"


async def check_redis_latency(redis_url: str) -> tuple[bool, float, str | None]:
    start = time.perf_counter()
    r = aioredis.from_url(redis_url, socket_timeout=1.0, socket_connect_timeout=1.0)
    try:
        async with asyncio.timeout(2):
            await r.ping()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return True, latency_ms, None
    except Exception:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return False, latency_ms, "Redis unavailable"
    finally:
        try:
            async with asyncio.timeout(0.2):
                await r.aclose()
        except Exception:
            pass
