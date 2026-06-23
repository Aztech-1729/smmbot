"""
Admin tickets router.
"""

from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.keyboards.common import add_footer
from bot.services.ticket_service import get_all_open_tickets, get_user_tickets, add_admin_reply
from bot.services.notification_service import notify_ticket_reply
from bot.models.ticket import get_ticket_badge
from bot.utils.formatting import format_datetime


router = Router(name="admin_tickets")

class AdminTicketReplyWizard(StatesGroup):
    waiting_for_reply = State()


@router.callback_query(F.data.startswith("adm_tickets:"))
async def adm_tickets_cb(callback_query: CallbackQuery):
    """List all open tickets."""
    page = int(callback_query.data.split(":")[1])
    tix, total = await get_all_open_tickets(page=page, per_page=10)
    
    if not tix:
        await callback_query.message.edit_text(
            "🎉 No open tickets!",
            reply_markup=add_footer([], "admin")
        )
        return
        
    from bot.utils.pagination import Paginator
    p = Paginator(list(range(total)), page=page, per_page=10)
    
    text = f"🎟 **Open Tickets** (Page {page}/{p.total_pages})\n\n"
    
    kb_rows = []
    for t in tix:
        badge = get_ticket_badge(t.get("status", ""))
        subj = t.get("subject", "No Subject")[:20]
        btn_text = f"{badge} [{t['user_id']}] {subj}"
        
        kb_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"adm_tview:{str(t['_id'])}:{page}", style="primary")])

    nav = p.get_nav_buttons("adm_tickets")
    if nav:
        kb_rows.append(nav)
        
    await callback_query.message.edit_text(
        text,
        reply_markup=add_footer(kb_rows, "admin")
    )


@router.callback_query(F.data.startswith("adm_utickets:"))
async def adm_utickets_cb(callback_query: CallbackQuery):
    """Admin view of a specific user's tickets."""
    parts = callback_query.data.split(":")
    target_id = int(parts[1])
    page = int(parts[2])
    
    tix, total = await get_user_tickets(target_id, page=page, per_page=10)
    
    if not tix:
        await callback_query.message.edit_text(
            f"User `{target_id}` has no tickets.",
            reply_markup=add_footer([], f"adm_usr:{target_id}")
        )
        return
        
    from bot.utils.pagination import Paginator
    p = Paginator(list(range(total)), page=page, per_page=10)
    
    text = f"🎟 **Tickets for {target_id}** (Page {page}/{p.total_pages})\n\n"
    
    kb_rows = []
    for t in tix:
        badge = get_ticket_badge(t.get("status", ""))
        subj = t.get("subject", "No Subject")[:20]
        btn_text = f"{badge} {subj}"
        kb_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"adm_tview:{str(t['_id'])}:u{target_id}", style="primary")])

    nav = p.get_nav_buttons(f"adm_utickets:{target_id}")
    if nav:
        kb_rows.append(nav)
        
    await callback_query.message.edit_text(
        text,
        reply_markup=add_footer(kb_rows, f"adm_usr:{target_id}")
    )


@router.callback_query(F.data.startswith("adm_tview:"))
async def adm_tview_cb(callback_query: CallbackQuery):
    """Admin ticket view."""
    parts = callback_query.data.split(":")
    ticket_id = parts[1]
    back_target_raw = parts[2]
    
    if back_target_raw.startswith("u"):
        back_target = f"adm_utickets:{back_target_raw[1:]}:1"
    else:
        back_target = f"adm_tickets:{back_target_raw}"
        
    from bot.services.ticket_service import get_ticket_by_id
    ticket = await get_ticket_by_id(ticket_id)
    
    if not ticket:
        await callback_query.answer("Ticket not found.", show_alert=True)
        return
        
    badge = get_ticket_badge(ticket.get("status", ""))
    
    lines = [
        f"━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🎟 **Ticket:** {ticket.get('subject')}",
        f"User: `{ticket['user_id']}`",
        f"Status: {ticket.get('status')} {badge}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
    ]
    
    for m in ticket.get("messages", []):
        sender = f"👤 **User**" if m.get("sender") == "user" else "🎧 **Admin**"
        lines.append(f"{sender} - {format_datetime(m.get('sent_at'))}")
        lines.append(f"└ {m.get('text')}\n")
        
    text = "\n".join(lines)[:4000]
    
    kb = []
    if ticket.get("status") != "Closed":
        kb.append([
            InlineKeyboardButton(text="💬 Reply", callback_data=f"adm_treply:{ticket_id}", style="primary"),
            InlineKeyboardButton(text="✖ Close Ticket", callback_data=f"close_ticket:{ticket_id}", style="danger"), 
        ])
        
    await callback_query.message.edit_text(text, reply_markup=add_footer(kb, back_target))


@router.callback_query(F.data.startswith("adm_treply:"))
async def adm_treply_cb(callback_query: CallbackQuery, state: FSMContext):
    """Start admin reply wizard."""
    ticket_id = callback_query.data.split(":")[1]
    
    await state.set_state(AdminTicketReplyWizard.waiting_for_reply)
    await state.update_data(
        ticket_id=ticket_id,
        msg_id=callback_query.message.message_id,
    )
    
    await callback_query.message.edit_text(
        "💬 **Admin Reply**\n\nPlease type your reply to the user:",
        reply_markup=add_footer([], f"adm_tview:{ticket_id}:1")
    )
    await callback_query.answer()


@router.message(AdminTicketReplyWizard.waiting_for_reply)
async def process_admin_reply(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
        
    reply_text = message.text.strip()
    ticket_id = data["ticket_id"]
    
    try:
        await message.delete()
    except Exception:
        pass
        
    await state.clear()
    
    ticket = await add_admin_reply(ticket_id, reply_text)
    if ticket:
        await notify_ticket_reply(message.bot, ticket["user_id"], ticket)
        text = "✅ Reply sent and user notified."
    else:
        text = "❌ Failed to send reply."
        
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text=text,
            reply_markup=add_footer([[InlineKeyboardButton(text="🔙 Back to Ticket", callback_data=f"adm_tview:{ticket_id}:1", style="primary")]], "adm_tickets:1")
        )
    except Exception:
        pass
