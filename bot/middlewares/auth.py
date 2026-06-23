"""
Authentication middleware — upserts user on every interaction.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pyrogram import Client
from pyrogram.types import Message, CallbackQuery

from bot.database.mongo import users_col

logger = logging.getLogger(__name__)


async def upsert_user(client: Client, update) -> dict:
    """
    Ensure the user exists in the database.
    Updates username/first_name on every interaction.
    Returns the user document.
    """
    if isinstance(update, Message):
        user = update.from_user
    elif isinstance(update, CallbackQuery):
        user = update.from_user
    else:
        return {}

    if not user:
        return {}

    user_id = user.id
    username = user.username or ""
    first_name = user.first_name or ""

    doc = await users_col().find_one_and_update(
        {"_id": user_id},
        {
            "$set": {
                "username": username,
                "first_name": first_name,
            },
            "$setOnInsert": {
                "_id": user_id,
                "balance": 0.00,
                "currency": "INR",
                "language": "en",
                "notifications_enabled": True,
                "total_orders": 0,
                "completed_orders": 0,
                "is_banned": False,
                "joined_at": datetime.now(timezone.utc),
            },
        },
        upsert=True,
        return_document=True,
    )

    return doc or {}


async def check_banned(user_data: dict) -> bool:
    """Check if a user is banned."""
    return user_data.get("is_banned", False)


async def check_maintenance(user_data: dict, admin_ids: list) -> bool:
    """
    Check if maintenance mode is active.
    Admins bypass maintenance mode.
    """
    from bot.database.mongo import get_global_settings

    user_id = user_data.get("_id", 0)
    if user_id in admin_ids:
        return False

    settings = await get_global_settings()
    return settings.get("maintenance_mode", False)
