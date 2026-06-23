"""
Start and home navigation router.
"""

from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery

from bot.database.mongo import get_global_settings
from bot.keyboards.main_menu import get_main_menu
from bot.middlewares.auth import upsert_user, check_banned, check_maintenance
from bot.middlewares.rate_limit import is_rate_limited, RATE_LIMIT_MESSAGE
from bot.middlewares.admin_guard import is_admin

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    """Handle /start command and display main menu."""
    user_id = message.from_user.id

    if await is_rate_limited(user_id):
        await message.reply_text(RATE_LIMIT_MESSAGE)
        return

    user_data = await upsert_user(client, message)
    if await check_banned(user_data):
        return

    settings = await get_global_settings()
    admin_status = is_admin(user_id)

    if await check_maintenance(user_data, client.me.id if not admin_status else []): # simplistic check, real check needs settings.ADMIN_IDS
        # A more robust check is done, passing admin list to check_maintenance
        from bot.config.settings import get_settings
        app_settings = get_settings()
        if await check_maintenance(user_data, app_settings.ADMIN_IDS):
            await message.reply_text("🚧 **Maintenance Mode**\n\nThe bot is currently undergoing maintenance. Please check back later.")
            return

    welcome_msg = settings.get("welcome_message", "Welcome!")
    kb = get_main_menu(is_admin=admin_status)

    await message.reply_text(welcome_msg, reply_markup=kb)


@Client.on_callback_query(filters.regex(r"^home$"))
async def home_cb(client: Client, callback_query: CallbackQuery):
    """Return to the main menu."""
    user_id = callback_query.from_user.id
    
    if await is_rate_limited(user_id):
        await callback_query.answer("Too many requests, slow down.", show_alert=True)
        return

    user_data = await upsert_user(client, callback_query)
    if await check_banned(user_data):
        await callback_query.answer("You are banned.", show_alert=True)
        return

    settings = await get_global_settings()
    admin_status = is_admin(user_id)
    
    from bot.config.settings import get_settings
    app_settings = get_settings()
    if await check_maintenance(user_data, app_settings.ADMIN_IDS):
        await callback_query.answer("Maintenance mode is active.", show_alert=True)
        return

    welcome_msg = settings.get("welcome_message", "Welcome!")
    kb = get_main_menu(is_admin=admin_status)

    try:
        await callback_query.edit_message_text(welcome_msg, reply_markup=kb)
    except Exception:
        # Message might be exactly the same
        pass
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^close$"))
async def close_cb(client: Client, callback_query: CallbackQuery):
    """Dismiss the message."""
    try:
        await callback_query.message.delete()
    except Exception:
        pass
    await callback_query.answer()
