"""
Admin guard middleware — restricts access to admin-only operations.
"""

from __future__ import annotations

import logging

from bot.config.settings import get_settings

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """Check if a user ID is in the admin list."""
    settings = get_settings()
    return user_id in settings.ADMIN_IDS


ADMIN_DENIED_MESSAGE = "🚫 **Access Denied**\n\nThis area is restricted to administrators."
