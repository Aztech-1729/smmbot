"""
Main application entry point.
"""

import asyncio
import logging
import sys

try:
    import uvloop
except ImportError:
    uvloop = None
from pyrogram import Client
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config.settings import get_settings
from bot.database.mongo import connect_mongo, close_mongo, init_global_settings
from bot.database.redis import connect_redis, close_redis
from bot.services.provider import get_provider
from bot.workers.order_status_worker import check_active_orders
from bot.workers.broadcast_worker import process_broadcast_queue

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def main():
    """Application startup and runtime management."""
    settings = get_settings()

    # 1. Initialize databases
    await connect_mongo()
    await connect_redis()
    await init_global_settings()

    # 2. Warm up provider cache
    provider = get_provider()
    try:
        await provider.get_services()
        await provider.get_balance()
    except Exception as e:
        logger.warning("Initial provider cache warmup failed: %s", e)

    # 3. Initialize Pyrogram client
    # We pass the plugins dict to autoload all routers inside bot.routers
    client = Client(
        name="smm_panel_bot",
        bot_token=settings.BOT_TOKEN,
        api_id=settings.API_ID,
        api_hash=settings.API_HASH,
        plugins=dict(root="bot.routers"),
        in_memory=True,   # We don't need persistent sessions for a bot token
    )

    # 4. Initialize Background Scheduler
    scheduler = AsyncIOScheduler()
    
    # Run order status check every 5 minutes
    scheduler.add_job(
        check_active_orders,
        "interval",
        minutes=5,
        args=[client],
        id="order_status_checker",
        replace_existing=True,
    )
    
    # Run broadcast queue processor every 30 seconds
    scheduler.add_job(
        process_broadcast_queue,
        "interval",
        seconds=30,
        args=[client],
        id="broadcast_processor",
        replace_existing=True,
    )
    
    scheduler.start()
    logger.info("APScheduler started")

    # 5. Run the bot
    logger.info("Starting Pyrogram client...")
    try:
        await client.start()
        logger.info("Bot started successfully. Username: @%s", client.me.username)
        
        # Block forever
        from pyrogram import idle
        await idle()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down...")
    finally:
        logger.info("Stopping services...")
        scheduler.shutdown()
        if client.is_connected:
            await client.stop()
        await provider.close()
        await close_mongo()
        await close_redis()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    # Use uvloop for maximum asyncio performance
    if sys.platform != "win32":
        try:
            import uvloop
            uvloop.install()
        except ImportError:
            pass
    
    asyncio.run(main())
