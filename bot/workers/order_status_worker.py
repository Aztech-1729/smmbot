"""
Background worker to poll active orders and update their status.
Scheduled by APScheduler every 5 minutes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pyrogram import Client

from bot.database.mongo import orders_col, users_col
from bot.models.order import OrderStatus
from bot.services.order_service import get_all_active_orders
from bot.services.provider import get_provider
from bot.services.notification_service import notify_order_status_changed

logger = logging.getLogger(__name__)


async def check_active_orders(client: Client) -> None:
    """
    1. Fetch all active orders from MongoDB.
    2. Batch them in chunks of 100.
    3. Call the multi-status API endpoint.
    4. Update DB and notify users if status changed.
    """
    logger.info("Starting order status check...")
    
    active_orders = await get_all_active_orders()
    if not active_orders:
        logger.debug("No active orders to check.")
        return
        
    provider = get_provider()
    
    # Map to keep track of provider_id -> order doc
    p_id_to_order = {
        str(o.get("provider_order_id")): o 
        for o in active_orders 
        if o.get("provider_order_id")
    }
    
    provider_ids = list(p_id_to_order.keys())
    if not provider_ids:
        return
        
    # Chunk into 100s for the API
    chunk_size = 100
    for i in range(0, len(provider_ids), chunk_size):
        chunk = provider_ids[i:i + chunk_size]
        try:
            status_map = await provider.get_multi_order_status(chunk)
            await _process_status_map(client, status_map, p_id_to_order)
        except Exception as e:
            logger.error("Failed to check order statuses: %s", e)


async def _process_status_map(client: Client, status_map: dict, p_id_to_order: dict) -> None:
    """Process the response from the multi-status API."""
    for p_id, data in status_map.items():
        if "error" in data:
            logger.warning("Error in status response for order %s: %s", p_id, data["error"])
            continue
            
        order = p_id_to_order.get(str(p_id))
        if not order:
            continue
            
        old_status = order.get("status", "")
        new_status = data.get("status", old_status)
        
        # Normalize status
        status_normalization = {
            "pending": "Pending",
            "processing": "Processing",
            "in progress": "In Progress",
            "completed": "Completed",
            "cancelled": "Cancelled",
            "canceled": "Cancelled",
            "partial": "Partial",
        }
        new_status = status_normalization.get(new_status.lower(), new_status)
        
        # If nothing changed except maybe start_count/remains, we still update it silently
        update_data = {
            "status": new_status,
            "start_count": int(data.get("start_count", 0)),
            "remains": int(data.get("remains", 0)),
            "charge": float(data.get("charge", 0)),
            "updated_at": datetime.now(timezone.utc),
        }
        
        await orders_col().update_one(
            {"_id": order["_id"]},
            {"$set": update_data}
        )
        
        # If status actually changed, notify user and handle special logic
        if old_status != new_status:
            logger.info("Order %s status changed: %s -> %s", order["_id"], old_status, new_status)
            
            # Update user stats if newly completed
            if new_status == OrderStatus.COMPLETED.value:
                await users_col().update_one(
                    {"_id": order["user_id"]},
                    {"$inc": {"completed_orders": 1}}
                )
                
            # Notify user
            await notify_order_status_changed(
                client=client,
                user_id=order["user_id"],
                order=order,
                old_status=old_status,
                new_status=new_status,
            )
