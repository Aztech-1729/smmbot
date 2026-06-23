"""
Order placement and tracking router.
"""

from __future__ import annotations

import logging
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery

from bot.database.mongo import get_global_settings
from bot.database.redis import (
    get_wizard_state, set_wizard_state, clear_wizard_state, delete_cached
)
from bot.keyboards.order_kb import (
    categories_keyboard, service_list_keyboard, service_detail_keyboard,
    order_confirm_keyboard, order_detail_keyboard
)
from bot.keyboards.common import add_footer
from bot.middlewares.auth import upsert_user, check_banned, check_maintenance
from bot.middlewares.rate_limit import is_rate_limited
from bot.models.order import OrderStatus
from bot.services.provider import get_provider, ProviderAPIError
from bot.services.order_service import (
    calculate_user_cost, place_order, get_user_orders, get_order_by_id,
    get_order_by_provider_id, refresh_order_status, request_refill, request_cancel, InsufficientBalanceError, OrderError
)
from bot.services.wallet_service import get_balance
from bot.utils.formatting import format_currency, format_datetime, SEPARATOR
from bot.utils.validators import validate_url, validate_quantity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# New Order Flow
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex(r"^new_order$"))
async def new_order_cb(client: Client, callback_query: CallbackQuery):
    """Show categories."""
    user_id = callback_query.from_user.id
    await clear_wizard_state(user_id)

    provider = get_provider()
    try:
        grouped = await provider.get_services_by_category()
    except Exception as e:
        await callback_query.answer(f"Failed to fetch services: {e}", show_alert=True)
        return

    categories = list(grouped.keys())
    kb = categories_keyboard(categories)

    await callback_query.edit_message_text(
        "📦 **Select a Category**",
        reply_markup=kb
    )
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^cat:(.*)$"))
async def category_cb(client: Client, callback_query: CallbackQuery):
    """Show services for a category."""
    user_id = callback_query.from_user.id
    await clear_wizard_state(user_id)
    
    cat_name = callback_query.matches[0].group(1)
    
    provider = get_provider()
    grouped = await provider.get_services_by_category()
    
    # We might have truncated the category name in the callback data to fit in 64 bytes
    # Let's find the full category name
    full_cat = None
    for c in grouped.keys():
        if c.startswith(cat_name):
            full_cat = c
            break
            
    if not full_cat or full_cat not in grouped:
        await callback_query.answer("Category not found.", show_alert=True)
        return

    settings = await get_global_settings()
    markup = settings.get("markup_percent", 50)

    text, kb = service_list_keyboard(grouped[full_cat], full_cat, page=1, markup_percent=markup)
    
    try:
        await callback_query.edit_message_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^svcpg:(.*):(\d+)$"))
async def service_page_cb(client: Client, callback_query: CallbackQuery):
    """Paginate services."""
    cat_name = callback_query.matches[0].group(1)
    page = int(callback_query.matches[0].group(2))
    
    provider = get_provider()
    grouped = await provider.get_services_by_category()
    
    full_cat = None
    for c in grouped.keys():
        if c.startswith(cat_name):
            full_cat = c
            break
            
    if not full_cat or full_cat not in grouped:
        await callback_query.answer("Category not found.", show_alert=True)
        return

    settings = await get_global_settings()
    markup = settings.get("markup_percent", 50)

    text, kb = service_list_keyboard(grouped[full_cat], full_cat, page=page, markup_percent=markup)
    
    try:
        await callback_query.edit_message_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^svc:(\d+)$"))
