"""
Order-related keyboards: categories, service lists, service detail, order confirmation, order detail.
"""

from __future__ import annotations

from typing import List, Dict, Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.common import back_home_close
from bot.utils.pagination import Paginator
from bot.utils.formatting import format_currency, truncate_text


# Category emoji mapping
CATEGORY_EMOJIS: Dict[str, str] = {
    "instagram": "📸",
    "youtube": "▶",
    "telegram": "📱",
    "tiktok": "🎵",
    "facebook": "🎯",
    "twitter": "📢",
    "x": "📢",
    "website": "🌐",
    "discord": "🎮",
    "spotify": "🎧",
    "twitch": "🎬",
    "linkedin": "💼",
    "pinterest": "📌",
    "reddit": "🔖",
    "snapchat": "👻",
    "threads": "🧵",
}


def get_category_emoji(category: str) -> str:
    """Get an emoji for a category based on keyword matching."""
    cat_lower = category.lower()
    for keyword, emoji in CATEGORY_EMOJIS.items():
        if keyword in cat_lower:
            return emoji
    return "📦"


def categories_keyboard(categories: List[str]) -> InlineKeyboardMarkup:
    """Build a grid of category buttons."""
    keyboard = []
    row = []
    for cat in sorted(categories):
        emoji = get_category_emoji(cat)
        btn = InlineKeyboardButton(
            text=f"{emoji} {truncate_text(cat, 20)}",
            callback_data=f"cat:{cat[:40]}",
            style="primary"
        )
        row.append(btn)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append(back_home_close("home"))
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def service_list_keyboard(
    services: List[Dict[str, Any]],
    category: str,
    page: int = 1,
    markup_percent: int = 50,
) -> tuple:
    """
    Build a paginated service list keyboard.
    Returns (text, InlineKeyboardMarkup).
    """
    paginator = Paginator(services, page=page, per_page=10)
    emoji = get_category_emoji(category)

    text_lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{emoji} {category}",
        f"Page {paginator.page} / {paginator.total_pages}",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    keyboard = []
    for svc in paginator.items:
        rate = float(svc.get("rate", 0))
        user_rate = rate * (1 + markup_percent / 100)
        name = svc.get("name", "Service")
        svc_id = svc.get("service", "0")
        btn_text = f"{truncate_text(name, 28)} — {format_currency(user_rate)}/1K"
        keyboard.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"svc:{svc_id}",
                style="primary"
            )
        ])

    # Pagination nav
    nav = paginator.get_nav_buttons(f"svcpg:{category[:30]}")
    if nav:
        keyboard.append(nav)

    keyboard.append(back_home_close("new_order"))
    text = "\n".join(text_lines)
    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)


def service_detail_keyboard(
    service: Dict[str, Any],
    markup_percent: int = 50,
    category: str = "",
    is_favorite: bool = False,
) -> tuple:
    """
    Build the service detail view.
    Returns (text, InlineKeyboardMarkup).
    """
    emoji = get_category_emoji(category or service.get("category", ""))
    name = service.get("name", "Service")
    rate = float(service.get("rate", 0))
    user_rate = rate * (1 + markup_percent / 100)
    min_qty = int(service.get("min", 0))
    max_qty = int(service.get("max", 0))
    svc_id = service.get("service", "0")
    svc_type = service.get("type", "Default")

    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{emoji} {name}\n\n"
        f"Category:   {category}\n"
        f"Type:       {svc_type}\n"
        f"Rate:       {format_currency(user_rate)} / 1000\n"
        f"Minimum:    {min_qty:,}\n"
        f"Maximum:    {max_qty:,}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    fav_text = "⭐ Remove Favorite" if is_favorite else "⭐ Add to Favorites"
    fav_data = f"unfav:{svc_id}" if is_favorite else f"fav:{svc_id}"

    keyboard = [
        [
            InlineKeyboardButton(text="Place Order", callback_data=f"place:{svc_id}", style="success"),
            InlineKeyboardButton(text=fav_text, callback_data=fav_data, style="primary"),
        ],
        back_home_close(f"cat:{category[:40]}"),
    ]

    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)


def order_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirm / Cancel buttons for order placement."""
    keyboard = [
        [
            InlineKeyboardButton(text="Confirm Order", callback_data="order_confirm", style="success"),
        ],
        [
            InlineKeyboardButton(text="Cancel", callback_data="order_cancel", style="danger"),
        ],
        back_home_close("new_order"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def order_detail_keyboard(
    order: dict,
    back_target: str = "my_orders:1",
) -> InlineKeyboardMarkup:
    """Build the order detail keyboard with refill/cancel if supported."""
    keyboard = []
    order_id = str(order.get("provider_order_id", ""))
    mongo_id = str(order.get("_id", ""))

    action_row = []
    status = order.get("status", "")
    if status not in ("Completed", "Cancelled"):
        if order.get("refill_supported"):
            action_row.append(
                InlineKeyboardButton(
                    text="Refill", callback_data=f"refill:{mongo_id}", style="primary"
                )
            )
        if order.get("cancel_supported") and status not in ("Completed", "Cancelled"):
            action_row.append(
                InlineKeyboardButton(
                    text="Cancel Order", callback_data=f"cancel_order:{mongo_id}", style="danger"
                )
            )
    if action_row:
        keyboard.append(action_row)

    keyboard.append([
        InlineKeyboardButton(text="🔄 Refresh", callback_data=f"refresh_order:{mongo_id}", style="primary"),
    ])
    keyboard.append(back_home_close(back_target))
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
