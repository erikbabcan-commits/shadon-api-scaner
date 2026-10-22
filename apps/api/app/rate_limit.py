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
                return -1, max(1, remaining_ttl)
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

        settings = get_settings()
        if settings.straz_env in ("test", "testing"):
            rem, t = await _in_memory_limiter.check(full_key, limit, window)
            remaining, ttl = rem, t
            if remaining < 0:
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
            return

        remaining: int
        ttl: int

        try:
            r = get_redis_client()
            # Atomic counter + expiry: no worker can leave an unbounded counter
            # between INCR and EXPIRE, and all instances share the same budget.
            current_hits, ttl = await r.eval(
                "local hits = redis.call('INCR', KEYS[1]); "
                "local ttl = redis.call('TTL', KEYS[1]); "
                "if ttl < 0 then redis.call('EXPIRE', KEYS[1], ARGV[1]); ttl = tonumber(ARGV[1]); end; "
                "return {hits, ttl}",
                1, full_key, window,
            )
            ttl = max(1, int(ttl))

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
            if settings.is_production:
                # Local fallback would multiply the allowance by instance count.
                raise HTTPException(status_code=503, detail="Rate limiter unavailable") from None
            # Fallback to in-memory limiter when Redis is unreachable (e.g. testing or local dev)
            rem, t = await _in_memory_limiter.check(full_key, limit, window)
            remaining, ttl = rem, t
            if remaining < 0:
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
