"""
Order placement and tracking router.
"""

from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.mongo import get_global_settings
from bot.keyboards.order_kb import (
    categories_keyboard, service_list_keyboard, service_detail_keyboard,
    order_confirm_keyboard, order_detail_keyboard
)
from bot.keyboards.common import add_footer
from bot.states import OrderWizard
from bot.services.provider import get_provider
from bot.services.order_service import (
    calculate_user_cost, place_order, get_user_orders, get_order_by_id,
    get_order_by_provider_id, refresh_order_status, request_refill, request_cancel, InsufficientBalanceError, OrderError
)
from bot.services.wallet_service import get_balance
from bot.utils.formatting import format_currency, format_datetime, SEPARATOR
from bot.utils.validators import validate_url, validate_quantity

logger = logging.getLogger(__name__)

router = Router(name="orders")

# ---------------------------------------------------------------------------
# New Order Flow
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "new_order")
async def new_order_cb(callback_query: CallbackQuery, state: FSMContext):
    """Show categories."""
    await state.clear()

    provider = get_provider()
    try:
        grouped = await provider.get_services_by_category()
    except Exception as e:
        await callback_query.answer(f"Failed to fetch services: {e}", show_alert=True)
        return

    categories = list(grouped.keys())
    kb = categories_keyboard(categories)

    await callback_query.message.edit_text(
        "📦 **Select a Category**",
        reply_markup=kb
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("cat:"))
async def category_cb(callback_query: CallbackQuery, state: FSMContext):
    """Show services for a category."""
    await state.clear()
    
    cat_name = callback_query.data.split(":", 1)[1]
    
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

    text, kb = service_list_keyboard(grouped[full_cat], full_cat, page=1, markup_percent=markup)
    
    try:
        await callback_query.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback_query.answer()


@router.callback_query(F.data.startswith("svcpg:"))
async def service_page_cb(callback_query: CallbackQuery):
    """Paginate services."""
    parts = callback_query.data.split(":")
    cat_name = parts[1]
    page = int(parts[2])
    
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
        await callback_query.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback_query.answer()


@router.callback_query(F.data.startswith("svc:"))
async def service_detail_cb(callback_query: CallbackQuery, state: FSMContext):
    """Show service details."""
    user_id = callback_query.from_user.id
    await state.clear()
    svc_id = callback_query.data.split(":")[1]
    
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
    
    await callback_query.message.edit_text(text, reply_markup=kb)
    await callback_query.answer()


@router.callback_query(F.data.startswith("place:"))
async def place_order_cb(callback_query: CallbackQuery, state: FSMContext):
    """Start the order placement wizard."""
    svc_id = callback_query.data.split(":")[1]
    
    provider = get_provider()
    service = await provider.find_service_by_id(svc_id)
    
    if not service:
        await callback_query.answer("Service not found.", show_alert=True)
        return

    # Store wizard state
    await state.set_state(OrderWizard.waiting_for_link)
    await state.update_data(
        service_id=svc_id,
        service_name=service.get("name", ""),
        rate=float(service.get("rate", 0)),
        min=int(service.get("min", 0)),
        max=int(service.get("max", 0)),
        msg_id=callback_query.message.message_id,
    )

    await callback_query.message.edit_text(
        f"🔗 **Enter the target URL** for `{service.get('name')}`\n\n"
        "Please provide the full URL (e.g., https://instagram.com/p/...).",
        reply_markup=add_footer([], f"svc:{svc_id}")
    )
    await callback_query.answer()


@router.message(OrderWizard.waiting_for_link)
async def process_order_url(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    try:
        await message.delete()
    except Exception:
        pass

    url = message.text.strip()
    if not validate_url(url):
        try:
            await message.bot.edit_message_text(
                chat_id=user_id,
                message_id=data["msg_id"],
                text="❌ **Invalid URL format.**\n\nPlease enter a valid URL starting with http:// or https://",
                reply_markup=add_footer([], f"svc:{data['service_id']}")
            )
        except Exception:
            pass
        return
        
    await state.update_data(url=url)
    await state.set_state(OrderWizard.waiting_for_quantity)
    
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text=(
                f"🔢 **Enter Quantity**\n\n"
                f"URL: `{url}`\n"
                f"Min: {data['min']:,} | Max: {data['max']:,}\n\n"
                "Please type the number you want to order:"
            ),
            reply_markup=add_footer([], f"place:{data['service_id']}")
        )
    except Exception:
        pass


@router.message(OrderWizard.waiting_for_quantity)
async def process_order_quantity(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    try:
        await message.delete()
    except Exception:
        pass

    qty_str = message.text.strip()
    is_valid, qty, err = validate_quantity(qty_str, data["min"], data["max"])
    
    if not is_valid:
        try:
            await message.bot.edit_message_text(
                chat_id=user_id,
                message_id=data["msg_id"],
                text=f"{err}\n\nPlease try again:",
                reply_markup=add_footer([], f"place:{data['service_id']}")
            )
        except Exception:
            pass
        return
        
    await state.update_data(quantity=qty)
    await state.set_state(OrderWizard.confirm_order)
    
    # Calculate cost
    settings = await get_global_settings()
    markup = settings.get("markup_percent", 50)
    user_cost = calculate_user_cost(qty, data["rate"], markup)
    await state.update_data(user_cost=user_cost)
    
    balance = await get_balance(user_id)
    
    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛒 **Order Summary**\n\n"
        f"Service:   {data['service_name']}\n"
        f"Quantity:  {qty:,}\n"
        f"URL:       {data['url']}\n"
        f"Price:     {format_currency(user_cost)}\n"
        f"Balance:   {format_currency(balance)} → {format_currency(balance - user_cost)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    try:
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text=text,
            reply_markup=order_confirm_keyboard()
        )
    except Exception:
        pass


