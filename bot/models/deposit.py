"""
Deposit data model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DepositStatus(str, Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class DepositModel(BaseModel):
    """Represents a deposit request."""

    id: Optional[str] = Field(None, alias="_id")
    user_id: int = 0
    amount: float = 0.00
    transaction_id: str = ""
    screenshot_file_id: Optional[str] = None
    status: str = DepositStatus.PENDING.value
    admin_note: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: Optional[datetime] = None

    class Config:
        populate_by_name = True

    def to_doc(self) -> dict:
        """Convert to a MongoDB document (without _id for insert)."""
        return {
            "user_id": self.user_id,
            "amount": self.amount,
            "transaction_id": self.transaction_id,
            "screenshot_file_id": self.screenshot_file_id,
            "status": self.status,
            "admin_note": self.admin_note,
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
        }
