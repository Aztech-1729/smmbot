"""
Broadcast log data model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class BroadcastLogModel(BaseModel):
    """Represents a broadcast log entry."""

    id: Optional[str] = Field(None, alias="_id")
    admin_id: int = 0
    content_type: str = "text"  # text | photo | video | document
    message: str = ""
    total_users: int = 0
    success_count: int = 0
    failed_count: int = 0
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        populate_by_name = True

    def to_doc(self) -> dict:
        """Convert to a MongoDB document (without _id for insert)."""
        return {
            "admin_id": self.admin_id,
            "content_type": self.content_type,
            "message": self.message,
            "total_users": self.total_users,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "sent_at": self.sent_at,
        }
