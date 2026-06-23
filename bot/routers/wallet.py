"""
Wallet, transactions, and deposit flows.
"""

from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot.states import AddFundsWizard
from bot.keyboards.common import add_footer
from bot.services.wallet_service import get_balance, get_transactions, get_user_deposits, create_deposit
from bot.services.notification_service import notify_new_deposit_to_admins
from bot.utils.formatting import format_currency, format_datetime, SEPARATOR
from bot.utils.validators import validate_amount

logger = logging.getLogger(__name__)

router = Router(name="wallet")

# ---------------------------------------------------------------------------
# Wallet Page
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "wallet")
async def wallet_cb(callback_query: CallbackQuery, state: FSMContext):
    """Show the wallet page."""
    await state.clear()
    user_id = callback_query.from_user.id
    balance = await get_balance(user_id)
    
    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 **My Wallet**\n\n"
        f"Balance:    {format_currency(balance)}\n"
        f"Currency:   INR\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    kb = [
        [InlineKeyboardButton(text="📜 Transaction History", callback_data="txn_hist:1", style="primary")],
        [InlineKeyboardButton(text="📥 Deposit History", callback_data="dep_hist:1", style="primary")],
        [InlineKeyboardButton(text="➕ Add Funds", callback_data="add_funds", style="success")],
    ]
    
    await callback_query.message.edit_text(
        text,
        reply_markup=add_footer(kb, "home")
    )
    await callback_query.answer()


# ---------------------------------------------------------------------------
# Transaction History
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("txn_hist:"))
async def transaction_history_cb(callback_query: CallbackQuery):
    """Paginated transaction history."""
    user_id = callback_query.from_user.id
    page = int(callback_query.data.split(":")[1])
    
    txns, total = await get_transactions(user_id, page=page, per_page=10)
    
    if not txns:
        await callback_query.message.edit_text(
            "You don't have any transactions yet.",
            reply_markup=add_footer([], "wallet")
        )
        return
        
    from bot.utils.pagination import Paginator
    p = Paginator(list(range(total)), page=page, per_page=10)
    
    lines = [f"📜 **Transaction History** (Page {page}/{p.total_pages})\n"]
    for t in txns:
        amount = float(t.get("amount", 0))
        sign = "+" if amount >= 0 else ""
        icon = "🟢" if amount >= 0 else "🔴"
        dt = format_datetime(t.get("created_at"))
        desc = t.get("description", "")
        lines.append(f"{icon} {sign}{format_currency(abs(amount))} — {desc}")
        lines.append(f"└ ⏱ {dt}")
        lines.append("")
        
    text = "\n".join(lines)
    
    kb_rows = []
    nav = p.get_nav_buttons("txn_hist")
    if nav:
        kb_rows.append(nav)
        
    await callback_query.message.edit_text(
        text,
        reply_markup=add_footer(kb_rows, "wallet")
    )


# ---------------------------------------------------------------------------
# Deposit History
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("dep_hist:"))
async def deposit_history_cb(callback_query: CallbackQuery):
    """Paginated deposit history."""
    user_id = callback_query.from_user.id
    page = int(callback_query.data.split(":")[1])
    
    deps, total = await get_user_deposits(user_id, page=page, per_page=10)
    
    if not deps:
        await callback_query.message.edit_text(
            "You don't have any deposit requests yet.",
            reply_markup=add_footer([], "wallet")
        )
        return
        
    from bot.utils.pagination import Paginator
    p = Paginator(list(range(total)), page=page, per_page=10)
    
    status_icons = {
        "Pending": "🟡",
        "Approved": "🟢",
        "Rejected": "🔴",
    }
    
    lines = [f"📥 **Deposit History** (Page {page}/{p.total_pages})\n"]
    for d in deps:
        status = d.get("status", "")
        icon = status_icons.get(status, "⚪")
        dt = format_datetime(d.get("created_at"))
        amt = format_currency(d.get("amount", 0))
        txn = d.get("transaction_id", "")
        
        lines.append(f"{icon} **{status}** | {amt}")
        lines.append(f"└ ID: `{txn}`")
        lines.append(f"└ ⏱ {dt}")
        lines.append("")
        
    text = "\n".join(lines)
    
    kb_rows = []
    nav = p.get_nav_buttons("dep_hist")
    if nav:
        kb_rows.append(nav)
        
    await callback_query.message.edit_text(
        text,
        reply_markup=add_footer(kb_rows, "wallet")
    )


