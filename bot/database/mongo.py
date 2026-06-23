"""
MongoDB async client via Motor with collection references and index management.
"""

from __future__ import annotations

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING, DESCENDING

from bot.config.settings import get_settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


async def connect_mongo() -> None:
    """Initialize the Motor client and database reference."""
    global _client, _db
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.MONGO_URI)
    _db = _client.get_default_database()
    if _db is None:
        # Fallback: parse db name from URI or use default
        _db = _client["smm_panel"]
    logger.info("MongoDB connected — database=%s", _db.name)
    await ensure_indexes()


async def close_mongo() -> None:
    """Close the Motor client."""
    global _client
    if _client:
        _client.close()
        logger.info("MongoDB connection closed")


def get_db() -> AsyncIOMotorDatabase:
    """Return the database reference. Must call connect_mongo() first."""
    if _db is None:
        raise RuntimeError("MongoDB not connected. Call connect_mongo() first.")
    return _db


# ---------------------------------------------------------------------------
# Collection accessors
# ---------------------------------------------------------------------------

def users_col():
    return get_db()["users"]


def orders_col():
    return get_db()["orders"]


def transactions_col():
    return get_db()["transactions"]


def deposits_col():
    return get_db()["deposits"]


def tickets_col():
    return get_db()["tickets"]


def favorites_col():
    return get_db()["favorites"]


def settings_col():
    return get_db()["settings"]


def broadcast_logs_col():
    return get_db()["broadcast_logs"]


# ---------------------------------------------------------------------------
# Index creation
# ---------------------------------------------------------------------------

async def ensure_indexes() -> None:
    """Create required indexes for all collections."""
    logger.info("Ensuring MongoDB indexes…")

    # orders
    await orders_col().create_indexes([
        IndexModel([("user_id", ASCENDING)]),
        IndexModel([("provider_order_id", ASCENDING)]),
        IndexModel([("status", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
    ])

    # transactions
    await transactions_col().create_indexes([
        IndexModel([("user_id", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
    ])

    # tickets
    await tickets_col().create_indexes([
        IndexModel([("user_id", ASCENDING)]),
        IndexModel([("status", ASCENDING)]),
    ])

    # deposits
    await deposits_col().create_indexes([
        IndexModel([("user_id", ASCENDING)]),
        IndexModel([("status", ASCENDING)]),
    ])

    # favorites — unique compound index
    await favorites_col().create_indexes([
        IndexModel(
            [("user_id", ASCENDING), ("service_id", ASCENDING)],
            unique=True,
        ),
    ])

    logger.info("MongoDB indexes ensured")


async def init_global_settings() -> None:
    """Ensure the global settings document exists with defaults."""
    settings = get_settings()
    existing = await settings_col().find_one({"_id": "global"})
    if not existing:
        await settings_col().insert_one({
            "_id": "global",
            "markup_percent": settings.DEFAULT_MARKUP_PERCENT,
            "maintenance_mode": False,
            "welcome_message": "Welcome to the SMM Panel Bot! 🚀\nOrder social media services quickly and easily.",
            "support_username": "",
        })
        logger.info("Global settings initialized with defaults")


async def get_global_settings() -> dict:
    """Fetch the global settings document."""
    doc = await settings_col().find_one({"_id": "global"})
    if not doc:
        await init_global_settings()
        doc = await settings_col().find_one({"_id": "global"})
    return doc


async def update_global_settings(update: dict) -> None:
    """Update specific fields in the global settings document."""
    await settings_col().update_one(
        {"_id": "global"},
        {"$set": update},
    )
