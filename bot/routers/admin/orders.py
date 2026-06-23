"""
Admin orders router.
"""

from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton

from bot.services.order_service import get_all_orders_paginated
from bot.models.order import get_status_badge
from bot.keyboards.common import add_footer
from bot.utils.formatting import format_currency


router = Router(name="admin_orders")

@router.callback_query(F.data.startswith("adm_orders:"))
async def adm_orders_cb(callback_query: CallbackQuery):
    """Admin global order list."""
    page = int(callback_query.data.split(":")[1])
    orders, total = await get_all_orders_paginated(page=page)
    
    if not orders:
        await callback_query.message.edit_text(
            "No orders found in the system.",
            reply_markup=add_footer([], "admin")
        )
        return
        
    from bot.utils.pagination import Paginator
    p = Paginator(list(range(total)), page=page, per_page=10)
    
    text = f"📦 **All Orders** (Page {page}/{p.total_pages})\n\n"
    
    kb_rows = []
    for o in orders:
        badge = get_status_badge(o.get("status", ""))
        name = o.get("service_name", "Service")
        short_name = name[:15] + "…" if len(name) > 15 else name
        
        btn_text = f"{badge} [{o['user_id']}] {short_name} — {format_currency(o.get('user_cost', 0))}"
        kb_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"ord:{str(o['_id'])}:{page}", style="primary")])

    nav = p.get_nav_buttons("adm_orders")
    if nav:
        kb_rows.append(nav)
        
    await callback_query.message.edit_text(
        text,
        reply_markup=add_footer(kb_rows, "admin")
    )


@router.callback_query(F.data.startswith("adm_uorders:"))
async def adm_uorders_cb(callback_query: CallbackQuery):
    """Admin view of a specific user's orders."""
    parts = callback_query.data.split(":")
    target_id = int(parts[1])
    page = int(parts[2])
    
    orders, total = await get_all_orders_paginated(page=page, user_filter=target_id)
    
    if not orders:
        await callback_query.message.edit_text(
            f"User `{target_id}` has no orders.",
            reply_markup=add_footer([], f"adm_usr:{target_id}")
        )
        return
        
    from bot.utils.pagination import Paginator
    p = Paginator(list(range(total)), page=page, per_page=10)
    
    text = f"📦 **Orders for {target_id}** (Page {page}/{p.total_pages})\n\n"
    
    kb_rows = []
    for o in orders:
        badge = get_status_badge(o.get("status", ""))
        name = o.get("service_name", "Service")
        short_name = name[:20] + "…" if len(name) > 20 else name
        
        btn_text = f"{badge} {short_name} — {format_currency(o.get('user_cost', 0))}"
        kb_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"ord:{str(o['_id'])}:{page}", style="primary")])

    nav = p.get_nav_buttons(f"adm_uorders:{target_id}")
    if nav:
        kb_rows.append(nav)
        
    await callback_query.message.edit_text(
        text,
        reply_markup=add_footer(kb_rows, f"adm_usr:{target_id}")
    )
