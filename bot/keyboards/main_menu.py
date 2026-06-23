"""
Main menu keyboard.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """
    Build the main menu inline keyboard.
    Admin users see an additional 👑 Admin Panel button.
    """
    keyboard = [
        [
            InlineKeyboardButton(text="🚀 New Order", callback_data="new_order", style="success"),
            InlineKeyboardButton(text="📦 My Orders", callback_data="my_orders:1", style="primary"),
        ],
        [
            InlineKeyboardButton(text="📊 Track Order", callback_data="track_order", style="primary"),
            InlineKeyboardButton(text="💰 Wallet", callback_data="wallet", style="primary"),
        ],
        [
            InlineKeyboardButton(text="➕ Add Funds", callback_data="add_funds", style="success"),
            InlineKeyboardButton(text="⭐ Favorites", callback_data="favorites:1", style="primary"),
        ],
        [
            InlineKeyboardButton(text="🔍 Search Service", callback_data="search", style="primary"),
            InlineKeyboardButton(text="🎟 Support", callback_data="support", style="primary"),
        ],
        [
            InlineKeyboardButton(text="👤 Profile", callback_data="profile", style="primary"),
            InlineKeyboardButton(text="⚙ Settings", callback_data="user_settings", style="primary"),
        ],
    ]

    if is_admin:
        keyboard.append([
            InlineKeyboardButton(text="👑 Admin Panel", callback_data="admin", style="danger"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
