"""
Support tickets router.
"""

from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.database.redis import get_wizard_state, set_wizard_state, clear_wizard_state
from bot.keyboards.common import add_footer
from bot.services.ticket_service import (
    create_ticket, get_user_tickets, get_ticket_by_id, add_user_message, close_ticket
)
from bot.services.notification_service import notify_new_ticket_to_admins
from bot.utils.formatting import format_datetime, SEPARATOR
from bot.utils.validators import sanitize_text

logger = logging.getLogger(__name__)


@Client.on_callback_query(filters.regex(r"^support$"))
async def support_cb(client: Client, callback_query: CallbackQuery):
    """Support menu."""
    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎟 **Support**\n\n"
        f"How can we help you today?\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    kb = [
        [InlineKeyboardButton("➕ Create New Ticket", callback_data="new_ticket")],
        [InlineKeyboardButton("📋 My Tickets", callback_data="my_tickets:1")],
    ]
    
    await callback_query.edit_message_text(text, reply_markup=add_footer(kb, "home"))
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^new_ticket$"))
async def new_ticket_cb(client: Client, callback_query: CallbackQuery):
    """Start the new ticket wizard."""
    user_id = callback_query.from_user.id
    
    await set_wizard_state(user_id, {
        "flow": "support",
        "step": "subject",
        "msg_id": callback_query.message.id,
    })
    
    await callback_query.edit_message_text(
        "📝 **New Ticket**\n\nPlease enter the **Subject** of your issue (e.g., 'Order not starting'):",
        reply_markup=add_footer([], "support")
    )
    await callback_query.answer()


async def _handle_support_wizard(client: Client, message: Message, state: dict):
    """Handle text input for the support wizard."""
    user_id = message.from_user.id
    step = state.get("step")
    
    try:
        await message.delete()
    except Exception:
        pass
        
    if step == "subject":
        subject = sanitize_text(message.text, 100)
        if not subject:
            return
            
        state["subject"] = subject
        state["step"] = "message"
        await set_wizard_state(user_id, state)
        
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=state["msg_id"],
                text=(
                    f"📝 **Subject**: {subject}\n\n"
                    "Now, please describe your issue in detail:"
                ),
                reply_markup=add_footer([], "support")
            )
        except Exception:
            pass
            
    elif step == "message":
        text = sanitize_text(message.text, 2000)
        if not text:
            return
            
        # Optional: Add to existing ticket if state says so
        if state.get("ticket_id"):
            ticket = await add_user_message(state["ticket_id"], text)
            await clear_wizard_state(user_id)
            if ticket:
                # Mock a callback to view ticket
                try:
                    await client.edit_message_text(
                        chat_id=user_id,
                        message_id=state["msg_id"],
                        text="✅ Reply sent.",
                        reply_markup=add_footer([], f"view_ticket:{state['ticket_id']}")
                    )
                except Exception:
                    pass
            return
            
        # Create new ticket
        ticket = await create_ticket(user_id, state["subject"], text)
        await clear_wizard_state(user_id)
        
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=state["msg_id"],
                text=(
                    f"✅ **Ticket Created!**\n\n"
                    f"We have received your message and will reply shortly."
                ),
                reply_markup=add_footer([], "support")
            )
        except Exception:
            pass
            
        await notify_new_ticket_to_admins(client, ticket)


