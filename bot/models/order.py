"""
Order data model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    PENDING = "Pending"
    PROCESSING = "Processing"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    PARTIAL = "Partial"


# Status badge mapping
STATUS_BADGES = {
    OrderStatus.COMPLETED: "🟢",
    OrderStatus.PROCESSING: "🟡",
    OrderStatus.IN_PROGRESS: "🔵",
    OrderStatus.CANCELLED: "🔴",
    OrderStatus.PENDING: "⚪",
    OrderStatus.PARTIAL: "🟠",
}


def get_status_badge(status: str) -> str:
    """Return the emoji badge for an order status string."""
    try:
        return STATUS_BADGES.get(OrderStatus(status), "⚪")
    except ValueError:
        return "⚪"


class OrderModel(BaseModel):
    """Represents an order in the system."""

    id: Optional[str] = Field(None, alias="_id")
    provider_order_id: Optional[str] = None
    user_id: int = 0
    service_id: str = ""
    service_name: str = ""
    category: str = ""
    quantity: int = 0
    url: str = ""
    provider_rate: float = 0.00
    user_cost: float = 0.00
    markup_percent: int = 0
    status: str = OrderStatus.PENDING.value
    start_count: int = 0
    remains: int = 0
    charge: float = 0.00
    refill_supported: bool = False
    cancel_supported: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        populate_by_name = True

    def to_doc(self) -> dict:
        """Convert to a MongoDB document (without _id for insert)."""
        return {
            "provider_order_id": self.provider_order_id,
            "user_id": self.user_id,
            "service_id": self.service_id,
            "service_name": self.service_name,
            "category": self.category,
            "quantity": self.quantity,
            "url": self.url,
            "provider_rate": self.provider_rate,
            "user_cost": self.user_cost,
            "markup_percent": self.markup_percent,
            "status": self.status,
            "start_count": self.start_count,
            "remains": self.remains,
            "charge": self.charge,
            "refill_supported": self.refill_supported,
            "cancel_supported": self.cancel_supported,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
