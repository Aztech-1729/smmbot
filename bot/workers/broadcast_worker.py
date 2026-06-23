"""
Background worker to process broadcast jobs.
Runs continuously, fetching pending jobs and broadcasting with rate limits.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from pyrogram import Client

from bot.database.mongo import broadcast_logs_col, users_col

logger = logging.getLogger(__name__)


async def process_broadcast_queue(client: Client) -> None:
    """
    Check for pending broadcasts and execute them.
    This runs periodically via APScheduler.
    """
    job = await broadcast_logs_col().find_one_and_update(
        {"status": "pending"},
        {"$set": {"status": "processing"}},
        sort=[("created_at", 1)],
        return_document=True,
    )
    
    if not job:
        return
        
    logger.info("Starting broadcast job: %s", job["_id"])
    
    total_users = 0
    success_count = 0
    failed_count = 0
    
    msg_type = job.get("content_type", "text")
    content = job.get("message", "")
    file_id = job.get("file_id")
    
    # Iterate all users
    cursor = users_col().find({}, {"_id": 1, "is_banned": 1})
    async for user in cursor:
        if user.get("is_banned"):
            continue
            
        total_users += 1
        user_id = user["_id"]
        
        try:
            if msg_type == "text":
                await client.send_message(chat_id=user_id, text=content)
            elif msg_type == "photo":
                await client.send_photo(chat_id=user_id, photo=file_id, caption=content)
            elif msg_type == "video":
                await client.send_video(chat_id=user_id, video=file_id, caption=content)
            elif msg_type == "document":
                await client.send_document(chat_id=user_id, document=file_id, caption=content)
                
            success_count += 1
        except Exception:
            failed_count += 1
            
        # Telegram API rate limit mitigation (~30 msgs per sec max overall, safer to do 10-15)
        await asyncio.sleep(0.05)
        
    # Mark completed
    await broadcast_logs_col().update_one(
        {"_id": job["_id"]},
        {
            "$set": {
                "status": "completed",
                "total_users": total_users,
                "success_count": success_count,
                "failed_count": failed_count,
                "completed_at": datetime.now(timezone.utc),
            }
        }
    )
    
    # Notify the admin who created it
    admin_id = job.get("admin_id")
    if admin_id:
        try:
            await client.send_message(
                chat_id=admin_id,
                text=(
                    f"📢 **Broadcast Completed**\n\n"
                    f"Targeted: {total_users}\n"
                    f"Success:  {success_count}\n"
                    f"Failed:   {failed_count}"
                )
            )
        except Exception:
            pass
            
    logger.info("Broadcast job %s completed.", job["_id"])
