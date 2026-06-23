"""
Admin panel keyboards.
"""

from __future__ import annotations

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.common import back_home_close


def admin_main_keyboard() -> InlineKeyboardMarkup:
    """Admin panel main menu."""
    keyboard = [
        [
            InlineKeyboardButton("📊 Dashboard", callback_data="adm_dashboard"),
        ],
        [
            InlineKeyboardButton("👥 Users", callback_data="adm_users"),
            InlineKeyboardButton("📦 Orders", callback_data="adm_orders:1"),
        ],
        [
            InlineKeyboardButton("💰 Finances", callback_data="adm_finances"),
            InlineKeyboardButton("🎟 Tickets", callback_data="adm_tickets:1"),
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast"),
            InlineKeyboardButton("⚙ Settings", callback_data="adm_settings"),
        ],
        back_home_close("home"),
    ]
    return InlineKeyboardMarkup(keyboard)


def admin_deposit_keyboard(deposit_id: str) -> InlineKeyboardMarkup:
    """Approve / Reject buttons for a pending deposit."""
    keyboard = [
        [
            InlineKeyboardButton(
                "🟩 Approve", callback_data=f"dep_approve:{deposit_id}"
            ),
            InlineKeyboardButton(
                "🟥 Reject", callback_data=f"dep_reject:{deposit_id}"
            ),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def admin_user_actions_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Actions for viewing a specific user in admin."""
    keyboard = [
        [
            InlineKeyboardButton(
                "💰 Adjust Balance", callback_data=f"adm_adjust:{user_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                "🚫 Ban User", callback_data=f"adm_ban:{user_id}"
            ),
            InlineKeyboardButton(
                "✅ Unban User", callback_data=f"adm_unban:{user_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                "📦 User Orders", callback_data=f"adm_uorders:{user_id}:1"
            ),
            InlineKeyboardButton(
                "🎟 User Tickets", callback_data=f"adm_utickets:{user_id}:1"
            ),
        ],
        back_home_close("adm_users"),
    ]
    return InlineKeyboardMarkup(keyboard)


def admin_finance_keyboard() -> InlineKeyboardMarkup:
    """Finance management menu."""
    keyboard = [
        [
            InlineKeyboardButton(
                "📥 Pending Deposits", callback_data="adm_deps:Pending:1"
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Approved Deposits", callback_data="adm_deps:Approved:1"
            ),
            InlineKeyboardButton(
                "❌ Rejected Deposits", callback_data="adm_deps:Rejected:1"
            ),
        ],
        [
            InlineKeyboardButton(
                "📜 All Transactions", callback_data="adm_txns:1"
            ),
        ],
        [
            InlineKeyboardButton(
                "📈 Revenue Report", callback_data="adm_revenue"
            ),
        ],
        back_home_close("admin"),
    ]
    return InlineKeyboardMarkup(keyboard)


def admin_settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    """Admin settings menu with current values."""
    maint_icon = "🟢" if not settings.get("maintenance_mode") else "🔴"
    keyboard = [
        [
            InlineKeyboardButton(
                f"📊 Markup: {settings.get('markup_percent', 50)}%",
                callback_data="adm_set_markup",
            ),
        ],
        [
            InlineKeyboardButton(
                f"{maint_icon} Maintenance: {'ON' if settings.get('maintenance_mode') else 'OFF'}",
                callback_data="adm_toggle_maint",
            ),
        ],
        [
            InlineKeyboardButton(
                "📝 Welcome Message", callback_data="adm_set_welcome"
            ),
        ],
        [
            InlineKeyboardButton(
                "👤 Support Username", callback_data="adm_set_support"
            ),
        ],
        back_home_close("admin"),
    ]
    return InlineKeyboardMarkup(keyboard)


def broadcast_type_keyboard() -> InlineKeyboardMarkup:
    """Select broadcast content type."""
    keyboard = [
        [
            InlineKeyboardButton("📝 Text", callback_data="bcast_type:text"),
            InlineKeyboardButton("📷 Photo", callback_data="bcast_type:photo"),
        ],
        [
            InlineKeyboardButton("🎥 Video", callback_data="bcast_type:video"),
            InlineKeyboardButton("📄 Document", callback_data="bcast_type:document"),
        ],
        back_home_close("admin"),
    ]
    return InlineKeyboardMarkup(keyboard)
