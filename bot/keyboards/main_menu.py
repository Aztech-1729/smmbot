"""
Main menu keyboard.
"""

from __future__ import annotations

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """
    Build the main menu inline keyboard.
    Admin users see an additional 👑 Admin Panel button.
    """
    keyboard = [
        [
            InlineKeyboardButton("🚀 New Order", callback_data="new_order"),
            InlineKeyboardButton("📦 My Orders", callback_data="my_orders:1"),
        ],
        [
            InlineKeyboardButton("📊 Track Order", callback_data="track_order"),
            InlineKeyboardButton("💰 Wallet", callback_data="wallet"),
        ],
        [
            InlineKeyboardButton("➕ Add Funds", callback_data="add_funds"),
            InlineKeyboardButton("⭐ Favorites", callback_data="favorites:1"),
        ],
        [
            InlineKeyboardButton("🔍 Search Service", callback_data="search"),
            InlineKeyboardButton("🎟 Support", callback_data="support"),
        ],
        [
            InlineKeyboardButton("👤 Profile", callback_data="profile"),
            InlineKeyboardButton("⚙ Settings", callback_data="user_settings"),
        ],
    ]

    if is_admin:
        keyboard.append([
            InlineKeyboardButton("👑 Admin Panel", callback_data="admin"),
        ])

    return InlineKeyboardMarkup(keyboard)
