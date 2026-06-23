"""
Transaction data model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    DEDUCTION = "deduction"
    REFUND = "refund"
    ADMIN_ADJUSTMENT = "admin_adjustment"


class TransactionModel(BaseModel):
    """Represents a wallet transaction."""

    id: Optional[str] = Field(None, alias="_id")
    user_id: int = 0
    type: str = TransactionType.DEPOSIT.value
    amount: float = 0.00
    description: str = ""
    reference_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        populate_by_name = True

    def to_doc(self) -> dict:
        """Convert to a MongoDB document (without _id for insert)."""
        return {
            "user_id": self.user_id,
            "type": self.type,
            "amount": self.amount,
            "description": self.description,
            "reference_id": self.reference_id,
            "created_at": self.created_at,
        }
