"""
Admin settings router.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message, InlineKeyboardButton

from bot.database.mongo import get_global_settings, update_global_settings
from bot.database.redis import get_wizard_state, set_wizard_state, clear_wizard_state
from bot.keyboards.admin_kb import admin_settings_keyboard
from bot.keyboards.common import add_footer
from bot.middlewares.admin_guard import is_admin


@Client.on_callback_query(filters.regex(r"^adm_settings$"))
async def adm_settings_cb(client: Client, callback_query: CallbackQuery):
    """Show global settings."""
    if not is_admin(callback_query.from_user.id):
        return
        
    settings = await get_global_settings()
    
    await callback_query.edit_message_text(
        "⚙ **Global Settings**\n\nManage platform configuration:",
        reply_markup=admin_settings_keyboard(settings)
    )


@Client.on_callback_query(filters.regex(r"^adm_toggle_maint$"))
async def adm_toggle_maint_cb(client: Client, callback_query: CallbackQuery):
    """Toggle maintenance mode."""
    if not is_admin(callback_query.from_user.id):
        return
        
    settings = await get_global_settings()
    current = settings.get("maintenance_mode", False)
    
    await update_global_settings({"maintenance_mode": not current})
    await callback_query.answer(f"Maintenance mode: {'ON' if not current else 'OFF'}", show_alert=True)
    
    # Refresh view
    await adm_settings_cb(client, callback_query)


@Client.on_callback_query(filters.regex(r"^adm_set_(markup|welcome|support)$"))
async def adm_set_wizard_cb(client: Client, callback_query: CallbackQuery):
    """Start setting edit wizard."""
    if not is_admin(callback_query.from_user.id):
        return
        
    field = callback_query.matches[0].group(1)
    
    await set_wizard_state(callback_query.from_user.id, {
        "flow": f"adm_set_{field}",
        "msg_id": callback_query.message.id,
    })
    
    prompts = {
        "markup": "Enter the new **Markup Percentage** (e.g., 50 for 50%):",
        "welcome": "Enter the new **Welcome Message** for /start:",
        "support": "Enter the new **Support Username** (e.g., @MySupport):",
    }
    
    await callback_query.edit_message_text(
        f"⚙ **Update Setting**\n\n{prompts[field]}",
        reply_markup=add_footer([], "adm_settings")
    )


async def _handle_admin_setting_wizard(client: Client, message: Message, state: dict):
    user_id = message.from_user.id
    flow = state.get("flow")
    
    try:
        await message.delete()
    except Exception:
        pass
        
    update = {}
    if flow == "adm_set_markup":
        try:
            val = int(message.text.strip())
            update = {"markup_percent": val}
        except ValueError:
            return
    elif flow == "adm_set_welcome":
        update = {"welcome_message": message.text}
    elif flow == "adm_set_support":
        update = {"support_username": message.text.strip()}
        
    if update:
        await update_global_settings(update)
        await clear_wizard_state(user_id)
        
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=state["msg_id"],
                text="✅ Setting updated successfully.",
                reply_markup=add_footer([[InlineKeyboardButton("🔙 Back to Settings", callback_data="adm_settings")]], "admin")
            )
        except Exception:
            pass
