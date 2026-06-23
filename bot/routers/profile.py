"""
Profile router.
"""

from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.database.mongo import users_col
from bot.keyboards.common import add_footer
from bot.utils.formatting import format_currency, format_datetime


router = Router(name="profile")

@router.callback_query(F.data == "profile")
async def profile_cb(callback_query: CallbackQuery):
    """Show the user profile page."""
    user_id = callback_query.from_user.id
    user = await users_col().find_one({"_id": user_id})
    
    if not user:
        await callback_query.answer("Profile not found.", show_alert=True)
        return
        
    username = user.get("username", "N/A")
    username_str = f"@{username}" if username != "N/A" else "None"
    
    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **My Profile**\n\n"
        f"User ID:           `{user_id}`\n"
        f"Username:          {username_str}\n"
        f"Balance:           {format_currency(user.get('balance', 0))}\n"
        f"Total Orders:      {user.get('total_orders', 0):,}\n"
        f"Completed Orders:  {user.get('completed_orders', 0):,}\n"
        f"Joined:            {format_datetime(user.get('joined_at'))}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    await callback_query.message.edit_text(text, reply_markup=add_footer([], "home"))
    await callback_query.answer()