async def service_detail_cb(client: Client, callback_query: CallbackQuery):
    """Show service details."""
    user_id = callback_query.from_user.id
    await clear_wizard_state(user_id)
    svc_id = callback_query.matches[0].group(1)
    
    provider = get_provider()
    service = await provider.find_service_by_id(svc_id)
    
    if not service:
        await callback_query.answer("Service not found.", show_alert=True)
        return

    settings = await get_global_settings()
    markup = settings.get("markup_percent", 50)
    
    # Check if favorited
    from bot.database.mongo import favorites_col
    fav = await favorites_col().find_one({"user_id": user_id, "service_id": svc_id})
    is_favorite = bool(fav)

    text, kb = service_detail_keyboard(service, markup_percent=markup, is_favorite=is_favorite)
    
    await callback_query.edit_message_text(text, reply_markup=kb)
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^place:(\d+)$"))
async def place_order_cb(client: Client, callback_query: CallbackQuery):
    """Start the order placement wizard."""
    user_id = callback_query.from_user.id
    svc_id = callback_query.matches[0].group(1)
    
    provider = get_provider()
    service = await provider.find_service_by_id(svc_id)
    
    if not service:
        await callback_query.answer("Service not found.", show_alert=True)
        return

    # Store wizard state
    await set_wizard_state(user_id, {
        "flow": "new_order",
        "step": "url",
        "service_id": svc_id,
        "service_name": service.get("name", ""),
        "rate": float(service.get("rate", 0)),
        "min": int(service.get("min", 0)),
        "max": int(service.get("max", 0)),
        "msg_id": callback_query.message.id,
    })

    await callback_query.edit_message_text(
        f"🔗 **Enter the target URL** for `{service.get('name')}`\n\n"
        "Please provide the full URL (e.g., https://instagram.com/p/...).",
        reply_markup=add_footer([], f"svc:{svc_id}")
    )
    await callback_query.answer()


@Client.on_message(filters.text & filters.private)
async def wizard_message_handler(client: Client, message: Message):
    """Handle text input for wizards (order, deposit, support)."""
    user_id = message.from_user.id
    state = await get_wizard_state(user_id)
    
    if not state:
        # Fallthrough to other handlers or ignore
        return

    flow = state.get("flow")
    
    if flow == "new_order":
        await _handle_order_wizard(client, message, state)
    elif flow == "add_funds":
        from bot.routers.wallet import _handle_deposit_wizard
        await _handle_deposit_wizard(client, message, state)
    elif flow == "support":
        from bot.routers.support import _handle_support_wizard
        await _handle_support_wizard(client, message, state)
    elif flow == "broadcast":
        from bot.routers.admin.broadcast import _handle_broadcast_wizard
        await _handle_broadcast_wizard(client, message, state)
    elif flow.startswith("adm_set_"):
        from bot.routers.admin.settings import _handle_admin_setting_wizard
        await _handle_admin_setting_wizard(client, message, state)
    elif flow == "adm_adjust":
        from bot.routers.admin.users import _handle_admin_adjust_wizard
        await _handle_admin_adjust_wizard(client, message, state)
    elif flow == "track_order":
        await _handle_track_order_wizard(client, message, state)
    elif flow == "search":
        from bot.routers.search import _handle_search_wizard
        await _handle_search_wizard(client, message, state)


