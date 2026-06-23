"""
Admin broadcast router.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.mongo import broadcast_logs_col
from bot.database.redis import get_wizard_state, set_wizard_state, clear_wizard_state
from bot.keyboards.admin_kb import broadcast_type_keyboard
from bot.keyboards.common import add_footer
from bot.middlewares.admin_guard import is_admin
from bot.utils.formatting import SEPARATOR

logger = logging.getLogger(__name__)


@Client.on_callback_query(filters.regex(r"^adm_broadcast$"))
async def adm_broadcast_cb(client: Client, callback_query: CallbackQuery):
    """Broadcast menu."""
    if not is_admin(callback_query.from_user.id):
        return
        
    await callback_query.edit_message_text(
        "📢 **Broadcast System**\n\nSelect the type of message you want to send to all users:",
        reply_markup=broadcast_type_keyboard()
    )


@Client.on_callback_query(filters.regex(r"^bcast_type:(text|photo|video|document)$"))
async def bcast_type_cb(client: Client, callback_query: CallbackQuery):
    """Start broadcast wizard for specific type."""
    if not is_admin(callback_query.from_user.id):
        return
        
    msg_type = callback_query.matches[0].group(1)
    
    await set_wizard_state(callback_query.from_user.id, {
        "flow": "broadcast",
        "type": msg_type,
        "msg_id": callback_query.message.id,
    })
    
    prompts = {
        "text": "Please enter the **Text Message** to broadcast (Markdown supported):",
        "photo": "Please send the **Photo** with an optional caption:",
        "video": "Please send the **Video** with an optional caption:",
        "document": "Please send the **Document** with an optional caption:",
    }
    
    await callback_query.edit_message_text(
        f"📢 **Compose Broadcast**\n\n{prompts[msg_type]}",
        reply_markup=add_footer([], "adm_broadcast")
    )


# Note: This is called by the main wizard_message_handler for text,
# but we need another handler for media types.
async def _handle_broadcast_wizard(client: Client, message: Message, state: dict):
    """Handle text input for text broadcasts."""
    user_id = message.from_user.id
    msg_type = state.get("type")
    
    if msg_type != "text":
        return
        
    try:
        await message.delete()
    except Exception:
        pass
        
    state["content"] = message.text
    await set_wizard_state(user_id, state)
    await _show_broadcast_preview(client, user_id, state)


@Client.on_message((filters.photo | filters.video | filters.document) & filters.private, group=5)
async def _bcast_media_handler(client: Client, message: Message):
    """Handle media input for media broadcasts."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
        
    state = await get_wizard_state(user_id)
    if not state or state.get("flow") != "broadcast":
        return
        
    msg_type = state.get("type")
    
    file_id = None
    if msg_type == "photo" and message.photo:
        file_id = message.photo.file_id
    elif msg_type == "video" and message.video:
        file_id = message.video.file_id
    elif msg_type == "document" and message.document:
        file_id = message.document.file_id
        
    if not file_id:
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=state["msg_id"],
                text=f"❌ Please send a valid **{msg_type}**.",
                reply_markup=add_footer([], "adm_broadcast")
            )
        except Exception:
            pass
        return
        
    try:
        await message.delete()
    except Exception:
        pass
        
    state["file_id"] = file_id
    state["caption"] = message.caption or ""
    await set_wizard_state(user_id, state)
    await _show_broadcast_preview(client, user_id, state)


async def _show_broadcast_preview(client: Client, user_id: int, state: dict):
    """Show a preview and ask for confirmation."""
    msg_type = state.get("type")
    
    text = (
        f"📢 **Broadcast Preview**\n\n"
        f"Type: {msg_type.capitalize()}\n"
    )
    
    if msg_type == "text":
        text += f"\n{SEPARATOR}\n{state['content']}\n{SEPARATOR}\n\n"
    else:
        text += f"Caption: {state['caption']}\n\n"
        
    text += "Are you sure you want to send this to **ALL** users?"
    
    kb = [
        [
            InlineKeyboardButton("🟩 Send Broadcast", callback_data="bcast_confirm"),
            InlineKeyboardButton("🟥 Cancel", callback_data="adm_broadcast"),
        ]
    ]
    
    try:
        await client.edit_message_text(
            chat_id=user_id,
            message_id=state["msg_id"],
            text=text,
            reply_markup=add_footer(kb, "adm_broadcast")
        )
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^bcast_confirm$"))
async def bcast_confirm_cb(client: Client, callback_query: CallbackQuery):
    """Confirm and queue the broadcast."""
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        return
        
    state = await get_wizard_state(user_id)
    if not state or state.get("flow") != "broadcast":
        await callback_query.answer("Session expired.", show_alert=True)
        return
        
    # In a real heavy production system, we would push this to a Redis queue.
    # For this architecture, we will insert a pending job into MongoDB
    # and let the APScheduler worker pick it up.
    
    job_doc = {
        "admin_id": user_id,
        "content_type": state["type"],
        "message": state.get("content", state.get("caption", "")),
        "file_id": state.get("file_id"),
        "status": "pending",
        "total_users": 0,
        "success_count": 0,
        "failed_count": 0,
        "created_at": datetime.now(timezone.utc),
    }
    
    await broadcast_logs_col().insert_one(job_doc)
    await clear_wizard_state(user_id)
    
    await callback_query.edit_message_text(
        "✅ **Broadcast Queued!**\n\nThe background worker will process and send the messages shortly.",
        reply_markup=add_footer([], "adm_broadcast")
    )
    await callback_query.answer()
