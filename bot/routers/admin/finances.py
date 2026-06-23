"""
Admin finances router.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton

from bot.database.redis import get_wizard_state, set_wizard_state, clear_wizard_state
from bot.keyboards.admin_kb import admin_finance_keyboard
from bot.keyboards.common import add_footer
from bot.middlewares.admin_guard import is_admin
from bot.services.wallet_service import (
    get_all_transactions, get_deposits_by_status, approve_deposit, reject_deposit, get_deposit_by_id
)
from bot.services.notification_service import notify_deposit_approved, notify_deposit_rejected
from bot.utils.formatting import format_currency, format_datetime


@Client.on_callback_query(filters.regex(r"^adm_finances$"))
async def adm_finances_cb(client: Client, callback_query: CallbackQuery):
    """Show finances menu."""
    if not is_admin(callback_query.from_user.id):
        return
        
    await callback_query.edit_message_text(
        "💰 **Finance Management**\n\nSelect an option below:",
        reply_markup=admin_finance_keyboard()
    )


@Client.on_callback_query(filters.regex(r"^adm_deps:(Pending|Approved|Rejected):(\d+)$"))
async def adm_deposits_cb(client: Client, callback_query: CallbackQuery):
    """List deposits by status."""
    if not is_admin(callback_query.from_user.id):
        return
        
    status = callback_query.matches[0].group(1)
    page = int(callback_query.matches[0].group(2))
    
    deps, total = await get_deposits_by_status(status, page=page, per_page=10)
    
    if not deps:
        await callback_query.edit_message_text(
            f"No **{status}** deposits found.",
            reply_markup=add_footer([], "adm_finances")
        )
        return
        
    from bot.utils.pagination import Paginator
    p = Paginator(list(range(total)), page=page, per_page=10)
    
    text = f"📥 **{status} Deposits** (Page {page}/{p.total_pages})\n\n"
    
    kb_rows = []
    for d in deps:
        dt = format_datetime(d.get("created_at"))
        btn_text = f"[{d['user_id']}] {format_currency(d['amount'])} — {dt}"
        kb_rows.append([InlineKeyboardButton(btn_text, callback_data=f"adm_depview:{str(d['_id'])}")])

    nav = p.get_nav_buttons(f"adm_deps:{status}")
    if nav:
        kb_rows.append(nav)
        
    await callback_query.edit_message_text(
        text,
        reply_markup=add_footer(kb_rows, "adm_finances")
    )


@Client.on_callback_query(filters.regex(r"^adm_depview:(.*)$"))
async def adm_depview_cb(client: Client, callback_query: CallbackQuery):
    """View a single deposit to approve/reject."""
    if not is_admin(callback_query.from_user.id):
        return
        
    deposit_id = callback_query.matches[0].group(1)
    deposit = await get_deposit_by_id(deposit_id)
    
    if not deposit:
        await callback_query.answer("Deposit not found.", show_alert=True)
        return
        
    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 **Deposit Request**\n\n"
        f"User ID:   `{deposit['user_id']}`\n"
        f"Amount:    {format_currency(deposit['amount'])}\n"
        f"TXN ID:    `{deposit['transaction_id']}`\n"
        f"Status:    {deposit['status']}\n"
        f"Created:   {format_datetime(deposit['created_at'])}\n"
    )
    
    if deposit.get("reviewed_at"):
        text += f"Reviewed:  {format_datetime(deposit['reviewed_at'])}\n"
        if deposit.get("admin_note"):
            text += f"Note:      {deposit['admin_note']}\n"
            
    text += f"━━━━━━━━━━━━━━━━━━━━━━━━"
    
    kb = []
    if deposit['status'] == "Pending":
        from bot.keyboards.admin_kb import admin_deposit_keyboard
        kb = admin_deposit_keyboard(deposit_id).inline_keyboard
        
    # See if there's a photo to send. If so, we might want to send a new message with the photo.
    # For now, we just display the ID or send it as a reply.
    if deposit.get("screenshot_file_id"):
        text += "\n\n📷 **Screenshot attached.** (To view, use Telegram's file ID or handle it via a separate button)"
        # Simple approach: just show the file_id
        
    await callback_query.edit_message_text(
        text,
        reply_markup=add_footer(kb, f"adm_deps:{deposit['status']}:1")
    )


@Client.on_callback_query(filters.regex(r"^dep_approve:(.*)$"))
async def dep_approve_cb(client: Client, callback_query: CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        return
        
    deposit_id = callback_query.matches[0].group(1)
    deposit = await approve_deposit(deposit_id)
    
    if deposit:
        await callback_query.answer("Deposit approved! Balance credited.", show_alert=True)
        await notify_deposit_approved(client, deposit["user_id"], deposit)
        # Refresh
        callback_query.matches = [type("Match", (), {"group": lambda s, x: deposit_id})()]
        await adm_depview_cb(client, callback_query)
    else:
        await callback_query.answer("Failed to approve or already processed.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^dep_reject:(.*)$"))
async def dep_reject_cb(client: Client, callback_query: CallbackQuery):
    """Start rejection wizard to get a reason."""
    if not is_admin(callback_query.from_user.id):
        return
        
    deposit_id = callback_query.matches[0].group(1)
    
    await set_wizard_state(callback_query.from_user.id, {
        "flow": "adm_reject_dep",
        "deposit_id": deposit_id,
        "msg_id": callback_query.message.id,
    })
    
    await callback_query.edit_message_text(
        "❌ **Reject Deposit**\n\nPlease enter a reason for rejection:",
        reply_markup=add_footer([], f"adm_depview:{deposit_id}")
    )


from pyrogram.types import Message
@Client.on_message(filters.text & filters.private, group=3)
async def _adm_reject_dep_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
        
    state = await get_wizard_state(user_id)
    if not state or state.get("flow") != "adm_reject_dep":
        return
        
    reason = message.text.strip()
    deposit_id = state["deposit_id"]
    
    try:
        await message.delete()
    except Exception:
        pass
        
    await clear_wizard_state(user_id)
    
    deposit = await reject_deposit(deposit_id, admin_note=reason)
    if deposit:
        await notify_deposit_rejected(client, deposit["user_id"], deposit)
        text = f"✅ Deposit rejected.\nReason: {reason}"
    else:
        text = "❌ Failed to reject or already processed."
        
    try:
        await client.edit_message_text(
            chat_id=user_id,
            message_id=state["msg_id"],
            text=text,
            reply_markup=add_footer([[InlineKeyboardButton("🔙 Back to Deposit", callback_data=f"adm_depview:{deposit_id}")]], "adm_finances")
        )
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^adm_txns:(\d+)$"))
async def adm_txns_cb(client: Client, callback_query: CallbackQuery):
    """View all transactions."""
    if not is_admin(callback_query.from_user.id):
        return
        
    page = int(callback_query.matches[0].group(1))
    txns, total = await get_all_transactions(page=page, per_page=15)
    
    if not txns:
        await callback_query.edit_message_text(
            "No transactions found.",
            reply_markup=add_footer([], "adm_finances")
        )
        return
        
    from bot.utils.pagination import Paginator
    p = Paginator(list(range(total)), page=page, per_page=15)
    
    lines = [f"📜 **All Transactions** (Page {page}/{p.total_pages})\n"]
    for t in txns:
        amount = float(t.get("amount", 0))
        sign = "+" if amount >= 0 else ""
        icon = "🟢" if amount >= 0 else "🔴"
        dt = format_datetime(t.get("created_at"))
        
        lines.append(f"{icon} `[{t['user_id']}]` {sign}{format_currency(abs(amount))} — {t.get('type')}")
        lines.append(f"└ ⏱ {dt} | {t.get('description', '')[:20]}")
        
    text = "\n".join(lines)[:4000]
    
    kb_rows = []
    nav = p.get_nav_buttons("adm_txns")
    if nav:
        kb_rows.append(nav)
        
    await callback_query.edit_message_text(
        text,
        reply_markup=add_footer(kb_rows, "adm_finances")
    )


@Client.on_callback_query(filters.regex(r"^adm_revenue$"))
async def adm_revenue_cb(client: Client, callback_query: CallbackQuery):
    """Simple revenue report placeholder."""
    # Already computed totals in dashboard. This could be expanded to daily/weekly stats.
    # For now, we redirect to dashboard or show basic text.
    await callback_query.answer("Detailed revenue reports coming soon. View totals on Dashboard.", show_alert=True)