async def _handle_order_wizard(client: Client, message: Message, state: dict):
    user_id = message.from_user.id
    step = state.get("step")
    
    # Delete user's message to keep chat clean
    try:
        await message.delete()
    except Exception:
        pass

    if step == "url":
        url = message.text.strip()
        if not validate_url(url):
            try:
                await client.edit_message_text(
                    chat_id=user_id,
                    message_id=state["msg_id"],
                    text="❌ **Invalid URL format.**\n\nPlease enter a valid URL starting with http:// or https://",
                    reply_markup=add_footer([], f"svc:{state['service_id']}")
                )
            except Exception:
                pass
            return
            
        state["url"] = url
        state["step"] = "quantity"
        await set_wizard_state(user_id, state)
        
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=state["msg_id"],
                text=(
                    f"🔢 **Enter Quantity**\n\n"
                    f"URL: `{url}`\n"
                    f"Min: {state['min']:,} | Max: {state['max']:,}\n\n"
                    "Please type the number you want to order:"
                ),
                reply_markup=add_footer([], f"place:{state['service_id']}")
            )
        except Exception:
            pass
            
    elif step == "quantity":
        qty_str = message.text.strip()
        is_valid, qty, err = validate_quantity(qty_str, state["min"], state["max"])
        
        if not is_valid:
            try:
                await client.edit_message_text(
                    chat_id=user_id,
                    message_id=state["msg_id"],
                    text=f"{err}\n\nPlease try again:",
                    reply_markup=add_footer([], f"place:{state['service_id']}")
                )
            except Exception:
                pass
            return
            
        state["quantity"] = qty
        state["step"] = "confirm"
        await set_wizard_state(user_id, state)
        
        # Calculate cost
        settings = await get_global_settings()
        markup = settings.get("markup_percent", 50)
        user_cost = calculate_user_cost(qty, state["rate"], markup)
        state["user_cost"] = user_cost
        await set_wizard_state(user_id, state)
        
        balance = await get_balance(user_id)
        
        text = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛒 **Order Summary**\n\n"
            f"Service:   {state['service_name']}\n"
            f"Quantity:  {qty:,}\n"
            f"URL:       {state['url']}\n"
            f"Price:     {format_currency(user_cost)}\n"
            f"Balance:   {format_currency(balance)} → {format_currency(balance - user_cost)}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=state["msg_id"],
                text=text,
                reply_markup=order_confirm_keyboard()
            )
        except Exception:
            pass


@Client.on_callback_query(filters.regex(r"^order_confirm$"))
async def confirm_order_cb(client: Client, callback_query: CallbackQuery):
    """Finalize order placement."""
    user_id = callback_query.from_user.id
    state = await get_wizard_state(user_id)
    
    if not state or state.get("flow") != "new_order" or state.get("step") != "confirm":
        await callback_query.answer("Session expired. Please start over.", show_alert=True)
        return

    await callback_query.edit_message_text("⏳ Processing order...")
    
    try:
        order = await place_order(
            user_id=user_id,
            service_id=state["service_id"],
            url=state["url"],
            quantity=state["quantity"],
        )
        await clear_wizard_state(user_id)
        
        # We don't need to notify via notification_service here because the user gets this inline response
        await callback_query.edit_message_text(
            f"✅ **Order Placed Successfully!**\n\n"
            f"{SEPARATOR}\n"
            f"📦 Service: {order.get('service_name')}\n"
            f"🔢 Quantity: {order.get('quantity'):,}\n"
            f"🔗 URL: {order.get('url')}\n"
            f"💰 Cost: {format_currency(order.get('user_cost'))}\n"
            f"🆔 Order ID: `{order.get('provider_order_id')}`\n"
            f"{SEPARATOR}",
            reply_markup=add_footer([], "home")
        )
        
    except InsufficientBalanceError as e:
        kb = add_footer([
            [{"text": "➕ Add Funds", "callback_data": "add_funds"}],
        ], "new_order")
        from pyrogram.types import InlineKeyboardMarkup
        await callback_query.edit_message_text(
            f"❌ **Failed**\n\n{str(e)}",
            reply_markup=InlineKeyboardMarkup(kb.inline_keyboard)
        )
    except OrderError as e:
        await callback_query.edit_message_text(
            f"❌ **Order Failed**\n\n{str(e)}\n\nAny deducted balance has been refunded.",
            reply_markup=add_footer([], "new_order")
        )
    except Exception as e:
        logger.exception("Order error")
        await callback_query.edit_message_text(
            f"❌ **System Error**\n\nFailed to place order. Please try again later.",
            reply_markup=add_footer([], "new_order")
        )


@Client.on_callback_query(filters.regex(r"^order_cancel$"))
async def cancel_order_cb(client: Client, callback_query: CallbackQuery):
    """Cancel order placement."""
    user_id = callback_query.from_user.id
    await clear_wizard_state(user_id)
    await callback_query.answer("Order cancelled.")
    
    # Return to home
    from bot.routers.start import home_cb
    await home_cb(client, callback_query)


