"""
Application settings loaded from environment variables via Pydantic BaseSettings.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings
from pydantic import field_validator

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Central configuration loaded from .env or environment variables."""

    # Telegram
    BOT_TOKEN: str

    # MongoDB
    MONGO_URI: str = "mongodb://mongo:27017/smm_panel"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Admin Telegram user IDs (comma-separated in env)
    ADMIN_IDS: List[int] = []

    # Provider API
    PROVIDER_API_KEY: str
    PROVIDER_API_URL: str = "https://themainsmmprovider.com/api/v2"

    # Business config
    DEFAULT_MARKUP_PERCENT: int = 50

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(uid.strip()) for uid in v.split(",") if uid.strip()]
        elif isinstance(v, int):
            return [v]
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    settings = Settings()
    logger.info(
        "Settings loaded — admins=%s, provider_url=%s, markup=%d%%",
        settings.ADMIN_IDS,
        settings.PROVIDER_API_URL,
        settings.DEFAULT_MARKUP_PERCENT,
    )
    return settings
