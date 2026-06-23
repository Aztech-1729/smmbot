"""
Admin broadcast router.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot.database.mongo import broadcast_logs_col
from bot.states import AdminBroadcastWizard
from bot.keyboards.admin_kb import broadcast_type_keyboard
from bot.keyboards.common import add_footer
from bot.utils.formatting import SEPARATOR

logger = logging.getLogger(__name__)


router = Router(name="admin_broadcast")

@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_cb(callback_query: CallbackQuery, state: FSMContext):
    """Broadcast menu."""
    await state.clear()
        
    await callback_query.message.edit_text(
        "📢 **Broadcast System**\n\nSelect the type of message you want to send to all users:",
        reply_markup=broadcast_type_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("bcast_type:"))
async def bcast_type_cb(callback_query: CallbackQuery, state: FSMContext):
    """Start broadcast wizard for specific type."""
    msg_type = callback_query.data.split(":")[1]
    
    await state.set_state(AdminBroadcastWizard.waiting_for_content)
    await state.update_data(
        type=msg_type,
        msg_id=callback_query.message.message_id,
    )
    
    prompts = {
        "text": "Please enter the **Text Message** to broadcast (Markdown supported):",
        "photo": "Please send the **Photo** with an optional caption:",
        "video": "Please send the **Video** with an optional caption:",
        "document": "Please send the **Document** with an optional caption:",
    }
    
    await callback_query.message.edit_text(
        f"📢 **Compose Broadcast**\n\n{prompts[msg_type]}",
        reply_markup=add_footer([], "adm_broadcast")
    )
    await callback_query.answer()


@router.message(AdminBroadcastWizard.waiting_for_content, F.text)
async def process_broadcast_text(message: Message, state: FSMContext):
    """Handle text input for text broadcasts."""
    user_id = message.from_user.id
    data = await state.get_data()
    msg_type = data.get("type")
    
    if msg_type != "text":
        return
        
    try:
        await message.delete()
    except Exception:
        pass
        
    await state.update_data(content=message.text)
    await state.set_state("AdminBroadcastWizard:confirming")
    await _show_broadcast_preview(message.bot, user_id, await state.get_data())


@router.message(AdminBroadcastWizard.waiting_for_content, F.photo | F.video | F.document)
async def process_broadcast_media(message: Message, state: FSMContext):
    """Handle media input for media broadcasts."""
    user_id = message.from_user.id
    data = await state.get_data()
    msg_type = data.get("type")
    
    file_id = None
    if msg_type == "photo" and message.photo:
        file_id = message.photo[-1].file_id
    elif msg_type == "video" and message.video:
        file_id = message.video.file_id
    elif msg_type == "document" and message.document:
        file_id = message.document.file_id
        
    if not file_id:
        try:
            await message.bot.edit_message_text(
                chat_id=user_id,
                message_id=data["msg_id"],
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
        
    await state.update_data(
        file_id=file_id,
        caption=message.caption or ""
    )
    await state.set_state("AdminBroadcastWizard:confirming")
    await _show_broadcast_preview(message.bot, user_id, await state.get_data())


async def _show_broadcast_preview(bot, user_id: int, data: dict):
    """Show a preview and ask for confirmation."""
    msg_type = data.get("type")
    
    text = (
        f"📢 **Broadcast Preview**\n\n"
        f"Type: {msg_type.capitalize()}\n"
    )
    
    if msg_type == "text":
        text += f"\n{SEPARATOR}\n{data['content']}\n{SEPARATOR}\n\n"
    else:
        text += f"Caption: {data.get('caption', '')}\n\n"
        
    text += "Are you sure you want to send this to **ALL** users?"
    
    kb = [
        [
            InlineKeyboardButton(text="🟩 Send Broadcast", callback_data="bcast_confirm", style="success"),
            InlineKeyboardButton(text="🟥 Cancel", callback_data="adm_broadcast", style="danger"),
        ]
    ]
    
    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text=text,
            reply_markup=add_footer(kb, "adm_broadcast")
        )
    except Exception:
        pass


@router.callback_query(AdminBroadcastWizard.confirming, F.data == "bcast_confirm")
async def bcast_confirm_cb(callback_query: CallbackQuery, state: FSMContext):
    """Confirm and queue the broadcast."""
    user_id = callback_query.from_user.id
    data = await state.get_data()
        
    job_doc = {
        "admin_id": user_id,
        "content_type": data["type"],
        "message": data.get("content", data.get("caption", "")),
        "file_id": data.get("file_id"),
        "status": "pending",
        "total_users": 0,
        "success_count": 0,
        "failed_count": 0,
        "created_at": datetime.now(timezone.utc),
    }
    
    await broadcast_logs_col().insert_one(job_doc)
    await state.clear()
    
    await callback_query.message.edit_text(
        "✅ **Broadcast Queued!**\n\nThe background worker will process and send the messages shortly.",
        reply_markup=add_footer([], "adm_broadcast")
    )
    await callback_query.answer()
