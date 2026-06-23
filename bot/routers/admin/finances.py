"""
Admin finances router.
"""

from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.keyboards.admin_kb import admin_finance_keyboard
from bot.keyboards.common import add_footer
from bot.services.wallet_service import (
    get_all_transactions, get_deposits_by_status, approve_deposit, reject_deposit, get_deposit_by_id
)
from bot.services.notification_service import notify_deposit_approved, notify_deposit_rejected
from bot.utils.formatting import format_currency, format_datetime

router = Router(name="admin_finances")

class AdminRejectDepositWizard(StatesGroup):
    waiting_for_reason = State()


@router.callback_query(F.data == "adm_finances")
async def adm_finances_cb(callback_query: CallbackQuery, state: FSMContext):
    """Show finances menu."""
    await state.clear()
        
    await callback_query.message.edit_text(
        "💰 **Finance Management**\n\nSelect an option below:",
        reply_markup=admin_finance_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("adm_deps:"))
async def adm_deposits_cb(callback_query: CallbackQuery):
    """List deposits by status."""
    parts = callback_query.data.split(":")
    status = parts[1]
    page = int(parts[2])
    
    deps, total = await get_deposits_by_status(status, page=page, per_page=10)
    
    if not deps:
        await callback_query.message.edit_text(
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
        kb_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"adm_depview:{str(d['_id'])}", style="primary")])

    nav = p.get_nav_buttons(f"adm_deps:{status}")
    if nav:
        kb_rows.append(nav)
        
    await callback_query.message.edit_text(
        text,
        reply_markup=add_footer(kb_rows, "adm_finances")
    )


@router.callback_query(F.data.startswith("adm_depview:"))
async def adm_depview_cb(callback_query: CallbackQuery):
    """View a single deposit to approve/reject."""
    deposit_id = callback_query.data.split(":")[1]
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
        
    if deposit.get("screenshot_file_id"):
        text += "\n\n📷 **Screenshot attached.** (To view, use Telegram's file ID or handle it via a separate button)"
        
    await callback_query.message.edit_text(
        text,
        reply_markup=add_footer(kb, f"adm_deps:{deposit['status']}:1")
    )


@router.callback_query(F.data.startswith("dep_approve:"))
async def dep_approve_cb(callback_query: CallbackQuery):
    deposit_id = callback_query.data.split(":")[1]
    deposit = await approve_deposit(deposit_id)
    
    if deposit:
        await callback_query.answer("Deposit approved! Balance credited.", show_alert=True)
        await notify_deposit_approved(callback_query.bot, deposit["user_id"], deposit)
        await adm_depview_cb(callback_query)
    else:
        await callback_query.answer("Failed to approve or already processed.", show_alert=True)


@router.callback_query(F.data.startswith("dep_reject:"))
async def dep_reject_cb(callback_query: CallbackQuery, state: FSMContext):
    """Start rejection wizard to get a reason."""
    deposit_id = callback_query.data.split(":")[1]
    
    await state.set_state(AdminRejectDepositWizard.waiting_for_reason)
    await state.update_data(
        deposit_id=deposit_id,
        msg_id=callback_query.message.message_id,
    )
    
    await callback_query.message.edit_text(
        "❌ **Reject Deposit**\n\nPlease enter a reason for rejection:",
        reply_markup=add_footer([], f"adm_depview:{deposit_id}")
    )
    await callback_query.answer()


@router.message(AdminRejectDepositWizard.waiting_for_reason)
async def process_reject_reason(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
        
    reason = message.text.strip()
    deposit_id = data["deposit_id"]
    
    try:
        await message.delete()
    except Exception:
        pass
        
    await state.clear()
    
    deposit = await reject_deposit(deposit_id, admin_note=reason)
    if deposit:
        await notify_deposit_rejected(message.bot, deposit["user_id"], deposit)
        text = f"✅ Deposit rejected.\nReason: {reason}"
    else:
        text = "❌ Failed to reject or already processed."
        
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text=text,
            reply_markup=add_footer([[InlineKeyboardButton(text="🔙 Back to Deposit", callback_data=f"adm_depview:{deposit_id}", style="primary")]], "adm_finances")
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm_txns:"))
async def adm_txns_cb(callback_query: CallbackQuery):
    """View all transactions."""
    page = int(callback_query.data.split(":")[1])
    txns, total = await get_all_transactions(page=page, per_page=15)
    
    if not txns:
        await callback_query.message.edit_text(
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
        
    await callback_query.message.edit_text(
        text,
        reply_markup=add_footer(kb_rows, "adm_finances")
    )


@router.callback_query(F.data == "adm_revenue")
async def adm_revenue_cb(callback_query: CallbackQuery):
    """Simple revenue report placeholder."""
    await callback_query.answer("Detailed revenue reports coming soon. View totals on Dashboard.", show_alert=True)
