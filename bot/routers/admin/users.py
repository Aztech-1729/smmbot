"""
Admin user management router.
"""

from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.mongo import users_col
from bot.states import AdminAdjustWizard
from bot.keyboards.admin_kb import admin_user_actions_keyboard
from bot.keyboards.common import add_footer
from bot.services.wallet_service import admin_adjust_balance
from bot.utils.formatting import format_currency, format_datetime, SEPARATOR


router = Router(name="admin_users")

class AdminSearchUserWizard(StatesGroup):
    waiting_for_query = State()


@router.callback_query(F.data == "adm_users")
async def adm_users_cb(callback_query: CallbackQuery, state: FSMContext):
    """Start user search wizard."""
    await state.set_state(AdminSearchUserWizard.waiting_for_query)
    await state.update_data(msg_id=callback_query.message.message_id)
    
    await callback_query.message.edit_text(
        "👥 **User Management**\n\n"
        "Please enter the **Telegram User ID** or **Username** (without @) of the user:",
        reply_markup=add_footer([], "admin")
    )
    await callback_query.answer()


@router.message(AdminSearchUserWizard.waiting_for_query)
async def process_user_search(message: Message, state: FSMContext):
    """Handle text input for user search."""
    user_id = message.from_user.id
    data = await state.get_data()
        
    query = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass
        
    # Search by ID or Username
    try:
        search_id = int(query)
        user = await users_col().find_one({"_id": search_id})
    except ValueError:
        # It's a string
        user = await users_col().find_one({"username": {"$regex": f"^{query}$", "$options": "i"}})
        
    if not user:
        try:
            await message.bot.edit_message_text(
                chat_id=user_id,
                message_id=data["msg_id"],
                text=f"❌ User `{query}` not found.\n\nPlease try again:",
                reply_markup=add_footer([], "admin")
            )
        except Exception:
            pass
        return
        
    await state.clear()
    
    target_id = user["_id"]
    username = user.get("username", "N/A")
    username_str = f"@{username}" if username != "N/A" else "None"
    banned = "🔴 YES" if user.get("is_banned") else "🟢 NO"
    
    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **User Profile**\n\n"
        f"ID:       `{target_id}`\n"
        f"Username: {username_str}\n"
        f"Name:     {user.get('first_name', '')}\n"
        f"Balance:  {format_currency(user.get('balance', 0))}\n"
        f"Orders:   {user.get('total_orders', 0):,}\n"
        f"Joined:   {format_datetime(user.get('joined_at'))}\n"
        f"Banned:   {banned}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    kb = admin_user_actions_keyboard(target_id)
    
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text=text,
            reply_markup=kb
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm_adjust:"))
async def adm_adjust_cb(callback_query: CallbackQuery, state: FSMContext):
    """Start admin balance adjustment wizard."""
    target_id = int(callback_query.data.split(":")[1])
    
    await state.set_state(AdminAdjustWizard.waiting_for_amount)
    await state.update_data(
        target_id=target_id,
        msg_id=callback_query.message.message_id,
    )
    
    await callback_query.message.edit_text(
        f"💰 **Adjust Balance** for `{target_id}`\n\n"
        "Enter the amount to adjust (use negative numbers to deduct, e.g. `-50` or `100`):",
        reply_markup=add_footer([], "adm_users")
    )
    await callback_query.answer()


@router.message(AdminAdjustWizard.waiting_for_amount)
async def process_adjust_amount(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    try:
        await message.delete()
    except Exception:
        pass
        
    try:
        amount = float(message.text.strip().replace(",", ""))
    except ValueError:
        try:
            await message.bot.edit_message_text(
                chat_id=user_id,
                message_id=data["msg_id"],
                text="❌ Invalid number. Please enter a valid amount:",
                reply_markup=add_footer([], "adm_users")
            )
        except Exception:
            pass
        return
        
    await state.update_data(amount=amount)
    await state.set_state("AdminAdjustWizard:waiting_for_reason")
    
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text=f"Amount: `{amount}`\n\nPlease enter a **Reason** for this adjustment:",
            reply_markup=add_footer([], "adm_users")
        )
    except Exception:
        pass


@router.message(F.state == "AdminAdjustWizard:waiting_for_reason")
async def process_adjust_reason(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    try:
        await message.delete()
    except Exception:
        pass
        
    reason = message.text.strip()
    amount = data["amount"]
    target_id = data["target_id"]
    
    await state.clear()
    
    success = await admin_adjust_balance(target_id, amount, reason)
    if success:
        text = f"✅ Balance adjusted successfully.\nTarget: `{target_id}`\nAmount: {amount}"
    else:
        text = "❌ Failed to adjust balance."
        
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text=text,
            reply_markup=add_footer([[InlineKeyboardButton(text="🔙 Back to User", callback_data=f"adm_usr:{target_id}", style="primary")]], "adm_users")
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm_ban:"))
async def adm_ban_cb(callback_query: CallbackQuery):
    target_id = int(callback_query.data.split(":")[1])
    await users_col().update_one({"_id": target_id}, {"$set": {"is_banned": True}})
    await callback_query.answer("User banned.", show_alert=True)
    
    await adm_usr_direct_cb(callback_query)


@router.callback_query(F.data.startswith("adm_unban:"))
async def adm_unban_cb(callback_query: CallbackQuery):
    target_id = int(callback_query.data.split(":")[1])
    await users_col().update_one({"_id": target_id}, {"$set": {"is_banned": False}})
    await callback_query.answer("User unbanned.", show_alert=True)
    
    await adm_usr_direct_cb(callback_query)


@router.callback_query(F.data.startswith("adm_usr:"))
async def adm_usr_direct_cb(callback_query: CallbackQuery):
    target_id = int(callback_query.data.split(":")[1])
    user = await users_col().find_one({"_id": target_id})
    if not user:
        await callback_query.answer("User not found.", show_alert=True)
        return
        
    username = user.get("username", "N/A")
    username_str = f"@{username}" if username != "N/A" else "None"
    banned = "🔴 YES" if user.get("is_banned") else "🟢 NO"
    
    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **User Profile**\n\n"
        f"ID:       `{target_id}`\n"
        f"Username: {username_str}\n"
        f"Balance:  {format_currency(user.get('balance', 0))}\n"
        f"Orders:   {user.get('total_orders', 0):,}\n"
        f"Banned:   {banned}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    kb = admin_user_actions_keyboard(target_id)
    try:
        await callback_query.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback_query.answer()
