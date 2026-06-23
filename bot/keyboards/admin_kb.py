"""
Admin panel keyboards.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.common import back_home_close


def admin_main_keyboard() -> InlineKeyboardMarkup:
    """Admin panel main menu."""
    keyboard = [
        [
            InlineKeyboardButton(text="📊 Dashboard", callback_data="adm_dashboard", style="primary"),
        ],
        [
            InlineKeyboardButton(text="👥 Users", callback_data="adm_users", style="primary"),
            InlineKeyboardButton(text="📦 Orders", callback_data="adm_orders:1", style="primary"),
        ],
        [
            InlineKeyboardButton(text="💰 Finances", callback_data="adm_finances", style="primary"),
            InlineKeyboardButton(text="🎟 Tickets", callback_data="adm_tickets:1", style="primary"),
        ],
        [
            InlineKeyboardButton(text="📢 Broadcast", callback_data="adm_broadcast", style="primary"),
            InlineKeyboardButton(text="⚙ Settings", callback_data="adm_settings", style="primary"),
        ],
        back_home_close("home"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def admin_deposit_keyboard(deposit_id: str) -> InlineKeyboardMarkup:
    """Approve / Reject buttons for a pending deposit."""
    keyboard = [
        [
            InlineKeyboardButton(
                text="Approve", callback_data=f"dep_approve:{deposit_id}", style="success"
            ),
            InlineKeyboardButton(
                text="Reject", callback_data=f"dep_reject:{deposit_id}", style="danger"
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def admin_user_actions_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Actions for viewing a specific user in admin."""
    keyboard = [
        [
            InlineKeyboardButton(
                text="💰 Adjust Balance", callback_data=f"adm_adjust:{user_id}", style="primary"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🚫 Ban User", callback_data=f"adm_ban:{user_id}", style="danger"
            ),
            InlineKeyboardButton(
                text="✅ Unban User", callback_data=f"adm_unban:{user_id}", style="success"
            ),
        ],
        [
            InlineKeyboardButton(
                text="📦 User Orders", callback_data=f"adm_uorders:{user_id}:1", style="primary"
            ),
            InlineKeyboardButton(
                text="🎟 User Tickets", callback_data=f"adm_utickets:{user_id}:1", style="primary"
            ),
        ],
        back_home_close("adm_users"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def admin_finance_keyboard() -> InlineKeyboardMarkup:
    """Finance management menu."""
    keyboard = [
        [
            InlineKeyboardButton(
                text="📥 Pending Deposits", callback_data="adm_deps:Pending:1", style="primary"
            ),
        ],
        [
            InlineKeyboardButton(
                text="✅ Approved Deposits", callback_data="adm_deps:Approved:1", style="success"
            ),
            InlineKeyboardButton(
                text="❌ Rejected Deposits", callback_data="adm_deps:Rejected:1", style="danger"
            ),
        ],
        [
            InlineKeyboardButton(
                text="📜 All Transactions", callback_data="adm_txns:1", style="primary"
            ),
        ],
        [
            InlineKeyboardButton(
                text="📈 Revenue Report", callback_data="adm_revenue", style="primary"
            ),
        ],
        back_home_close("admin"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def admin_settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    """Admin settings menu with current values."""
    maint_icon = "🟢" if not settings.get("maintenance_mode") else "🔴"
    keyboard = [
        [
            InlineKeyboardButton(
                text=f"📊 Markup: {settings.get('markup_percent', 50)}%",
                callback_data="adm_set_markup",
                style="primary"
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"{maint_icon} Maintenance: {'ON' if settings.get('maintenance_mode') else 'OFF'}",
                callback_data="adm_toggle_maint",
                style="primary"
            ),
        ],
        [
            InlineKeyboardButton(
                text="📝 Welcome Message", callback_data="adm_set_welcome", style="primary"
            ),
        ],
        [
            InlineKeyboardButton(
                text="👤 Support Username", callback_data="adm_set_support", style="primary"
            ),
        ],
        back_home_close("admin"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def broadcast_type_keyboard() -> InlineKeyboardMarkup:
    """Select broadcast content type."""
    keyboard = [
        [
            InlineKeyboardButton(text="📝 Text", callback_data="bcast_type:text", style="primary"),
            InlineKeyboardButton(text="📷 Photo", callback_data="bcast_type:photo", style="primary"),
        ],
        [
            InlineKeyboardButton(text="🎥 Video", callback_data="bcast_type:video", style="primary"),
            InlineKeyboardButton(text="📄 Document", callback_data="bcast_type:document", style="primary"),
        ],
        back_home_close("admin"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
