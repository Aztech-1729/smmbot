"""
Aiogram middlewares for Authentication and Rate Limiting.
"""

import logging
from datetime import datetime, timezone
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject, User

from bot.database.mongo import users_col, get_global_settings
from bot.config.settings import get_settings

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """
    Middleware to upsert user, check ban status, and check maintenance mode.
    Injects `user_data` into the handler's `data` dict.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user: User = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        user_id = user.id
        
        # Upsert user
        from pymongo import ReturnDocument
        doc = await users_col().find_one_and_update(
            {"_id": user_id},
            {
                "$set": {
                    "username": user.username or "",
                    "first_name": user.first_name or "",
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
            return_document=ReturnDocument.AFTER,
        )

        doc = doc or {}

        # Check banned
        if doc.get("is_banned"):
            if isinstance(event, Message):
                await event.answer("🚫 You are banned from using this bot.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 You are banned.", show_alert=True)
            return

        # Check maintenance
        settings = get_settings()
        if user_id not in settings.ADMIN_IDS:
            global_settings = await get_global_settings()
            if global_settings.get("maintenance_mode"):
                if isinstance(event, Message):
                    await event.answer("⚙️ Bot is currently in maintenance mode. Please check back later.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⚙️ Maintenance Mode", show_alert=True)
                return

        # Inject into data
        data["user_data"] = doc
        
        return await handler(event, data)


class AdminMiddleware(BaseMiddleware):
    """
    Middleware to ensure only admins can access certain routes.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user: User = data.get("event_from_user")
        if not user:
            return

        settings = get_settings()
        if user.id not in settings.ADMIN_IDS:
            if isinstance(event, Message):
                await event.answer("🚫 You are not authorized to use this.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Unauthorized", show_alert=True)
            return
            
        return await handler(event, data)
