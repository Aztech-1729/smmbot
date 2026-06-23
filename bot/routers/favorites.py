"""
Favorites router.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.mongo import favorites_col
from bot.keyboards.common import add_footer


@Client.on_callback_query(filters.regex(r"^fav:(\d+)$"))
async def add_favorite_cb(client: Client, callback_query: CallbackQuery):
    """Add a service to favorites."""
    user_id = callback_query.from_user.id
    svc_id = callback_query.matches[0].group(1)
    
    from bot.services.provider import get_provider
    provider = get_provider()
    service = await provider.find_service_by_id(svc_id)
    
    if not service:
        await callback_query.answer("Service not found.", show_alert=True)
        return
        
    try:
        await favorites_col().insert_one({
            "user_id": user_id,
            "service_id": svc_id,
            "service_name": service.get("name", ""),
            "category": service.get("category", ""),
            "added_at": datetime.now(timezone.utc),
        })
        await callback_query.answer("Added to favorites! ⭐", show_alert=True)
    except Exception:
        # Likely duplicate key error
        await callback_query.answer("Already in favorites.", show_alert=True)
        
    # Refresh detail page
    from bot.routers.orders import service_detail_cb
    await service_detail_cb(client, callback_query)


@Client.on_callback_query(filters.regex(r"^unfav:(\d+)$"))
async def remove_favorite_cb(client: Client, callback_query: CallbackQuery):
    """Remove a service from favorites."""
    user_id = callback_query.from_user.id
    svc_id = callback_query.matches[0].group(1)
    
    await favorites_col().delete_one({"user_id": user_id, "service_id": svc_id})
    await callback_query.answer("Removed from favorites.", show_alert=True)
    
    # Refresh detail page
    from bot.routers.orders import service_detail_cb
    await service_detail_cb(client, callback_query)


@Client.on_callback_query(filters.regex(r"^favorites:(\d+)$"))
async def list_favorites_cb(client: Client, callback_query: CallbackQuery):
    """List favorited services."""
    user_id = callback_query.from_user.id
    page = int(callback_query.matches[0].group(1))
    
    col = favorites_col()
    total = await col.count_documents({"user_id": user_id})
    
    if total == 0:
        await callback_query.edit_message_text(
            "You haven't added any services to your favorites yet.\n\n"
            "Browse services and click ⭐ **Add to Favorites**.",
            reply_markup=add_footer([], "home")
        )
        return
        
    per_page = 10
    skip = (page - 1) * per_page
    cursor = col.find({"user_id": user_id}).sort("added_at", -1).skip(skip).limit(per_page)
    favs = await cursor.to_list(length=per_page)
    
    from bot.utils.pagination import Paginator
    from bot.utils.formatting import truncate_text
    
    p = Paginator(list(range(total)), page=page, per_page=per_page)
    
    text = f"⭐ **My Favorites** (Page {page}/{p.total_pages})\n\n"
    
    kb = []
    for fav in favs:
        name = fav.get("service_name", "Service")
        svc_id = fav.get("service_id")
        kb.append([InlineKeyboardButton(f"⭐ {truncate_text(name, 35)}", callback_data=f"svc:{svc_id}")])
        
    nav = p.get_nav_buttons("favorites")
    if nav:
        kb.append(nav)
        
    await callback_query.edit_message_text(text, reply_markup=add_footer(kb, "home"))
    await callback_query.answer()
