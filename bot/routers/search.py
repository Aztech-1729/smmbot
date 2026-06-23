"""
Search services router.
"""

from __future__ import annotations

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.mongo import get_global_settings
from bot.keyboards.common import add_footer
from bot.services.provider import get_provider
from bot.utils.validators import sanitize_text

router = Router(name="search")

class SearchWizard(StatesGroup):
    waiting_for_query = State()


@router.callback_query(F.data == "search")
async def search_cb(callback_query: CallbackQuery, state: FSMContext):
    """Start search wizard."""
    await state.set_state(SearchWizard.waiting_for_query)
    await state.update_data(msg_id=callback_query.message.message_id)
    
    await callback_query.message.edit_text(
        "🔍 **Search Services**\n\nPlease enter a keyword to search for (e.g., 'Instagram likes'):",
        reply_markup=add_footer([], "home")
    )
    await callback_query.answer()


@router.message(SearchWizard.waiting_for_query)
async def process_search_query(message: Message, state: FSMContext):
    """Handle text input for search."""
    user_id = message.from_user.id
    query = sanitize_text(message.text, 50).lower()
    data = await state.get_data()
    
    try:
        await message.delete()
    except Exception:
        pass
        
    if not query:
        return
        
    provider = get_provider()
    all_services = await provider.get_services()
    
    results = []
    for svc in all_services:
        name = svc.get("name", "").lower()
        cat = svc.get("category", "").lower()
        if query in name or query in cat:
            results.append(svc)
            
    if not results:
        try:
            await message.bot.edit_message_text(
                chat_id=user_id,
                message_id=data["msg_id"],
                text=f"🔍 No services found for **'{query}'**.\n\nPlease try another keyword:",
                reply_markup=add_footer([], "home")
            )
        except Exception:
            pass
        return
        
    await state.clear()
    
    # Show results using the generic service list keyboard
    # but we'll use a special callback prefix for pagination
    settings = await get_global_settings()
    markup = settings.get("markup_percent", 50)
    
    from bot.utils.pagination import Paginator
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from bot.utils.formatting import format_currency, truncate_text
    
    p = Paginator(results, page=1, per_page=10)
    
    lines = [
        f"━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🔍 **Search Results: '{query}'**",
        f"Found {len(results)} services | Page 1/{p.total_pages}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
    ]
    
    kb = []
    for svc in p.items:
        rate = float(svc.get("rate", 0))
        user_rate = rate * (1 + markup / 100)
        name = svc.get("name", "Service")
        svc_id = svc.get("service", "0")
        btn_text = f"{truncate_text(name, 28)} — {format_currency(user_rate)}/1K"
        kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"svc:{svc_id}", style="primary")])
        
    if p.has_next:
        lines.append("*(Showing top 10 results)*")
        
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text="\n".join(lines),
            reply_markup=add_footer(kb, "home")
        )
    except Exception:
        pass
