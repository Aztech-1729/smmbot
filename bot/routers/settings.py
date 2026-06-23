"""
User settings router.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.mongo import users_col
from bot.keyboards.common import add_footer
from bot.utils.formatting import SEPARATOR


@Client.on_callback_query(filters.regex(r"^user_settings$"))
async def user_settings_cb(client: Client, callback_query: CallbackQuery):
    """Show user settings page."""
    user_id = callback_query.from_user.id
    user = await users_col().find_one({"_id": user_id})
    
    if not user:
        return
        
    notif = user.get("notifications_enabled", True)
    notif_icon = "🟢" if notif else "🔴"
    
    # For now currency is fixed to INR in the system logic based on markup
    # but we display it here for completeness
    
    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚙ **Settings**\n\n"
        f"Customize your experience.\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    kb = [
        [InlineKeyboardButton(f"{notif_icon} Order Notifications", callback_data="toggle_notif")],
        [InlineKeyboardButton("🌍 Language: English", callback_data="noop")],
        [InlineKeyboardButton("💱 Currency: INR", callback_data="noop")],
    ]
    
    await callback_query.edit_message_text(text, reply_markup=add_footer(kb, "home"))
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^toggle_notif$"))
async def toggle_notif_cb(client: Client, callback_query: CallbackQuery):
    """Toggle order notifications."""
    user_id = callback_query.from_user.id
    user = await users_col().find_one({"_id": user_id})
    
    if not user:
        return
        
    current = user.get("notifications_enabled", True)
    await users_col().update_one({"_id": user_id}, {"$set": {"notifications_enabled": not current}})
    
    await callback_query.answer("Notification settings updated.")
    await user_settings_cb(client, callback_query)
