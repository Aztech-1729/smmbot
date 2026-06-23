"""
Admin user management router.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message, InlineKeyboardButton

from bot.database.mongo import users_col
from bot.database.redis import set_wizard_state, clear_wizard_state
from bot.keyboards.admin_kb import admin_user_actions_keyboard
from bot.keyboards.common import add_footer
from bot.middlewares.admin_guard import is_admin
from bot.services.wallet_service import admin_adjust_balance
from bot.utils.formatting import format_currency, format_datetime, SEPARATOR
from bot.utils.validators import validate_amount


@Client.on_callback_query(filters.regex(r"^adm_users$"))
async def adm_users_cb(client: Client, callback_query: CallbackQuery):
    """Start user search wizard."""
    if not is_admin(callback_query.from_user.id):
        return
        
    await set_wizard_state(callback_query.from_user.id, {
        "flow": "adm_users",
        "msg_id": callback_query.message.id,
    })
    
    await callback_query.edit_message_text(
        "👥 **User Management**\n\n"
        "Please enter the **Telegram User ID** or **Username** (without @) of the user:",
        reply_markup=add_footer([], "admin")
    )


@Client.on_message(filters.text & filters.private, group=2)
async def _adm_users_handler(client: Client, message: Message):
    """Handle text input for user search."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
        
    from bot.database.redis import get_wizard_state
    state = await get_wizard_state(user_id)
    if not state or state.get("flow") != "adm_users":
        return
        
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
            await client.edit_message_text(
                chat_id=user_id,
                message_id=state["msg_id"],
                text=f"❌ User `{query}` not found.\n\nPlease try again:",
                reply_markup=add_footer([], "admin")
            )
        except Exception:
            pass
        return
        
    await clear_wizard_state(user_id)
    
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
        await client.edit_message_text(
            chat_id=user_id,
            message_id=state["msg_id"],
            text=text,
            reply_markup=kb
        )
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^adm_adjust:(\d+)$"))
async def adm_adjust_cb(client: Client, callback_query: CallbackQuery):
    """Start admin balance adjustment wizard."""
    if not is_admin(callback_query.from_user.id):
        return
        
    target_id = int(callback_query.matches[0].group(1))
    
    await set_wizard_state(callback_query.from_user.id, {
        "flow": "adm_adjust",
        "step": "amount",
        "target_id": target_id,
        "msg_id": callback_query.message.id,
    })
    
    await callback_query.edit_message_text(
        f"💰 **Adjust Balance** for `{target_id}`\n\n"
        "Enter the amount to adjust (use negative numbers to deduct, e.g. `-50` or `100`):",
        reply_markup=add_footer([], "adm_users")
    )


async def _handle_admin_adjust_wizard(client: Client, message: Message, state: dict):
    user_id = message.from_user.id
    step = state.get("step")
    target_id = state.get("target_id")
    
    try:
        await message.delete()
    except Exception:
        pass
        
    if step == "amount":
        try:
            amount = float(message.text.strip().replace(",", ""))
        except ValueError:
            try:
                await client.edit_message_text(
                    chat_id=user_id,
                    message_id=state["msg_id"],
                    text="❌ Invalid number. Please enter a valid amount:",
                    reply_markup=add_footer([], "adm_users")
                )
            except Exception:
                pass
            return
            
        state["amount"] = amount
        state["step"] = "reason"
        await set_wizard_state(user_id, state)
        
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=state["msg_id"],
                text=f"Amount: `{amount}`\n\nPlease enter a **Reason** for this adjustment:",
                reply_markup=add_footer([], "adm_users")
            )
        except Exception:
            pass
            
    elif step == "reason":
        reason = message.text.strip()
        amount = state["amount"]
        
        await clear_wizard_state(user_id)
        
        success = await admin_adjust_balance(target_id, amount, reason)
        if success:
            text = f"✅ Balance adjusted successfully.\nTarget: `{target_id}`\nAmount: {amount}"
        else:
            text = "❌ Failed to adjust balance."
            
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=state["msg_id"],
                text=text,
                reply_markup=add_footer([[InlineKeyboardButton("🔙 Back to User", callback_data=f"adm_usr:{target_id}")]], "adm_users")
            )
        except Exception:
            pass


@Client.on_callback_query(filters.regex(r"^adm_ban:(\d+)$"))
async def adm_ban_cb(client: Client, callback_query: CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        return
    target_id = int(callback_query.matches[0].group(1))
    await users_col().update_one({"_id": target_id}, {"$set": {"is_banned": True}})
    await callback_query.answer("User banned.", show_alert=True)
    
    # Send user back to search
    await adm_users_cb(client, callback_query)


@Client.on_callback_query(filters.regex(r"^adm_unban:(\d+)$"))
async def adm_unban_cb(client: Client, callback_query: CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        return
    target_id = int(callback_query.matches[0].group(1))
    await users_col().update_one({"_id": target_id}, {"$set": {"is_banned": False}})
    await callback_query.answer("User unbanned.", show_alert=True)
    
    await adm_users_cb(client, callback_query)


# We need a hidden route to view a user directly by ID after actions
@Client.on_callback_query(filters.regex(r"^adm_usr:(\d+)$"))
async def adm_usr_direct_cb(client: Client, callback_query: CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        return
        
    target_id = int(callback_query.matches[0].group(1))
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
    await callback_query.edit_message_text(text, reply_markup=kb)
