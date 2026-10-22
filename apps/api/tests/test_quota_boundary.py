import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
import redis.asyncio as aioredis
from app import rate_limit
from app.rate_limit import RateLimiter, InMemorySlidingWindow


@pytest.mark.asyncio
async def test_memory_limit_allows_exact_budget():
    limiter = InMemorySlidingWindow()
    assert (await limiter.check("fixture", 2, 60))[0] == 1
    assert (await limiter.check("fixture", 2, 60))[0] == 0
    assert (await limiter.check("fixture", 2, 60))[0] == -1


@pytest.mark.asyncio
async def test_production_does_not_fallback_to_per_instance_budget(monkeypatch):
    monkeypatch.setattr(rate_limit, "get_settings", lambda: SimpleNamespace(straz_env="production", is_production=True))
    redis = SimpleNamespace(eval=AsyncMock(side_effect=aioredis.RedisError("synthetic outage")))
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: redis)
    with pytest.raises(HTTPException) as exc:
        await RateLimiter(2, 60).check("fixture")
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_independent_instances_share_counter(monkeypatch):
    monkeypatch.setattr(rate_limit, "get_settings", lambda: SimpleNamespace(straz_env="production", is_production=True))
    count = 0
    async def evaluate(script, numkeys, key, window):
        nonlocal count
        assert "EXPIRE" in script and numkeys == 1
        count += 1
        return [count, window]
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: SimpleNamespace(eval=evaluate))
    first, second = RateLimiter(2, 60), RateLimiter(2, 60)
    await first.check("fixture"); await second.check("fixture")
    with pytest.raises(HTTPException) as exc:
        await first.check("fixture")
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_missing_or_untrusted_origin_rejected_in_production(client, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "settings", SimpleNamespace(is_production=True, cors_origins_list=["https://example.invalid"]))
    for headers in [{}, {"Origin": "https://attacker.invalid"}]:
        response = await client.post("/auth/logout", headers=headers)
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_real_redis_shared_budget_and_expiry(monkeypatch):
    import os
    import uuid
    from urllib.parse import urlsplit
    endpoint = os.environ.get("QUOTA_REDIS_URL")
    if not endpoint:
        pytest.skip("isolated Redis fixture is not configured")
    assert urlsplit(endpoint).hostname in ("127.0.0.1", "localhost")
    redis = aioredis.from_url(endpoint, decode_responses=True)
    key = "synthetic-" + uuid.uuid4().hex
    monkeypatch.setattr(rate_limit, "get_settings", lambda: SimpleNamespace(straz_env="production", is_production=True))
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: redis)
    try:
        await RateLimiter(1, 1).check(key)
        with pytest.raises(HTTPException) as exc:
            await RateLimiter(1, 1).check(key)
        assert exc.value.status_code == 429
        await asyncio.sleep(1.1)
        await RateLimiter(1, 1).check(key)
    finally:
        await redis.delete("straz:ratelimit:" + key)
        await redis.aclose()
