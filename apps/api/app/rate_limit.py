from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, Request, Response, status
import redis.asyncio as aioredis

from app.config import get_settings


class InMemorySlidingWindow:
    """Fallback in-process rate limiter."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str, limit: int, window: int) -> tuple[int, int]:
        async with self._lock:
            now = time.monotonic()
            q = self._hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                remaining_ttl = int(window - (now - q[0])) if q else window
                return 0, max(1, remaining_ttl)
            q.append(now)
            remaining = limit - len(q)
            ttl = int(window - (now - q[0])) if q else window
            return remaining, max(1, ttl)


_in_memory_limiter = InMemorySlidingWindow()
_redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
    return _redis_client


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds

    async def check(
        self,
        key: str,
        response: Response | None = None,
        custom_limit: int | None = None,
        custom_window: int | None = None,
    ) -> None:
        limit = custom_limit or self.limit
        window = custom_window or self.window
        full_key = f"straz:ratelimit:{key}"

        remaining: int
        ttl: int

        try:
            r = get_redis_client()
            pipe = r.pipeline()
            pipe.incr(full_key)
            pipe.ttl(full_key)
            current_hits, current_ttl = await pipe.execute()

            if current_hits == 1 or current_ttl == -1:
                await r.expire(full_key, window)
                ttl = window
            else:
                ttl = max(1, current_ttl)

            if current_hits > limit:
                headers = {
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(ttl),
                    "Retry-After": str(ttl),
                }
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later.",
                    headers=headers,
                )

            remaining = max(0, limit - current_hits)

        except (aioredis.RedisError, OSError):
            # Fallback to in-memory limiter when Redis is unreachable (e.g. testing or local dev)
            rem, t = await _in_memory_limiter.check(full_key, limit, window)
            remaining, ttl = rem, t
            if remaining == 0 and rem == 0:
                # check if exceeded
                headers = {
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(ttl),
                    "Retry-After": str(ttl),
                }
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later.",
                    headers=headers,
                )

        if response is not None:
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(ttl)


login_limiter = RateLimiter(limit=10, window_seconds=60)
change_password_limiter = RateLimiter(limit=5, window_seconds=60)
run_limiter = RateLimiter(limit=30, window_seconds=60)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