# ---------------------------------------------------------------------------
# My Orders
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex(r"^my_orders:(\d+)$"))
async def my_orders_cb(client: Client, callback_query: CallbackQuery):
    """List user orders."""
    user_id = callback_query.from_user.id
    page = int(callback_query.matches[0].group(1))
    
    orders, total = await get_user_orders(user_id, page=page, per_page=10)
    
    if not orders:
        await callback_query.edit_message_text(
            "You don't have any orders yet.",
            reply_markup=add_footer([], "home")
        )
        return

    from bot.models.order import get_status_badge
    from bot.utils.pagination import Paginator
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    # Create a mock paginator just to use its nav_buttons logic
    # We already did DB pagination
    p = Paginator(list(range(total)), page=page, per_page=10)
    
    text = f"📦 **My Orders** (Page {page}/{p.total_pages})\n\n"
    
    kb_rows = []
    for o in orders:
        badge = get_status_badge(o.get("status", ""))
        name = o.get("service_name", "Service")
        # Ensure name is short
        short_name = name[:20] + "…" if len(name) > 20 else name
        btn_text = f"{badge} {short_name} — {o.get('quantity')} — {format_currency(o.get('user_cost'))}"
        kb_rows.append([InlineKeyboardButton(btn_text, callback_data=f"ord:{str(o['_id'])}:{page}")])

    nav = p.get_nav_buttons("my_orders")
    if nav:
        kb_rows.append(nav)
        
    kb_rows.append(add_footer([], "home").inline_keyboard[0])
    
    await callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb_rows))


@Client.on_callback_query(filters.regex(r"^ord:([^:]+):(\d+)$"))
async def view_order_cb(client: Client, callback_query: CallbackQuery):
    """View order details."""
    mongo_id = callback_query.matches[0].group(1)
    page = callback_query.matches[0].group(2)
    
    order = await get_order_by_id(mongo_id)
    if not order or order["user_id"] != callback_query.from_user.id:
        await callback_query.answer("Order not found.", show_alert=True)
        return

    from bot.models.order import get_status_badge
    badge = get_status_badge(order.get("status", ""))

    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **Order Status**\n\n"
        f"Service:     {order.get('service_name')}\n"
        f"URL:         {order.get('url')}\n"
        f"Quantity:    {order.get('quantity'):,}\n"
        f"Cost:        {format_currency(order.get('user_cost'))}\n\n"
        f"Order ID:    `{order.get('provider_order_id', 'N/A')}`\n"
        f"Status:      {order.get('status')} {badge}\n"
        f"Charge:      {format_currency(order.get('charge', 0))}\n"
        f"Start Count: {order.get('start_count', 0):,}\n"
        f"Remains:     {order.get('remains', 0):,}\n"
        f"Created:     {format_datetime(order.get('created_at'))}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    kb = order_detail_keyboard(order, back_target=f"my_orders:{page}")
    await callback_query.edit_message_text(text, reply_markup=kb)