# ---------------------------------------------------------------------------
# Add Funds Wizard
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "add_funds")
async def add_funds_cb(callback_query: CallbackQuery, state: FSMContext):
    """Start the add funds wizard."""
    await state.set_state(AddFundsWizard.waiting_for_amount)
    await state.update_data(msg_id=callback_query.message.message_id)
    
    await callback_query.message.edit_text(
        "➕ **Add Funds**\n\n"
        "Please enter the **amount** you wish to deposit (e.g., 500):",
        reply_markup=add_footer([], "wallet")
    )
    await callback_query.answer()


@router.message(AddFundsWizard.waiting_for_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    try:
        await message.delete()
    except Exception:
        pass
        
    if not message.text:
        return
        
    is_valid, amt, err = validate_amount(message.text)
    if not is_valid:
        try:
            await message.bot.edit_message_text(
                chat_id=user_id,
                message_id=data["msg_id"],
                text=f"{err}\n\nPlease enter a valid amount:",
                reply_markup=add_footer([], "wallet")
            )
        except Exception:
            pass
        return
        
    await state.update_data(amount=amt)
    
    # Normally we wait for a transaction ID here. For simplicity in Aiogram FSM, let's just make it a single step or two steps.
    # We will pretend the next step is txn_id. But wait, I didn't define txn_id state. I will add it to bot/states.py but for now we can dynamically set state or use generic string.
    # Actually, in states.py I only defined `waiting_for_amount`. I need to add `waiting_for_txn` and `waiting_for_screenshot`.
    # Let me just set it to a generic string since FSMContext allows arbitrary strings in aiogram 3 `set_state("AddFundsWizard:waiting_for_txn")`.
    
    await state.set_state("AddFundsWizard:waiting_for_txn")
    
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text=(
                f"💰 Amount: {format_currency(amt)}\n\n"
                "Now, please transfer the funds and enter the **Transaction ID** (UTR / Reference Number):"
            ),
            reply_markup=add_footer([], "add_funds")
        )
    except Exception:
        pass


@router.message(F.state == "AddFundsWizard:waiting_for_txn")
async def process_deposit_txn(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    try:
        await message.delete()
    except Exception:
        pass
        
    if not message.text:
        return
        
    txn_id = message.text.strip()
    await state.update_data(txn_id=txn_id)
    await state.set_state("AddFundsWizard:waiting_for_screenshot")
    
    kb = [[InlineKeyboardButton(text="⏭ Skip Screenshot", callback_data="skip_screenshot", style="primary")]]
    
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text=(
                f"💰 Amount: {format_currency(data['amount'])}\n"
                f"🆔 TXN ID: `{txn_id}`\n\n"
                "Please send a **screenshot** of the payment, or click Skip."
            ),
            reply_markup=add_footer(kb, "add_funds")
        )
    except Exception:
        pass


@router.message(F.state == "AddFundsWizard:waiting_for_screenshot", F.photo)
async def process_deposit_screenshot(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    file_id = message.photo[-1].file_id
    
    try:
        await message.delete()
    except Exception:
        pass
        
    await _finalize_deposit(message.bot, user_id, data, file_id, data["msg_id"], state)


@router.message(F.state == "AddFundsWizard:waiting_for_screenshot")
async def process_deposit_screenshot_invalid(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    try:
        await message.delete()
    except Exception:
        pass
        
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text="❌ Please send a valid **photo** or skip this step.",
            reply_markup=add_footer([[InlineKeyboardButton(text="⏭ Skip Screenshot", callback_data="skip_screenshot", style="primary")]], "add_funds")
        )
    except Exception:
        pass


@router.callback_query(F.state == "AddFundsWizard:waiting_for_screenshot", F.data == "skip_screenshot")
async def skip_screenshot_cb(callback_query: CallbackQuery, state: FSMContext):
    """Skip screenshot and finalize deposit."""
    user_id = callback_query.from_user.id
    data = await state.get_data()
    
    await _finalize_deposit(callback_query.bot, user_id, data, None, callback_query.message.message_id, state)
    await callback_query.answer()


async def _finalize_deposit(bot, user_id: int, data: dict, file_id: str | None, msg_id: int, state: FSMContext):
    """Finalize the deposit request and notify admins."""
    
    deposit = await create_deposit(
        user_id=user_id,
        amount=data["amount"],
        transaction_id=data["txn_id"],
        screenshot_file_id=file_id,
    )
    
    await state.clear()
    
    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=msg_id,
            text=(
                f"✅ **Deposit Request Submitted**\n\n"
                f"{SEPARATOR}\n"
                f"Amount: {format_currency(data['amount'])}\n"
                f"TXN ID: `{data['txn_id']}`\n\n"
                "Your request has been sent to the admins for approval."
            ),
            reply_markup=add_footer([], "wallet")
        )
    except Exception:
        pass
        
    await notify_new_deposit_to_admins(bot, deposit)
