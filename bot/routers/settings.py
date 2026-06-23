"""
User settings router.
"""

from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton

from bot.database.mongo import users_col
from bot.keyboards.common import add_footer


router = Router(name="settings")

@router.callback_query(F.data == "user_settings")
async def user_settings_cb(callback_query: CallbackQuery):
    """Show user settings page."""
    user_id = callback_query.from_user.id
    user = await users_col().find_one({"_id": user_id})
    
    if not user:
        return
        
    notif = user.get("notifications_enabled", True)
    notif_icon = "🟢" if notif else "🔴"
    
    text = (
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚙ **Settings**\n\n"
        "Customize your experience.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    kb = [
        [InlineKeyboardButton(text=f"{notif_icon} Order Notifications", callback_data="toggle_notif")],
        [InlineKeyboardButton(text="🌍 Language: English", callback_data="noop")],
        [InlineKeyboardButton(text="💱 Currency: INR", callback_data="noop")],
    ]
    
    await callback_query.message.edit_text(text, reply_markup=add_footer(kb, "home"))
    await callback_query.answer()


@router.callback_query(F.data == "toggle_notif")
async def toggle_notif_cb(callback_query: CallbackQuery):
    """Toggle order notifications."""
    user_id = callback_query.from_user.id
    user = await users_col().find_one({"_id": user_id})
    
    if not user:
        return
        
    current = user.get("notifications_enabled", True)
    await users_col().update_one({"_id": user_id}, {"$set": {"notifications_enabled": not current}})
    
    await callback_query.answer("Notification settings updated.")
    await user_settings_cb(callback_query)

@router.callback_query(F.data == "noop")
async def noop_cb(callback_query: CallbackQuery):
    """Ignore clicks on display buttons."""
    await callback_query.answer()
