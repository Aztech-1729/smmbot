"""
Order service — business logic for order lifecycle management.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId

from bot.database.mongo import orders_col, users_col, get_global_settings
from bot.models.order import OrderModel, OrderStatus
from bot.services.provider import get_provider, ProviderAPIError
from bot.services.wallet_service import deduct_balance, credit_balance
from bot.utils.formatting import format_currency

logger = logging.getLogger(__name__)


class InsufficientBalanceError(Exception):
    """Raised when user balance is insufficient for an order."""
    pass


class OrderError(Exception):
    """General order error."""
    pass


def calculate_user_cost(
    quantity: int,
    provider_rate: float,
    markup_percent: int,
) -> float:
    """
    Calculate the cost to the user.
    Formula: (quantity / 1000) × provider_rate × (1 + markup_percent / 100)
    """
    return round((quantity / 1000) * provider_rate * (1 + markup_percent / 100), 2)


async def place_order(
    user_id: int,
    service_id: str,
    url: str,
    quantity: int,
) -> Dict[str, Any]:
    """
    Place a new order end-to-end:
    1. Fetch service details
    2. Calculate cost with markup
    3. Deduct balance atomically
    4. Call provider API
    5. Store order in MongoDB
    """
    provider = get_provider()

    # 1. Get service info
    service = await provider.find_service_by_id(service_id)
    if not service:
        raise OrderError("Service not found.")

    # 2. Get markup and calculate cost
    settings = await get_global_settings()
    markup = settings.get("markup_percent", 50)
    provider_rate = float(service.get("rate", 0))
    user_cost = calculate_user_cost(quantity, provider_rate, markup)

    if user_cost <= 0:
        raise OrderError("Invalid cost calculation.")

    # 3. Deduct balance atomically
    success = await deduct_balance(user_id, user_cost, f"Order: {service.get('name', 'Service')}")
    if not success:
        raise InsufficientBalanceError(
            f"Insufficient balance. Required: {format_currency(user_cost)}"
        )

    # 4. Call provider API
    try:
        result = await provider.add_order(service_id, url, quantity)
    except ProviderAPIError as e:
        # Refund the user on provider failure
        await credit_balance(user_id, user_cost, f"Refund: Order failed — {e.message}")
        raise OrderError(f"Provider error: {e.message}")
    except Exception as e:
        # Refund on any unexpected error
        await credit_balance(user_id, user_cost, f"Refund: Order failed — unexpected error")
        raise OrderError(f"Failed to place order: {str(e)}")

    provider_order_id = str(result.get("order", ""))

    # 5. Store order in MongoDB
    order = OrderModel(
        provider_order_id=provider_order_id,
        user_id=user_id,
        service_id=str(service_id),
        service_name=service.get("name", ""),
        category=service.get("category", ""),
        quantity=quantity,
        url=url,
        provider_rate=provider_rate,
        user_cost=user_cost,
        markup_percent=markup,
        status=OrderStatus.PENDING.value,
    )
    doc = order.to_doc()
    insert_result = await orders_col().insert_one(doc)
    doc["_id"] = insert_result.inserted_id

    # Update user order count
    await users_col().update_one(
        {"_id": user_id},
        {"$inc": {"total_orders": 1}},
    )

    logger.info(
        "Order placed: user=%d, provider_order=%s, cost=%s",
        user_id, provider_order_id, user_cost,
    )
    return doc


async def get_user_orders(
    user_id: int,
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[dict], int]:
    """
    Get paginated orders for a user, newest first.
    Returns (orders, total_count).
    """
    col = orders_col()
    total = await col.count_documents({"user_id": user_id})
    skip = (page - 1) * per_page

    cursor = col.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(per_page)
    orders = await cursor.to_list(length=per_page)
    return orders, total


async def get_order_by_id(order_id: str) -> Optional[dict]:
    """Fetch a single order by MongoDB _id."""
    try:
        oid = ObjectId(order_id)
    except Exception:
        return None
    return await orders_col().find_one({"_id": oid})


async def get_order_by_provider_id(provider_order_id: str) -> Optional[dict]:
    """Fetch a single order by provider order ID."""
    return await orders_col().find_one({"provider_order_id": str(provider_order_id)})


async def refresh_order_status(order_id: str) -> Optional[dict]:
    """
    Refresh order status from the provider and update in DB.
    Returns the updated order or None.
    """
    order = await get_order_by_id(order_id)
    if not order:
        return None

    provider_oid = order.get("provider_order_id")
    if not provider_oid:
        return order

    provider = get_provider()
    try:
        status_data = await provider.get_order_status(provider_oid)
    except ProviderAPIError:
        return order
    except Exception:
        return order

    new_status = status_data.get("status", order.get("status", "Pending"))
    # Normalize status casing
    status_map = {
        "pending": "Pending",
        "processing": "Processing",
        "in progress": "In Progress",
        "completed": "Completed",
        "cancelled": "Cancelled",
        "canceled": "Cancelled",
        "partial": "Partial",
    }
    new_status = status_map.get(new_status.lower(), new_status)

    update_data = {
        "status": new_status,
        "start_count": int(status_data.get("start_count", 0)),
        "remains": int(status_data.get("remains", 0)),
        "charge": float(status_data.get("charge", 0)),
        "updated_at": datetime.now(timezone.utc),
    }

    await orders_col().update_one(
        {"_id": order["_id"]},
        {"$set": update_data},
    )

    # Update completed count if newly completed
    old_status = order.get("status", "")
    if old_status != "Completed" and new_status == "Completed":
        await users_col().update_one(
            {"_id": order["user_id"]},
            {"$inc": {"completed_orders": 1}},
        )

    order.update(update_data)
    return order


async def request_refill(order_id: str) -> Tuple[bool, str]:
    """Request a refill for an order. Returns (success, message)."""
    order = await get_order_by_id(order_id)
    if not order:
        return False, "Order not found."

    provider_oid = order.get("provider_order_id")
    if not provider_oid:
        return False, "No provider order ID found."

    provider = get_provider()
    try:
        result = await provider.refill_order(provider_oid)
        msg = result.get("message", "Refill request submitted successfully.")
        return True, msg
    except ProviderAPIError as e:
        return False, f"Provider error: {e.message}"
    except Exception as e:
        return False, f"Error: {str(e)}"


async def request_cancel(order_id: str) -> Tuple[bool, str]:
    """Request cancellation for an order. Returns (success, message)."""
    order = await get_order_by_id(order_id)
    if not order:
        return False, "Order not found."

    provider_oid = order.get("provider_order_id")
    if not provider_oid:
        return False, "No provider order ID found."

    provider = get_provider()
    try:
        result = await provider.cancel_order(provider_oid)
        msg = result.get("message", "Cancellation request submitted successfully.")
        await orders_col().update_one(
            {"_id": order["_id"]},
            {"$set": {"status": "Cancelled", "updated_at": datetime.now(timezone.utc)}},
        )
        return True, msg
    except ProviderAPIError as e:
        return False, f"Provider error: {e.message}"
    except Exception as e:
        return False, f"Error: {str(e)}"


async def get_all_active_orders() -> List[dict]:
    """Get all orders with active (non-terminal) statuses for the status worker."""
    terminal = [OrderStatus.COMPLETED.value, OrderStatus.CANCELLED.value]
    cursor = orders_col().find({"status": {"$nin": terminal}})
    return await cursor.to_list(length=None)


async def get_all_orders_paginated(
    page: int = 1,
    per_page: int = 10,
    status_filter: Optional[str] = None,
    user_filter: Optional[int] = None,
) -> Tuple[List[dict], int]:
    """Admin: get all orders with optional filters, paginated."""
    query: dict = {}
    if status_filter:
        query["status"] = status_filter
    if user_filter:
        query["user_id"] = user_filter

    col = orders_col()
    total = await col.count_documents(query)
    skip = (page - 1) * per_page
    cursor = col.find(query).sort("created_at", -1).skip(skip).limit(per_page)
    orders = await cursor.to_list(length=per_page)
    return orders, total
