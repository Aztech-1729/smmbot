"""
Redis async client with helpers for caching, wizard state, and rate limiting.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import orjson
import redis.asyncio as aioredis

from bot.config.settings import get_settings

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None


async def connect_redis() -> None:
    """Initialize the async Redis client with hiredis parser."""
    global _redis
    settings = get_settings()
    _redis = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=False,  # we handle bytes via orjson
    )
    # Test connectivity
    await _redis.ping()
    logger.info("Redis connected — url=%s", settings.REDIS_URL)


async def close_redis() -> None:
    """Close the Redis connection."""
    global _redis
    if _redis:
        await _redis.close()
        logger.info("Redis connection closed")


def get_redis() -> aioredis.Redis:
    """Return the Redis client. Must call connect_redis() first."""
    if _redis is None:
        raise RuntimeError("Redis not connected. Call connect_redis() first.")
    return _redis


# ---------------------------------------------------------------------------
# Generic cache helpers
# ---------------------------------------------------------------------------

async def get_cached(key: str) -> Optional[Any]:
    """Get a cached value deserialized from JSON."""
    r = get_redis()
    data = await r.get(key)
    if data is None:
        return None
    return orjson.loads(data)


async def set_cached(key: str, value: Any, ttl: int = 300) -> None:
    """Set a cached value serialized to JSON with TTL in seconds."""
    r = get_redis()
    await r.set(key, orjson.dumps(value), ex=ttl)


async def delete_cached(key: str) -> None:
    """Delete a cached value."""
    r = get_redis()
    await r.delete(key)


# ---------------------------------------------------------------------------
# Wizard state helpers (order creation, deposit flow)
# ---------------------------------------------------------------------------

WIZARD_TTL = 1800  # 30 minutes


async def get_wizard_state(user_id: int) -> Optional[dict]:
    """Retrieve the wizard state for a user."""
    return await get_cached(f"wizard:{user_id}")


async def set_wizard_state(user_id: int, state: dict) -> None:
    """Store the wizard state for a user."""
    await set_cached(f"wizard:{user_id}", state, ttl=WIZARD_TTL)


async def clear_wizard_state(user_id: int) -> None:
    """Clear the wizard state for a user."""
    await delete_cached(f"wizard:{user_id}")


# ---------------------------------------------------------------------------
# Rate limiting helper
# ---------------------------------------------------------------------------

async def check_rate_limit(
    user_id: int,
    max_requests: int = 30,
    window_seconds: int = 60,
) -> bool:
    """
    Sliding window rate limiter.
    Returns True if the user is within limits, False if rate-limited.
    """
    r = get_redis()
    key = f"rate:{user_id}"
    import time
    now = time.time()

    pipe = r.pipeline()
    # Remove entries outside the window
    pipe.zremrangebyscore(key, 0, now - window_seconds)
    # Add current request
    pipe.zadd(key, {str(now): now})
    # Count requests in window
    pipe.zcard(key)
    # Set expiry on the key
    pipe.expire(key, window_seconds)
    results = await pipe.execute()

    request_count = results[2]
    return request_count <= max_requests
