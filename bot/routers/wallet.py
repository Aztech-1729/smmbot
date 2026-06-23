"""
Wallet, transactions, and deposit flows.
"""

from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.database.redis import get_wizard_state, set_wizard_state, clear_wizard_state
from bot.keyboards.common import add_footer
from bot.services.wallet_service import get_balance, get_transactions, get_user_deposits, create_deposit
from bot.services.notification_service import notify_new_deposit_to_admins
from bot.utils.formatting import format_currency, format_datetime, SEPARATOR
from bot.utils.validators import validate_amount

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wallet Page
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex(r"^wallet$"))
async def wallet_cb(client: Client, callback_query: CallbackQuery):
    """Show the wallet page."""
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
        [InlineKeyboardButton("📜 Transaction History", callback_data="txn_hist:1")],
        [InlineKeyboardButton("📥 Deposit History", callback_data="dep_hist:1")],
        [InlineKeyboardButton("➕ Add Funds", callback_data="add_funds")],
    ]
    
    await callback_query.edit_message_text(
        text,
        reply_markup=add_footer(kb, "home")
    )
    await callback_query.answer()


# ---------------------------------------------------------------------------
# Transaction History
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex(r"^txn_hist:(\d+)$"))
async def transaction_history_cb(client: Client, callback_query: CallbackQuery):
    """Paginated transaction history."""
    user_id = callback_query.from_user.id
    page = int(callback_query.matches[0].group(1))
    
    txns, total = await get_transactions(user_id, page=page, per_page=10)
    
    if not txns:
        await callback_query.edit_message_text(
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
        
    await callback_query.edit_message_text(
        text,
        reply_markup=add_footer(kb_rows, "wallet")
    )


# ---------------------------------------------------------------------------
# Deposit History
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex(r"^dep_hist:(\d+)$"))
async def deposit_history_cb(client: Client, callback_query: CallbackQuery):
    """Paginated deposit history."""
    user_id = callback_query.from_user.id
    page = int(callback_query.matches[0].group(1))
    
    deps, total = await get_user_deposits(user_id, page=page, per_page=10)
    
    if not deps:
        await callback_query.edit_message_text(
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
        
    await callback_query.edit_message_text(
        text,
        reply_markup=add_footer(kb_rows, "wallet")
    )


# ---------------------------------------------------------------------------
# Add Funds Wizard
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex(r"^add_funds$"))
async def add_funds_cb(client: Client, callback_query: CallbackQuery):
    """Start the add funds wizard."""
    user_id = callback_query.from_user.id
    
    await set_wizard_state(user_id, {
        "flow": "add_funds",
        "step": "amount",
        "msg_id": callback_query.message.id,
    })
    
    await callback_query.edit_message_text(
        "➕ **Add Funds**\n\n"
        "Please enter the **amount** you wish to deposit (e.g., 500):",
        reply_markup=add_footer([], "wallet")
    )
    await callback_query.answer()


# This is called by the main wizard handler in orders.py
async def _handle_deposit_wizard(client: Client, message: Message, state: dict):
    user_id = message.from_user.id
    step = state.get("step")
    
    try:
        await message.delete()
    except Exception:
        pass
        
    if step == "amount":
        if not message.text:
            return
            
        is_valid, amt, err = validate_amount(message.text)
        if not is_valid:
            try:
                await client.edit_message_text(
                    chat_id=user_id,
                    message_id=state["msg_id"],
                    text=f"{err}\n\nPlease enter a valid amount:",
                    reply_markup=add_footer([], "wallet")
                )
            except Exception:
                pass
            return
            
        state["amount"] = amt
        state["step"] = "txn_id"
        await set_wizard_state(user_id, state)
        
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=state["msg_id"],
                text=(
                    f"💰 Amount: {format_currency(amt)}\n\n"
                    "Now, please transfer the funds and enter the **Transaction ID** (UTR / Reference Number):"
                ),
                reply_markup=add_footer([], "add_funds")
            )
        except Exception:
            pass
            
    elif step == "txn_id":
        if not message.text:
            return
            
        txn_id = message.text.strip()
        state["txn_id"] = txn_id
        state["step"] = "screenshot"
        await set_wizard_state(user_id, state)
        
        kb = [[InlineKeyboardButton("⏭ Skip Screenshot", callback_data="skip_screenshot")]]
        
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=state["msg_id"],
                text=(
                    f"💰 Amount: {format_currency(state['amount'])}\n"
                    f"🆔 TXN ID: `{txn_id}`\n\n"
                    "Please send a **screenshot** of the payment, or click Skip."
                ),
                reply_markup=add_footer(kb, "add_funds")
            )
        except Exception:
            pass
            
    elif step == "screenshot":
        # We need a photo
        if message.photo:
            file_id = message.photo.file_id
            await _finalize_deposit(client, user_id, state, file_id)
        else:
            try:
                await client.edit_message_text(
                    chat_id=user_id,
                    message_id=state["msg_id"],
                    text="❌ Please send a valid **photo** or skip this step.",
                    reply_markup=add_footer([[InlineKeyboardButton("⏭ Skip Screenshot", callback_data="skip_screenshot")]], "add_funds")
                )
            except Exception:
                pass


@Client.on_callback_query(filters.regex(r"^skip_screenshot$"))
async def skip_screenshot_cb(client: Client, callback_query: CallbackQuery):
    """Skip screenshot and finalize deposit."""
    user_id = callback_query.from_user.id
    state = await get_wizard_state(user_id)
    
    if not state or state.get("flow") != "add_funds" or state.get("step") != "screenshot":
        await callback_query.answer("Session expired.", show_alert=True)
        return
        
    await _finalize_deposit(client, user_id, state, None, callback_query.message.id)
    await callback_query.answer()


async def _finalize_deposit(client: Client, user_id: int, state: dict, file_id: str | None = None, msg_id: int | None = None):
    """Finalize the deposit request and notify admins."""
    target_msg_id = msg_id or state.get("msg_id")
    
    deposit = await create_deposit(
        user_id=user_id,
        amount=state["amount"],
        transaction_id=state["txn_id"],
        screenshot_file_id=file_id,
    )
    
    await clear_wizard_state(user_id)
    
    try:
        await client.edit_message_text(
            chat_id=user_id,
            message_id=target_msg_id,
            text=(
                f"✅ **Deposit Request Submitted**\n\n"
                f"{SEPARATOR}\n"
                f"Amount: {format_currency(state['amount'])}\n"
                f"TXN ID: `{state['txn_id']}`\n\n"
                "Your request has been sent to the admins for approval."
            ),
            reply_markup=add_footer([], "wallet")
        )
    except Exception:
        pass
        
    await notify_new_deposit_to_admins(client, deposit)


@Client.on_message(filters.photo & filters.private, group=2)
async def _photo_handler(client: Client, message: Message):
    """Handle photo uploads for the deposit wizard."""
    user_id = message.from_user.id
    state = await get_wizard_state(user_id)
    
    if state and state.get("flow") == "add_funds" and state.get("step") == "screenshot":
        await _handle_deposit_wizard(client, message, state)
