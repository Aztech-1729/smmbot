"""
Main application entry point for Aiogram 3.
"""

import asyncio
import logging
import sys

try:
    import uvloop
except ImportError:
    uvloop = None

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder
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

    # 3. Initialize Aiogram Bot and Dispatcher with Redis storage
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = RedisStorage.from_url(settings.REDIS_URL, key_builder=DefaultKeyBuilder(with_destiny=True))
    dp = Dispatcher(storage=storage)

    # 4. Register middlewares and routers
    from bot.middlewares.aiogram_middlewares import AuthMiddleware, AdminMiddleware
    dp.message.outer_middleware(AuthMiddleware())
    dp.callback_query.outer_middleware(AuthMiddleware())

    from bot.routers.start import router as start_router
    from bot.routers.orders import router as orders_router
    from bot.routers.wallet import router as wallet_router
    from bot.routers.support import router as support_router
    from bot.routers.profile import router as profile_router
    from bot.routers.settings import router as settings_router
    from bot.routers.search import router as search_router
    from bot.routers.favorites import router as favorites_router

    from bot.routers.admin.dashboard import router as admin_dashboard_router
    from bot.routers.admin.settings import router as admin_settings_router
    from bot.routers.admin.users import router as admin_users_router
    from bot.routers.admin.finances import router as admin_finances_router
    from bot.routers.admin.orders import router as admin_orders_router
    from bot.routers.admin.tickets import router as admin_tickets_router
    from bot.routers.admin.broadcast import router as admin_broadcast_router

    admin_routers = [
        admin_dashboard_router,
        admin_settings_router,
        admin_users_router,
        admin_finances_router,
        admin_orders_router,
        admin_tickets_router,
        admin_broadcast_router
    ]
    
    for r in admin_routers:
        r.message.middleware(AdminMiddleware())
        r.callback_query.middleware(AdminMiddleware())

    dp.include_routers(
        start_router,
        orders_router,
        wallet_router,
        support_router,
        profile_router,
        settings_router,
        search_router,
        favorites_router,
        *admin_routers
    )

    # 5. Initialize Background Scheduler
    scheduler = AsyncIOScheduler()
    
    # Run order status check every 5 minutes
    scheduler.add_job(
        check_active_orders,
        "interval",
        minutes=5,
        args=[bot],
        id="order_status_checker",
        replace_existing=True,
    )
    
    # Run broadcast queue processor every 30 seconds
    scheduler.add_job(
        process_broadcast_queue,
        "interval",
        seconds=30,
        args=[bot],
        id="broadcast_processor",
        replace_existing=True,
    )
    
    scheduler.start()
    logger.info("APScheduler started")

    # 5. Run the bot
    logger.info("Starting Aiogram Polling...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down...")
    finally:
        logger.info("Stopping services...")
        scheduler.shutdown()
        await bot.session.close()
        await provider.close()
        await close_mongo()
        await close_redis()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    if sys.platform != "win32" and uvloop is not None:
        try:
            uvloop.install()
        except Exception:
            pass
    
    asyncio.run(main())