@router.callback_query(OrderWizard.confirm_order, F.data == "order_confirm")
async def confirm_order_cb(callback_query: CallbackQuery, state: FSMContext):
    """Finalize order placement."""
    user_id = callback_query.from_user.id
    data = await state.get_data()
    
    await callback_query.message.edit_text("⏳ Processing order...")
    
    try:
        order = await place_order(
            user_id=user_id,
            service_id=data["service_id"],
            url=data["url"],
            quantity=data["quantity"],
        )
        await state.clear()
        
        await callback_query.message.edit_text(
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
        from aiogram.types import InlineKeyboardMarkup
        await callback_query.message.edit_text(
            f"❌ **Failed**\n\n{str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb.inline_keyboard)
        )
    except OrderError as e:
        await callback_query.message.edit_text(
            f"❌ **Order Failed**\n\n{str(e)}\n\nAny deducted balance has been refunded.",
            reply_markup=add_footer([], "new_order")
        )
    except Exception:
        logger.exception("Order error")
        await callback_query.message.edit_text(
            "❌ **System Error**\n\nFailed to place order. Please try again later.",
            reply_markup=add_footer([], "new_order")
        )


@router.callback_query(F.data == "order_cancel")
async def cancel_order_cb(callback_query: CallbackQuery, state: FSMContext):
    """Cancel order placement."""
    await state.clear()
    await callback_query.answer("Order cancelled.")
    
    # Return to home
    from bot.routers.start import home_cb
    await home_cb(callback_query, {}, state)


# ---------------------------------------------------------------------------
# My Orders
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("my_orders:"))
async def my_orders_cb(callback_query: CallbackQuery):
    """List user orders."""
    user_id = callback_query.from_user.id
    page = int(callback_query.data.split(":")[1])
    
    orders, total = await get_user_orders(user_id, page=page, per_page=10)
    
    if not orders:
        await callback_query.message.edit_text(
            "You don't have any orders yet.",
            reply_markup=add_footer([], "home")
        )
        return

    from bot.models.order import get_status_badge
    from bot.utils.pagination import Paginator
    
    p = Paginator(list(range(total)), page=page, per_page=10)
    text = f"📦 **My Orders** (Page {page}/{p.total_pages})\n\n"
    
    kb_rows = []
    for o in orders:
        badge = get_status_badge(o.get("status", ""))
        name = o.get("service_name", "Service")
        short_name = name[:20] + "…" if len(name) > 20 else name
        btn_text = f"{badge} {short_name} — {o.get('quantity')} — {format_currency(o.get('user_cost'))}"
        kb_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"ord:{str(o['_id'])}:{page}", style="primary")])

    nav = p.get_nav_buttons("my_orders")
    if nav:
        kb_rows.append(nav)
        
    kb_rows.append(add_footer([], "home").inline_keyboard[0])
    
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))


@router.callback_query(F.data.startswith("ord:"))
async def view_order_cb(callback_query: CallbackQuery):
    """View order details."""
    parts = callback_query.data.split(":")
    mongo_id = parts[1]
    page = parts[2]
    
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
    await callback_query.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.startswith("refresh_order:"))
async def refresh_order_cb(callback_query: CallbackQuery):
    """Manually refresh order status."""
    mongo_id = callback_query.data.split(":")[1]
    
    updated_order = await refresh_order_status(mongo_id)
    if not updated_order:
        await callback_query.answer("Failed to refresh status.", show_alert=True)
        return
        
    await callback_query.answer("Status refreshed.")
    
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
        await callback_query.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data.startswith("refill:"))
async def refill_order_cb(callback_query: CallbackQuery):
    """Request order refill."""
    mongo_id = callback_query.data.split(":")[1]
    success, msg = await request_refill(mongo_id)
    await callback_query.answer(msg, show_alert=True)


@router.callback_query(F.data.startswith("cancel_order:"))
async def request_cancel_order_cb(callback_query: CallbackQuery):
    """Request order cancellation."""
    mongo_id = callback_query.data.split(":")[1]
    success, msg = await request_cancel(mongo_id)
    await callback_query.answer(msg, show_alert=True)
    if success:
        await refresh_order_cb(callback_query)


# ---------------------------------------------------------------------------
# Track Order (By ID)
# ---------------------------------------------------------------------------

class TrackWizard(StatesGroup):
    waiting_for_id = State()

@router.callback_query(F.data == "track_order")
async def track_order_cb(callback_query: CallbackQuery, state: FSMContext):
    """Start order tracking by ID wizard."""
    await state.set_state(TrackWizard.waiting_for_id)
    await state.update_data(msg_id=callback_query.message.message_id)
    
    await callback_query.message.edit_text(
        "📊 **Track Order**\n\nPlease enter the **Order ID**:",
        reply_markup=add_footer([], "home")
    )
    await callback_query.answer()


@router.message(TrackWizard.waiting_for_id)
async def handle_track_order_wizard(message: Message, state: FSMContext):
    user_id = message.from_user.id
    order_id_str = message.text.strip()
    data = await state.get_data()
    
    try:
        await message.delete()
    except Exception:
        pass
        
    order = await get_order_by_provider_id(order_id_str)
    if not order:
        try:
            await message.bot.edit_message_text(
                chat_id=user_id,
                message_id=data["msg_id"],
                text="❌ **Order not found.**\n\nPlease check the Order ID and try again:",
                reply_markup=add_footer([], "home")
            )
        except Exception:
            pass
        return
        
    await state.clear()
    
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
        await message.bot.edit_message_text(
            chat_id=user_id,
            message_id=data["msg_id"],
            text=text,
            reply_markup=kb
        )
    except Exception:
        pass