@Client.on_callback_query(filters.regex(r"^refresh_order:(.*)$"))
async def refresh_order_cb(client: Client, callback_query: CallbackQuery):
    """Manually refresh order status."""
    mongo_id = callback_query.matches[0].group(1)
    
    updated_order = await refresh_order_status(mongo_id)
    if not updated_order:
        await callback_query.answer("Failed to refresh status.", show_alert=True)
        return
        
    await callback_query.answer("Status refreshed.")
    
    # Find the page we were on from the previous callback_data
    # We don't have it here directly, default to 1
    page = 1
    if callback_query.message.reply_markup:
        for row in callback_query.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("back:my_orders:"):
                    page = btn.callback_data.split(":")[-1]
    
    from bot.models.order import get_status_badge
    badge = get_status_badge(updated_order.get("status", ""))

    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **Order Status**\n\n"
        f"Service:     {updated_order.get('service_name')}\n"
        f"URL:         {updated_order.get('url')}\n"
        f"Quantity:    {updated_order.get('quantity'):,}\n"
        f"Cost:        {format_currency(updated_order.get('user_cost'))}\n\n"
        f"Order ID:    `{updated_order.get('provider_order_id', 'N/A')}`\n"
        f"Status:      {updated_order.get('status')} {badge}\n"
        f"Charge:      {format_currency(updated_order.get('charge', 0))}\n"
        f"Start Count: {updated_order.get('start_count', 0):,}\n"
        f"Remains:     {updated_order.get('remains', 0):,}\n"
        f"Created:     {format_datetime(updated_order.get('created_at'))}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    kb = order_detail_keyboard(updated_order, back_target=f"my_orders:{page}")
    
    try:
        await callback_query.edit_message_text(text, reply_markup=kb)
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^refill:(.*)$"))
async def refill_order_cb(client: Client, callback_query: CallbackQuery):
    """Request order refill."""
    mongo_id = callback_query.matches[0].group(1)
    success, msg = await request_refill(mongo_id)
    await callback_query.answer(msg, show_alert=True)


@Client.on_callback_query(filters.regex(r"^cancel_order:(.*)$"))
async def request_cancel_order_cb(client: Client, callback_query: CallbackQuery):
    """Request order cancellation."""
    mongo_id = callback_query.matches[0].group(1)
    success, msg = await request_cancel(mongo_id)
    await callback_query.answer(msg, show_alert=True)
    if success:
        # Refresh the UI
        await refresh_order_cb(client, callback_query)


# ---------------------------------------------------------------------------
# Track Order (By ID)
# ---------------------------------------------------------------------------

@Client.on_callback_query(filters.regex(r"^track_order$"))
async def track_order_cb(client: Client, callback_query: CallbackQuery):
    """Start order tracking by ID wizard."""
    user_id = callback_query.from_user.id
    
    await set_wizard_state(user_id, {
        "flow": "track_order",
        "msg_id": callback_query.message.id,
    })
    
    await callback_query.edit_message_text(
        "📊 **Track Order**\n\nPlease enter the **Order ID**:",
        reply_markup=add_footer([], "home")
    )
    await callback_query.answer()


@Client.on_message(filters.text & filters.private, group=1)
async def _track_order_handler_fallback(client: Client, message: Message):
    pass

async def _handle_track_order_wizard(client: Client, message: Message, state: dict):
    user_id = message.from_user.id
    order_id_str = message.text.strip()
    
    try:
        await message.delete()
    except Exception:
        pass
        
    order = await get_order_by_provider_id(order_id_str)
    if not order:
        try:
            await client.edit_message_text(
                chat_id=user_id,
                message_id=state["msg_id"],
                text="❌ **Order not found.**\n\nPlease check the Order ID and try again:",
                reply_markup=add_footer([], "home")
            )
        except Exception:
            pass
        return
        
    await clear_wizard_state(user_id)
    
    from bot.models.order import get_status_badge
    badge = get_status_badge(order.get("status", ""))

    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **Order Status**\n\n"
        f"Service:     {order.get('service_name')}\n"
        f"URL:         {order.get('url')}\n"
        f"Quantity:    {order.get('quantity'):,}\n"
        f"Cost:        {format_currency(order.get('user_cost'))}\n\n"
        f"Order ID:    `{order.get('provider_order_id', 'N/A')}`\n"
        f"Status:      {order.get('status')} {badge}\n"
        f"Charge:      {format_currency(order.get('charge', 0))}\n"
        f"Start Count: {order.get('start_count', 0):,}\n"
        f"Remains:     {order.get('remains', 0):,}\n"
        f"Created:     {format_datetime(order.get('created_at'))}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    kb = order_detail_keyboard(order, back_target="home")
    
    try:
        await client.edit_message_text(
            chat_id=user_id,
            message_id=state["msg_id"],
            text=text,
            reply_markup=kb
        )
    except Exception:
        pass
