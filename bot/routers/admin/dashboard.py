"""
Admin dashboard router.
"""

from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.mongo import users_col, orders_col
from bot.keyboards.admin_kb import admin_main_keyboard
from bot.services.ticket_service import count_open_tickets
from bot.services.provider import get_provider
from bot.models.transaction import TransactionType
from bot.models.order import OrderStatus
from bot.utils.formatting import format_currency, format_number
from bot.keyboards.common import add_footer

router = Router(name="admin_dashboard")


@router.callback_query(F.data == "admin")
async def admin_menu_cb(callback_query: CallbackQuery, state: FSMContext):
    """Admin entry point."""
    await state.clear()
        
    await callback_query.message.edit_text(
        "👑 **Admin Panel**\n\nWelcome back. Select an option:",
        reply_markup=admin_main_keyboard()
    )
    await callback_query.answer()


@router.callback_query(F.data == "adm_dashboard")
async def adm_dashboard_cb(callback_query: CallbackQuery):
    """Show aggregate admin statistics."""
    await callback_query.message.edit_text("📊 Loading dashboard...")
    
    # Gathering stats
    total_users = await users_col().count_documents({})
    total_orders = await orders_col().count_documents({})
    completed_orders = await orders_col().count_documents({"status": OrderStatus.COMPLETED.value})
    pending_orders = await orders_col().count_documents({"status": OrderStatus.PENDING.value})
    open_tickets = await count_open_tickets()
    
    # Revenue (sum of all deposits)
    from bot.database.mongo import transactions_col
    pipeline_rev = [
        {"$match": {"type": TransactionType.DEPOSIT.value}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    rev_cursor = transactions_col().aggregate(pipeline_rev)
    rev_list = await rev_cursor.to_list(length=1)
    total_revenue = rev_list[0]["total"] if rev_list else 0.0
    
    # Profit (sum of (user_cost - provider_rate * qty/1000) for non-failed orders)
    pipeline_prof = [
        {"$match": {"status": {"$nin": [OrderStatus.CANCELLED.value]}}},
        {"$project": {
            "profit": {
                "$subtract": [
                    "$user_cost",
                    {"$multiply": [{"$divide": ["$quantity", 1000]}, "$provider_rate"]}
                ]
            }
        }},
        {"$group": {"_id": None, "total_profit": {"$sum": "$profit"}}}
    ]
    prof_cursor = orders_col().aggregate(pipeline_prof)
    prof_list = await prof_cursor.to_list(length=1)
    net_profit = prof_list[0]["total_profit"] if prof_list else 0.0
    
    # Provider Balance
    provider = get_provider()
    try:
        bal_data = await provider.get_balance()
        provider_bal = bal_data.get("balance", "N/A")
        provider_curr = bal_data.get("currency", "USD")
        provider_bal_str = f"{provider_bal} {provider_curr}"
    except Exception:
        provider_bal_str = "Error"
        
    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 **Admin Dashboard**\n\n"
        f"👥 Total Users:       {format_number(total_users)}\n"
        f"📦 Total Orders:      {format_number(total_orders)}\n"
        f"✅ Completed:         {format_number(completed_orders)}\n"
        f"⏳ Pending:           {format_number(pending_orders)}\n"
        f"💰 Total Revenue:     {format_currency(total_revenue)}\n"
        f"📈 Net Profit:        {format_currency(net_profit)}\n"
        f"🎟 Open Tickets:      {format_number(open_tickets)}\n"
        f"🔌 Provider Balance:  {provider_bal_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    await callback_query.message.edit_text(text, reply_markup=add_footer([], "admin"))
    await callback_query.answer()
