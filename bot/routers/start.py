"""
Start and home navigation router for Aiogram 3.
"""

from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from bot.database.mongo import get_global_settings
from bot.keyboards.main_menu import get_main_menu
from bot.config.settings import get_settings

logger = logging.getLogger(__name__)

router = Router(name="start")


@router.message(CommandStart())
async def start_cmd(message: Message, user_data: dict, state: FSMContext):
    """Handle /start command and display main menu."""
    await state.clear()
    
    settings = await get_global_settings()
    app_settings = get_settings()
    is_admin = message.from_user.id in app_settings.ADMIN_IDS

    welcome_msg = settings.get("welcome_message", "Welcome!")
    kb = get_main_menu(is_admin=is_admin)

    await message.answer(welcome_msg, reply_markup=kb)


@router.callback_query(F.data == "home")
async def home_cb(callback_query: CallbackQuery, user_data: dict, state: FSMContext):
    """Return to the main menu."""
    await state.clear()
    
    settings = await get_global_settings()
    app_settings = get_settings()
    is_admin = callback_query.from_user.id in app_settings.ADMIN_IDS

    welcome_msg = settings.get("welcome_message", "Welcome!")
    kb = get_main_menu(is_admin=is_admin)

    try:
        await callback_query.message.edit_text(welcome_msg, reply_markup=kb)
    except Exception:
        pass
    await callback_query.answer()


@router.callback_query(F.data == "close")
async def close_cb(callback_query: CallbackQuery):
    """Dismiss the message."""
    try:
        await callback_query.message.delete()
    except Exception:
        pass
    await callback_query.answer()
