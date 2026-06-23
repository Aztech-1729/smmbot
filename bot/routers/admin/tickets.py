"""
Admin tickets router.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message, InlineKeyboardButton

from bot.database.redis import get_wizard_state, set_wizard_state, clear_wizard_state
from bot.keyboards.common import add_footer
from bot.middlewares.admin_guard import is_admin
from bot.services.ticket_service import get_all_open_tickets, get_user_tickets, add_admin_reply
from bot.services.notification_service import notify_ticket_reply
from bot.models.ticket import get_ticket_badge
from bot.utils.formatting import format_datetime


@Client.on_callback_query(filters.regex(r"^adm_tickets:(\d+)$"))
async def adm_tickets_cb(client: Client, callback_query: CallbackQuery):
    """List all open tickets."""
    if not is_admin(callback_query.from_user.id):
        return
        
    page = int(callback_query.matches[0].group(1))
    tix, total = await get_all_open_tickets(page=page, per_page=10)
    
    if not tix:
        await callback_query.edit_message_text(
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
        
        # We reuse user's ticket view for simplicity, just change the back_target
        # Actually, let's make a dedicated admin view
        kb_rows.append([InlineKeyboardButton(btn_text, callback_data=f"adm_tview:{str(t['_id'])}:{page}")])

    nav = p.get_nav_buttons("adm_tickets")
    if nav:
        kb_rows.append(nav)
        
    await callback_query.edit_message_text(
        text,
        reply_markup=add_footer(kb_rows, "admin")
    )


# Also allow viewing tickets for a specific user
@Client.on_callback_query(filters.regex(r"^adm_utickets:(\d+):(\d+)$"))
async def adm_utickets_cb(client: Client, callback_query: CallbackQuery):
    """Admin view of a specific user's tickets."""
    if not is_admin(callback_query.from_user.id):
        return
        
    target_id = int(callback_query.matches[0].group(1))
    page = int(callback_query.matches[0].group(2))
    
    tix, total = await get_user_tickets(target_id, page=page, per_page=10)
    
    if not tix:
        await callback_query.edit_message_text(
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
        kb_rows.append([InlineKeyboardButton(btn_text, callback_data=f"adm_tview:{str(t['_id'])}:u{target_id}")])

    nav = p.get_nav_buttons(f"adm_utickets:{target_id}")
    if nav:
        kb_rows.append(nav)
        
    await callback_query.edit_message_text(
        text,
        reply_markup=add_footer(kb_rows, f"adm_usr:{target_id}")
    )


@Client.on_callback_query(filters.regex(r"^adm_tview:(.*):(.*)$"))
async def adm_tview_cb(client: Client, callback_query: CallbackQuery):
    """Admin ticket view."""
    if not is_admin(callback_query.from_user.id):
        return
        
    ticket_id = callback_query.matches[0].group(1)
    back_target_raw = callback_query.matches[0].group(2)
    
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
            InlineKeyboardButton("💬 Reply", callback_data=f"adm_treply:{ticket_id}"),
            InlineKeyboardButton("✖ Close Ticket", callback_data=f"close_ticket:{ticket_id}"), # Reuses user close logic
        ])
        
    await callback_query.edit_message_text(text, reply_markup=add_footer(kb, back_target))


@Client.on_callback_query(filters.regex(r"^adm_treply:(.*)$"))
async def adm_treply_cb(client: Client, callback_query: CallbackQuery):
    """Start admin reply wizard."""
    if not is_admin(callback_query.from_user.id):
        return
        
    ticket_id = callback_query.matches[0].group(1)
    
    await set_wizard_state(callback_query.from_user.id, {
        "flow": "adm_treply",
        "ticket_id": ticket_id,
        "msg_id": callback_query.message.id,
    })
    
    await callback_query.edit_message_text(
        "💬 **Admin Reply**\n\nPlease type your reply to the user:",
        reply_markup=add_footer([], f"adm_tview:{ticket_id}:1")
    )


@Client.on_message(filters.text & filters.private, group=4)
async def _adm_treply_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
        
    state = await get_wizard_state(user_id)
    if not state or state.get("flow") != "adm_treply":
        return
        
    reply_text = message.text.strip()
    ticket_id = state["ticket_id"]
    
    try:
        await message.delete()
    except Exception:
        pass
        
    await clear_wizard_state(user_id)
    
    ticket = await add_admin_reply(ticket_id, reply_text)
    if ticket:
        await notify_ticket_reply(client, ticket["user_id"], ticket)
        text = "✅ Reply sent and user notified."
    else:
        text = "❌ Failed to send reply."
        
    try:
        await client.edit_message_text(
            chat_id=user_id,
            message_id=state["msg_id"],
            text=text,
            reply_markup=add_footer([[InlineKeyboardButton("🔙 Back to Ticket", callback_data=f"adm_tview:{ticket_id}:1")]], "adm_tickets:1")
        )
    except Exception:
        pass
