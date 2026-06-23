"""
User data model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class UserModel(BaseModel):
    """Represents a user in the system."""

    id: int = Field(..., alias="_id", description="Telegram user ID")
    username: Optional[str] = None
    first_name: str = ""
    balance: float = 0.00
    currency: str = "INR"
    language: str = "en"
    notifications_enabled: bool = True
    total_orders: int = 0
    completed_orders: int = 0
    is_banned: bool = False
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        populate_by_name = True

    def to_doc(self) -> dict:
        """Convert to a MongoDB document."""
        return {
            "_id": self.id,
            "username": self.username,
            "first_name": self.first_name,
            "balance": self.balance,
            "currency": self.currency,
            "language": self.language,
            "notifications_enabled": self.notifications_enabled,
            "total_orders": self.total_orders,
            "completed_orders": self.completed_orders,
            "is_banned": self.is_banned,
            "joined_at": self.joined_at,
        }
