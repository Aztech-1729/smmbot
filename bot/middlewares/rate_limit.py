"""
Redis-backed rate limiting middleware.
"""

from __future__ import annotations

import logging

from bot.database.redis import check_rate_limit

logger = logging.getLogger(__name__)


async def is_rate_limited(user_id: int) -> bool:
    """
    Check if a user has exceeded the rate limit.
    Returns True if the user should be throttled.
    """
    allowed = await check_rate_limit(
        user_id=user_id,
        max_requests=30,
        window_seconds=60,
    )
    if not allowed:
        logger.warning("Rate limit exceeded for user %d", user_id)
    return not allowed


RATE_LIMIT_MESSAGE = (
    "⚠️ **Slow down!**\n\n"
    "You're sending requests too quickly.\n"
    "Please wait a moment before trying again."
)
