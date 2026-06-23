"""
Support ticket data model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class TicketStatus(str, Enum):
    OPEN = "Open"
    REPLIED = "Replied"
    CLOSED = "Closed"


TICKET_STATUS_BADGES = {
    TicketStatus.OPEN: "🟢",
    TicketStatus.REPLIED: "🟡",
    TicketStatus.CLOSED: "🔴",
}


def get_ticket_badge(status: str) -> str:
    """Return the emoji badge for a ticket status string."""
    try:
        return TICKET_STATUS_BADGES.get(TicketStatus(status), "⚪")
    except ValueError:
        return "⚪"


class TicketMessage(BaseModel):
    """A single message within a ticket thread."""

    sender: str = "user"  # "user" or "admin"
    text: str = ""
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_doc(self) -> dict:
        return {
            "sender": self.sender,
            "text": self.text,
            "sent_at": self.sent_at,
        }


class TicketModel(BaseModel):
    """Represents a support ticket."""

    id: Optional[str] = Field(None, alias="_id")
    user_id: int = 0
    subject: str = ""
    status: str = TicketStatus.OPEN.value
    messages: List[dict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        populate_by_name = True

    def to_doc(self) -> dict:
        """Convert to a MongoDB document (without _id for insert)."""
        return {
            "user_id": self.user_id,
            "subject": self.subject,
            "status": self.status,
            "messages": self.messages,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
