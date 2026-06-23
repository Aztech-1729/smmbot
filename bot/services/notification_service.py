"""
Notification service — sends structured messages to users and admins.
"""

from __future__ import annotations

import logging
from typing import Optional

from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.config.settings import get_settings
from bot.database.mongo import users_col
from bot.utils.formatting import format_currency, format_datetime, SEPARATOR
from bot.keyboards.admin_kb import admin_deposit_keyboard

logger = logging.getLogger(__name__)


async def notify_user(
    client: Client,
    user_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    check_enabled: bool = True,
) -> bool:
    """
    Send a notification to a user.
    Respects notifications_enabled setting unless check_enabled=False.
    """
    if check_enabled:
        user = await users_col().find_one({"_id": user_id}, {"notifications_enabled": 1})
        if user and not user.get("notifications_enabled", True):
            return False

    try:
        await client.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
        )
        return True
    except Exception as e:
        logger.warning("Failed to notify user %d: %s", user_id, e)
        return False


async def notify_admins(
    client: Client,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """Send a notification to all admin users."""
    settings = get_settings()
    for admin_id in settings.ADMIN_IDS:
        try:
            await client.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=reply_markup,
            )
        except Exception as e:
            logger.warning("Failed to notify admin %d: %s", admin_id, e)


# ---------------------------------------------------------------------------
# Notification templates
# ---------------------------------------------------------------------------

async def notify_order_created(client: Client, user_id: int, order: dict) -> None:
    """Notify user about a new order."""
    text = (
        f"✅ **Order Placed Successfully!**\n\n"
        f"{SEPARATOR}\n"
        f"📦 Service: {order.get('service_name', 'N/A')}\n"
        f"🔢 Quantity: {order.get('quantity', 0):,}\n"
        f"🔗 URL: {order.get('url', 'N/A')}\n"
        f"💰 Cost: {format_currency(order.get('user_cost', 0))}\n"
        f"🆔 Order ID: `{order.get('provider_order_id', 'N/A')}`\n"
        f"{SEPARATOR}"
    )
    await notify_user(client, user_id, text)


async def notify_order_status_changed(
    client: Client,
    user_id: int,
    order: dict,
    old_status: str,
    new_status: str,
) -> None:
    """Notify user about an order status change."""
    from bot.models.order import get_status_badge

    badge = get_status_badge(new_status)
    text = (
        f"📦 **Order Status Update**\n\n"
        f"{SEPARATOR}\n"
        f"🆔 Order: `{order.get('provider_order_id', 'N/A')}`\n"
        f"📋 Service: {order.get('service_name', 'N/A')}\n"
        f"📊 Status: {old_status} → {badge} {new_status}\n"
        f"{SEPARATOR}"
    )
    await notify_user(client, user_id, text)


async def notify_deposit_approved(client: Client, user_id: int, deposit: dict) -> None:
    """Notify user that their deposit was approved."""
    text = (
        f"✅ **Deposit Approved!**\n\n"
        f"{SEPARATOR}\n"
        f"💰 Amount: {format_currency(deposit.get('amount', 0))}\n"
        f"🆔 TXN ID: `{deposit.get('transaction_id', 'N/A')}`\n\n"
        f"Your balance has been updated.\n"
        f"{SEPARATOR}"
    )
    await notify_user(client, user_id, text, check_enabled=False)


async def notify_deposit_rejected(
    client: Client,
    user_id: int,
    deposit: dict,
) -> None:
    """Notify user that their deposit was rejected."""
    note = deposit.get("admin_note", "No reason provided")
    text = (
        f"❌ **Deposit Rejected**\n\n"
        f"{SEPARATOR}\n"
        f"💰 Amount: {format_currency(deposit.get('amount', 0))}\n"
        f"🆔 TXN ID: `{deposit.get('transaction_id', 'N/A')}`\n"
        f"📝 Reason: {note}\n"
        f"{SEPARATOR}"
    )
    await notify_user(client, user_id, text, check_enabled=False)


async def notify_new_deposit_to_admins(client: Client, deposit: dict) -> None:
    """Notify all admins about a new deposit request."""
    user = await users_col().find_one({"_id": deposit["user_id"]})
    username = user.get("username", "N/A") if user else "N/A"
    deposit_id = str(deposit.get("_id", ""))

    text = (
        f"📥 **New Deposit Request**\n\n"
        f"{SEPARATOR}\n"
        f"👤 User: @{username} (ID: `{deposit['user_id']}`)\n"
        f"💰 Amount: {format_currency(deposit.get('amount', 0))}\n"
        f"🆔 TXN ID: `{deposit.get('transaction_id', 'N/A')}`\n"
        f"📷 Screenshot: {'Yes' if deposit.get('screenshot_file_id') else 'No'}\n"
        f"{SEPARATOR}"
    )

    kb = admin_deposit_keyboard(deposit_id)
    await notify_admins(client, text, reply_markup=kb)


async def notify_new_ticket_to_admins(client: Client, ticket: dict) -> None:
    """Notify all admins about a new support ticket."""
    user = await users_col().find_one({"_id": ticket["user_id"]})
    username = user.get("username", "N/A") if user else "N/A"
    ticket_id = str(ticket.get("_id", ""))

    messages = ticket.get("messages", [])
    first_msg = messages[0]["text"] if messages else "No message"

    text = (
        f"🎟 **New Support Ticket**\n\n"
        f"{SEPARATOR}\n"
        f"👤 User: @{username} (ID: `{ticket['user_id']}`)\n"
        f"📋 Subject: {ticket.get('subject', 'N/A')}\n"
        f"💬 Message: {first_msg[:200]}\n"
        f"{SEPARATOR}"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Reply", callback_data=f"adm_treply:{ticket_id}")],
    ])
    await notify_admins(client, text, reply_markup=kb)


async def notify_ticket_reply(client: Client, user_id: int, ticket: dict) -> None:
    """Notify user about an admin reply to their ticket. Always sent (ignores notification setting)."""
    messages = ticket.get("messages", [])
    last_msg = messages[-1]["text"] if messages else "No message"

    text = (
        f"💬 **Ticket Reply**\n\n"
        f"{SEPARATOR}\n"
        f"📋 Subject: {ticket.get('subject', 'N/A')}\n"
        f"💬 Reply: {last_msg[:500]}\n"
        f"{SEPARATOR}"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 View Ticket", callback_data=f"view_ticket:{str(ticket['_id'])}")],
    ])
    await notify_user(client, user_id, text, reply_markup=kb, check_enabled=False)
