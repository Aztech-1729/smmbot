"""
Search services router.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery

from bot.database.mongo import get_global_settings
from bot.database.redis import get_wizard_state, set_wizard_state, clear_wizard_state
from bot.keyboards.common import add_footer
from bot.keyboards.order_kb import service_list_keyboard
from bot.services.provider import get_provider
from bot.utils.validators import sanitize_text


@Client.on_callback_query(filters.regex(r"^search$"))
async def search_cb(client: Client, callback_query: CallbackQuery):
    """Start search wizard."""
    user_id = callback_query.from_user.id
    
    await set_wizard_state(user_id, {
        "flow": "search",
        "msg_id": callback_query.message.id,
    })
    
    await callback_query.edit_message_text(
        "🔍 **Search Services**\n\nPlease enter a keyword to search for (e.g., 'Instagram likes'):",
        reply_markup=add_footer([], "home")
    )
    await callback_query.answer()


async def _handle_search_wizard(client: Client, message: Message, state: dict):
    """Handle text input for search."""
    user_id = message.from_user.id
    query = sanitize_text(message.text, 50).lower()
    
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
            await client.edit_message_text(
                chat_id=user_id,
                message_id=state["msg_id"],
                text=f"🔍 No services found for **'{query}'**.\n\nPlease try another keyword:",
                reply_markup=add_footer([], "home")
            )
        except Exception:
            pass
        return
        
    await clear_wizard_state(user_id)
    
    # Show results using the generic service list keyboard
    # but we'll use a special callback prefix for pagination
    settings = await get_global_settings()
    markup = settings.get("markup_percent", 50)
    
    # Let's write a quick inline builder for search results
    from bot.utils.pagination import Paginator
    from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
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
        kb.append([InlineKeyboardButton(btn_text, callback_data=f"svc:{svc_id}")])
        
    # We won't do pagination for search to keep it simple, just top 10
    if p.has_next:
        lines.append("*(Showing top 10 results)*")
        
    try:
        await client.edit_message_text(
            chat_id=user_id,
            message_id=state["msg_id"],
            text="\n".join(lines),
            reply_markup=add_footer(kb, "home")
        )
    except Exception:
        pass
