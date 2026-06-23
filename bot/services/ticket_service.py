"""
Support ticket service.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from bson import ObjectId

from bot.database.mongo import tickets_col
from bot.models.ticket import TicketStatus, TicketMessage

logger = logging.getLogger(__name__)


async def create_ticket(user_id: int, subject: str, message_text: str) -> dict:
    """Create a new support ticket with an initial message."""
    now = datetime.now(timezone.utc)
    msg = TicketMessage(sender="user", text=message_text, sent_at=now)

    doc = {
        "user_id": user_id,
        "subject": subject,
        "status": TicketStatus.OPEN.value,
        "messages": [msg.to_doc()],
        "created_at": now,
        "updated_at": now,
    }

    result = await tickets_col().insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info("Ticket created: user=%d, subject=%s", user_id, subject)
    return doc


async def add_user_message(ticket_id: str, text: str) -> Optional[dict]:
    """Add a message from the user to an existing ticket."""
    try:
        oid = ObjectId(ticket_id)
    except Exception:
        return None

    now = datetime.now(timezone.utc)
    msg = TicketMessage(sender="user", text=text, sent_at=now)

    result = await tickets_col().find_one_and_update(
        {"_id": oid},
        {
            "$push": {"messages": msg.to_doc()},
            "$set": {
                "status": TicketStatus.OPEN.value,
                "updated_at": now,
            },
        },
        return_document=True,
    )
    return result


async def add_admin_reply(ticket_id: str, text: str) -> Optional[dict]:
    """Add an admin reply to a ticket."""
    try:
        oid = ObjectId(ticket_id)
    except Exception:
        return None

    now = datetime.now(timezone.utc)
    msg = TicketMessage(sender="admin", text=text, sent_at=now)

    result = await tickets_col().find_one_and_update(
        {"_id": oid},
        {
            "$push": {"messages": msg.to_doc()},
            "$set": {
                "status": TicketStatus.REPLIED.value,
                "updated_at": now,
            },
        },
        return_document=True,
    )
    return result


async def close_ticket(ticket_id: str) -> Optional[dict]:
    """Close a ticket."""
    try:
        oid = ObjectId(ticket_id)
    except Exception:
        return None

    result = await tickets_col().find_one_and_update(
        {"_id": oid},
        {
            "$set": {
                "status": TicketStatus.CLOSED.value,
                "updated_at": datetime.now(timezone.utc),
            },
        },
        return_document=True,
    )
    return result


async def get_ticket_by_id(ticket_id: str) -> Optional[dict]:
    """Fetch a single ticket by ID."""
    try:
        oid = ObjectId(ticket_id)
    except Exception:
        return None
    return await tickets_col().find_one({"_id": oid})


async def get_user_tickets(
    user_id: int,
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[dict], int]:
    """Get paginated tickets for a user, newest first."""
    col = tickets_col()
    total = await col.count_documents({"user_id": user_id})
    skip = (page - 1) * per_page
    cursor = col.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(per_page)
    tix = await cursor.to_list(length=per_page)
    return tix, total


async def get_all_open_tickets(
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[dict], int]:
    """Admin: get all open/replied tickets, paginated."""
    col = tickets_col()
    query = {"status": {"$in": [TicketStatus.OPEN.value, TicketStatus.REPLIED.value]}}
    total = await col.count_documents(query)
    skip = (page - 1) * per_page
    cursor = col.find(query).sort("updated_at", -1).skip(skip).limit(per_page)
    tix = await cursor.to_list(length=per_page)
    return tix, total


async def count_open_tickets() -> int:
    """Count all open/replied tickets."""
    return await tickets_col().count_documents(
        {"status": {"$in": [TicketStatus.OPEN.value, TicketStatus.REPLIED.value]}}
    )
