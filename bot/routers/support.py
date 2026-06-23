"""
Support tickets router.
"""

from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot.states import TicketWizard
from bot.keyboards.common import add_footer
from bot.services.ticket_service import (
    create_ticket, get_user_tickets, get_ticket_by_id, add_user_message, close_ticket
)
from bot.services.notification_service import notify_new_ticket_to_admins
from bot.utils.formatting import format_datetime
from bot.utils.validators import sanitize_text

logger = logging.getLogger(__name__)

router = Router(name="support")

@router.callback_query(F.data == "support")
async def support_cb(callback_query: CallbackQuery, state: FSMContext):
    """Support menu."""
    await state.clear()
    text = (
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎟 **Support**\n\n"
        "How can we help you today?\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    kb = [
        [InlineKeyboardButton(text="➕ Create New Ticket", callback_data="new_ticket", style="primary")],
        [InlineKeyboardButton(text="📋 My Tickets", callback_data="my_tickets:1", style="primary")],
    ]
    
    await callback_query.message.edit_text(text, reply_markup=add_footer(kb, "home"))
    await callback_query.answer()


@router.callback_query(F.data == "new_ticket")
async def new_ticket_cb(callback_query: CallbackQuery, state: FSMContext):
    """Start the new ticket wizard."""
    await state.set_state(TicketWizard.waiting_for_subject)
    await state.update_data(msg_id=callback_query.message.message_id)
    
    await callback_query.message.edit_text(
        "📝 **New Ticket**\n\nPlease enter the **Subject** of your issue (e.g., 'Order not starting'):",
        reply_markup=add_footer([], "support")
    )
    await callback_query.answer()


@router.message(TicketWizard.waiting_for_subject)
async def process_ticket_subject(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    try:
        await message.delete()
    except Exception:
        pass
        
    subject = sanitize_text(message.text, 100)
    if not subject:
        return
        
    await state.update_data(subject=subject)
    await state.set_state(TicketWizard.waiting_for_message)
    
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text=(
                f"📝 **Subject**: {subject}\n\n"
                "Now, please describe your issue in detail:"
            ),
            reply_markup=add_footer([], "support")
        )
    except Exception:
        pass


@router.message(TicketWizard.waiting_for_message)
async def process_ticket_message(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    try:
        await message.delete()
    except Exception:
        pass
        
    text = sanitize_text(message.text, 2000)
    if not text:
        return
        
    # Optional: Add to existing ticket if state says so (from reply_ticket)
    if data.get("ticket_id"):
        ticket = await add_user_message(data["ticket_id"], text)
        await state.clear()
        if ticket:
            try:
                await message.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=data["msg_id"],
                    text="✅ Reply sent.",
                    reply_markup=add_footer([], f"view_ticket:{data['ticket_id']}")
                )
            except Exception:
                pass
        return
        
    # Create new ticket
    ticket = await create_ticket(user_id, data["subject"], text)
    await state.clear()
    
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text=(
                "✅ **Ticket Created!**\n\n"
                "We have received your message and will reply shortly."
            ),
            reply_markup=add_footer([], "support")
        )
    except Exception:
        pass
        
    await notify_new_ticket_to_admins(message.bot, ticket)


@router.callback_query(F.data.startswith("my_tickets:"))
async def my_tickets_cb(callback_query: CallbackQuery):
    """List user tickets."""
    user_id = callback_query.from_user.id
    page = int(callback_query.data.split(":")[1])
    
    tix, total = await get_user_tickets(user_id, page=page, per_page=10)
    
    if not tix:
        await callback_query.message.edit_text(
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
        kb_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"view_ticket:{str(t['_id'])}", style="primary")])

    nav = p.get_nav_buttons("my_tickets")
    if nav:
        kb_rows.append(nav)
        
    await callback_query.message.edit_text(text, reply_markup=add_footer(kb_rows, "support"))


@router.callback_query(F.data.startswith("view_ticket:"))
async def view_ticket_cb(callback_query: CallbackQuery):
    """View a single ticket."""
    user_id = callback_query.from_user.id
    ticket_id = callback_query.data.split(":")[1]
    
    ticket = await get_ticket_by_id(ticket_id)
    if not ticket or ticket["user_id"] != user_id:
        await callback_query.answer("Ticket not found.", show_alert=True)
        return
        
    from bot.models.ticket import get_ticket_badge
    badge = get_ticket_badge(ticket.get("status", ""))
    
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🎟 **Ticket:** {ticket.get('subject')}",
        f"Status: {ticket.get('status')} {badge}",
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
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
            InlineKeyboardButton(text="💬 Reply", callback_data=f"reply_ticket:{ticket_id}", style="primary"),
            InlineKeyboardButton(text="✖ Close Ticket", callback_data=f"close_ticket:{ticket_id}", style="danger"),
        ])
        
    await callback_query.message.edit_text(text, reply_markup=add_footer(kb, "my_tickets:1"))


@router.callback_query(F.data.startswith("reply_ticket:"))
async def reply_ticket_cb(callback_query: CallbackQuery, state: FSMContext):
    """Start reply to ticket wizard."""
    user_id = callback_query.from_user.id
    ticket_id = callback_query.data.split(":")[1]
    
    ticket = await get_ticket_by_id(ticket_id)
    if not ticket or ticket["user_id"] != user_id:
        await callback_query.answer("Ticket not found.", show_alert=True)
        return
        
    await state.set_state(TicketWizard.waiting_for_message)
    await state.update_data(
        ticket_id=ticket_id,
        msg_id=callback_query.message.message_id,
    )
    
    await callback_query.message.edit_text(
        "💬 **Reply to Ticket**\n\nPlease type your message below:",
        reply_markup=add_footer([], f"view_ticket:{ticket_id}")
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("close_ticket:"))
async def close_ticket_cb(callback_query: CallbackQuery):
    """Close a ticket."""
    user_id = callback_query.from_user.id
    ticket_id = callback_query.data.split(":")[1]
    
    ticket = await get_ticket_by_id(ticket_id)
    if not ticket or ticket["user_id"] != user_id:
        await callback_query.answer("Ticket not found.", show_alert=True)
        return
        
    await close_ticket(ticket_id)
    await callback_query.answer("Ticket closed.", show_alert=True)
    
    # Refresh view
    await view_ticket_cb(callback_query)