@Client.on_callback_query(filters.regex(r"^my_tickets:(\d+)$"))
async def my_tickets_cb(client: Client, callback_query: CallbackQuery):
    """List user tickets."""
    user_id = callback_query.from_user.id
    page = int(callback_query.matches[0].group(1))
    
    tix, total = await get_user_tickets(user_id, page=page, per_page=10)
    
    if not tix:
        await callback_query.edit_message_text(
            "You don't have any support tickets.",
            reply_markup=add_footer([], "support")
        )
        return
        
    from bot.utils.pagination import Paginator
    from bot.models.ticket import get_ticket_badge
    
    p = Paginator(list(range(total)), page=page, per_page=10)
    text = f"🎟 **My Tickets** (Page {page}/{p.total_pages})\n\n"
    
    kb_rows = []
    for t in tix:
        badge = get_ticket_badge(t.get("status", ""))
        subj = t.get("subject", "No Subject")
        if len(subj) > 25:
            subj = subj[:24] + "…"
            
        btn_text = f"{badge} {subj}"
        kb_rows.append([InlineKeyboardButton(btn_text, callback_data=f"view_ticket:{str(t['_id'])}")])

    nav = p.get_nav_buttons("my_tickets")
    if nav:
        kb_rows.append(nav)
        
    await callback_query.edit_message_text(text, reply_markup=add_footer(kb_rows, "support"))


@Client.on_callback_query(filters.regex(r"^view_ticket:(.*)$"))
async def view_ticket_cb(client: Client, callback_query: CallbackQuery):
    """View a single ticket."""
    user_id = callback_query.from_user.id
    ticket_id = callback_query.matches[0].group(1)
    
    ticket = await get_ticket_by_id(ticket_id)
    if not ticket or ticket["user_id"] != user_id:
        await callback_query.answer("Ticket not found.", show_alert=True)
        return
        
    from bot.models.ticket import get_ticket_badge
    badge = get_ticket_badge(ticket.get("status", ""))
    
    lines = [
        f"━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🎟 **Ticket:** {ticket.get('subject')}",
        f"Status: {ticket.get('status')} {badge}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
    ]
    
    for m in ticket.get("messages", []):
        sender = "👤 **You**" if m.get("sender") == "user" else "🎧 **Support**"
        lines.append(f"{sender} - {format_datetime(m.get('sent_at'))}")
        lines.append(f"└ {m.get('text')}\n")
        
    # Telegram max length
    text = "\n".join(lines)[:4000]
    
    kb = []
    if ticket.get("status") != "Closed":
        kb.append([
            InlineKeyboardButton("💬 Reply", callback_data=f"reply_ticket:{ticket_id}"),
            InlineKeyboardButton("✖ Close Ticket", callback_data=f"close_ticket:{ticket_id}"),
        ])
        
    await callback_query.edit_message_text(text, reply_markup=add_footer(kb, "my_tickets:1"))


@Client.on_callback_query(filters.regex(r"^reply_ticket:(.*)$"))
async def reply_ticket_cb(client: Client, callback_query: CallbackQuery):
    """Start reply to ticket wizard."""
    user_id = callback_query.from_user.id
    ticket_id = callback_query.matches[0].group(1)
    
    ticket = await get_ticket_by_id(ticket_id)
    if not ticket or ticket["user_id"] != user_id:
        await callback_query.answer("Ticket not found.", show_alert=True)
        return
        
    await set_wizard_state(user_id, {
        "flow": "support",
        "step": "message",
        "ticket_id": ticket_id,
        "msg_id": callback_query.message.id,
    })
    
    await callback_query.edit_message_text(
        "💬 **Reply to Ticket**\n\nPlease type your message below:",
        reply_markup=add_footer([], f"view_ticket:{ticket_id}")
    )


@Client.on_callback_query(filters.regex(r"^close_ticket:(.*)$"))
async def close_ticket_cb(client: Client, callback_query: CallbackQuery):
    """Close a ticket."""
    user_id = callback_query.from_user.id
    ticket_id = callback_query.matches[0].group(1)
    
    ticket = await get_ticket_by_id(ticket_id)
    if not ticket or ticket["user_id"] != user_id:
        await callback_query.answer("Ticket not found.", show_alert=True)
        return
        
    await close_ticket(ticket_id)
    await callback_query.answer("Ticket closed.", show_alert=True)
    
    # Refresh view
    callback_query.matches = [type("Match", (), {"group": lambda s, x: ticket_id})()]
    await view_ticket_cb(client, callback_query)
