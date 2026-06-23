"""
Admin settings router.
"""

from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot.database.mongo import get_global_settings, update_global_settings
from bot.states import AdminSettingsWizard
from bot.keyboards.admin_kb import admin_settings_keyboard
from bot.keyboards.common import add_footer


router = Router(name="admin_settings")

@router.callback_query(F.data == "adm_settings")
async def adm_settings_cb(callback_query: CallbackQuery, state: FSMContext):
    """Show global settings."""
    await state.clear()
        
    settings = await get_global_settings()
    
    await callback_query.message.edit_text(
        "⚙ **Global Settings**\n\nManage platform configuration:",
        reply_markup=admin_settings_keyboard(settings)
    )
    await callback_query.answer()


@router.callback_query(F.data == "adm_toggle_maint")
async def adm_toggle_maint_cb(callback_query: CallbackQuery):
    """Toggle maintenance mode."""
    settings = await get_global_settings()
    current = settings.get("maintenance_mode", False)
    
    await update_global_settings({"maintenance_mode": not current})
    await callback_query.answer(f"Maintenance mode: {'ON' if not current else 'OFF'}", show_alert=True)
    
    # Refresh view
    await adm_settings_cb(callback_query, FSMContext(storage=callback_query.bot.storage, key=callback_query.bot.storage.resolve_address(callback_query.bot, callback_query.message.chat.id, callback_query.from_user.id)))


@router.callback_query(F.data.startswith("adm_set_"))
async def adm_set_wizard_cb(callback_query: CallbackQuery, state: FSMContext):
    """Start setting edit wizard."""
    field = callback_query.data.split("_")[2] # markup, welcome, support
    
    if field == "markup":
        await state.set_state(AdminSettingsWizard.waiting_for_markup)
    elif field == "welcome":
        await state.set_state(AdminSettingsWizard.waiting_for_welcome)
    elif field == "support":
        await state.set_state(AdminSettingsWizard.waiting_for_support)
        
    await state.update_data(msg_id=callback_query.message.message_id)
    
    prompts = {
        "markup": "Enter the new **Markup Percentage** (e.g., 50 for 50%):",
        "welcome": "Enter the new **Welcome Message** for /start:",
        "support": "Enter the new **Support Username** (e.g., @MySupport):",
    }
    
    await callback_query.message.edit_text(
        f"⚙ **Update Setting**\n\n{prompts[field]}",
        reply_markup=add_footer([], "adm_settings")
    )
    await callback_query.answer()


@router.message(AdminSettingsWizard.waiting_for_markup)
async def process_markup_setting(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    try:
        await message.delete()
    except Exception:
        pass
        
    try:
        val = int(message.text.strip())
        await update_global_settings({"markup_percent": val})
        await state.clear()
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text="✅ Setting updated successfully.",
            reply_markup=add_footer([[InlineKeyboardButton(text="🔙 Back to Settings", callback_data="adm_settings", style="primary")]], "admin")
        )
    except ValueError:
        pass


@router.message(AdminSettingsWizard.waiting_for_welcome)
async def process_welcome_setting(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    try:
        await message.delete()
    except Exception:
        pass
        
    await update_global_settings({"welcome_message": message.text})
    await state.clear()
    
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text="✅ Setting updated successfully.",
            reply_markup=add_footer([[InlineKeyboardButton(text="🔙 Back to Settings", callback_data="adm_settings", style="primary")]], "admin")
        )
    except Exception:
        pass


@router.message(AdminSettingsWizard.waiting_for_support)
async def process_support_setting(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    try:
        await message.delete()
    except Exception:
        pass
        
    await update_global_settings({"support_username": message.text.strip()})
    await state.clear()
    
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text="✅ Setting updated successfully.",
            reply_markup=add_footer([[InlineKeyboardButton(text="🔙 Back to Settings", callback_data="adm_settings", style="primary")]], "admin")
        )
    except Exception:
        pass
