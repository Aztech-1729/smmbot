"""
Wallet service — balance management, deposits, and transactions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from bson import ObjectId

from bot.database.mongo import users_col, transactions_col, deposits_col
from bot.models.transaction import TransactionType
from bot.models.deposit import DepositStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Balance operations (atomic)
# ---------------------------------------------------------------------------

async def get_balance(user_id: int) -> float:
    """Get the current balance for a user."""
    user = await users_col().find_one({"_id": user_id}, {"balance": 1})
    if not user:
        return 0.0
    return float(user.get("balance", 0))


async def deduct_balance(user_id: int, amount: float, description: str = "") -> bool:
    """
    Atomically deduct balance from a user.
    Uses $gte filter to ensure balance is sufficient.
    Returns True if successful, False if insufficient.
    """
    result = await users_col().update_one(
        {"_id": user_id, "balance": {"$gte": amount}},
        {"$inc": {"balance": -amount}},
    )

    if result.modified_count == 0:
        logger.warning(
            "Balance deduction failed: user=%d, amount=%s (insufficient)",
            user_id, amount,
        )
        return False

    # Log transaction
    await transactions_col().insert_one({
        "user_id": user_id,
        "type": TransactionType.DEDUCTION.value,
        "amount": -amount,
        "description": description,
        "created_at": datetime.now(timezone.utc),
    })

    logger.info("Balance deducted: user=%d, amount=%s", user_id, amount)
    return True


async def credit_balance(
    user_id: int,
    amount: float,
    description: str = "",
    tx_type: str = TransactionType.DEPOSIT.value,
    reference_id: Optional[str] = None,
) -> bool:
    """Credit balance to a user and log the transaction."""
    result = await users_col().update_one(
        {"_id": user_id},
        {"$inc": {"balance": amount}},
    )

    if result.modified_count == 0:
        logger.warning("Balance credit failed: user=%d, amount=%s", user_id, amount)
        return False

    await transactions_col().insert_one({
        "user_id": user_id,
        "type": tx_type,
        "amount": amount,
        "description": description,
        "reference_id": reference_id,
        "created_at": datetime.now(timezone.utc),
    })

    logger.info("Balance credited: user=%d, amount=%s", user_id, amount)
    return True


async def admin_adjust_balance(
    user_id: int,
    amount: float,
    reason: str = "Admin adjustment",
) -> bool:
    """Admin balance adjustment (can be positive or negative)."""
    result = await users_col().update_one(
        {"_id": user_id},
        {"$inc": {"balance": amount}},
    )

    if result.modified_count == 0:
        return False

    await transactions_col().insert_one({
        "user_id": user_id,
        "type": TransactionType.ADMIN_ADJUSTMENT.value,
        "amount": amount,
        "description": reason,
        "created_at": datetime.now(timezone.utc),
    })

    logger.info(
        "Admin balance adjustment: user=%d, amount=%s, reason=%s",
        user_id, amount, reason,
    )
    return True


# ---------------------------------------------------------------------------
# Transaction queries
# ---------------------------------------------------------------------------

async def get_transactions(
    user_id: int,
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[dict], int]:
    """Get paginated transactions for a user, newest first."""
    col = transactions_col()
    total = await col.count_documents({"user_id": user_id})
    skip = (page - 1) * per_page
    cursor = col.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(per_page)
    txns = await cursor.to_list(length=per_page)
    return txns, total


async def get_all_transactions(
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[dict], int]:
    """Admin: get all transactions paginated."""
    col = transactions_col()
    total = await col.count_documents({})
    skip = (page - 1) * per_page
    cursor = col.find().sort("created_at", -1).skip(skip).limit(per_page)
    txns = await cursor.to_list(length=per_page)
    return txns, total


# ---------------------------------------------------------------------------
# Deposit operations
# ---------------------------------------------------------------------------

async def create_deposit(
    user_id: int,
    amount: float,
    transaction_id: str,
    screenshot_file_id: Optional[str] = None,
) -> dict:
    """Create a new deposit request."""
    doc = {
        "user_id": user_id,
        "amount": amount,
        "transaction_id": transaction_id,
        "screenshot_file_id": screenshot_file_id,
        "status": DepositStatus.PENDING.value,
        "admin_note": None,
        "created_at": datetime.now(timezone.utc),
        "reviewed_at": None,
    }
    result = await deposits_col().insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info("Deposit created: user=%d, amount=%s, txn=%s", user_id, amount, transaction_id)
    return doc


async def approve_deposit(deposit_id: str) -> Optional[dict]:
    """
    Approve a pending deposit:
    1. Update deposit status
    2. Credit user balance
    3. Log transaction
    """
    try:
        oid = ObjectId(deposit_id)
    except Exception:
        return None

    deposit = await deposits_col().find_one({"_id": oid})
    if not deposit or deposit["status"] != DepositStatus.PENDING.value:
        return None

    # Update deposit status
    await deposits_col().update_one(
        {"_id": oid},
        {
            "$set": {
                "status": DepositStatus.APPROVED.value,
                "reviewed_at": datetime.now(timezone.utc),
            }
        },
    )

    # Credit user balance
    await credit_balance(
        user_id=deposit["user_id"],
        amount=deposit["amount"],
        description=f"Deposit approved (TXN: {deposit['transaction_id']})",
        tx_type=TransactionType.DEPOSIT.value,
        reference_id=str(oid),
    )

    deposit["status"] = DepositStatus.APPROVED.value
    logger.info("Deposit approved: id=%s, user=%d, amount=%s", deposit_id, deposit["user_id"], deposit["amount"])
    return deposit


async def reject_deposit(deposit_id: str, admin_note: str = "") -> Optional[dict]:
    """Reject a pending deposit with an optional admin note."""
    try:
        oid = ObjectId(deposit_id)
    except Exception:
        return None

    deposit = await deposits_col().find_one({"_id": oid})
    if not deposit or deposit["status"] != DepositStatus.PENDING.value:
        return None

    await deposits_col().update_one(
        {"_id": oid},
        {
            "$set": {
                "status": DepositStatus.REJECTED.value,
                "admin_note": admin_note or "No reason provided",
                "reviewed_at": datetime.now(timezone.utc),
            }
        },
    )

    deposit["status"] = DepositStatus.REJECTED.value
    deposit["admin_note"] = admin_note
    logger.info("Deposit rejected: id=%s, user=%d", deposit_id, deposit["user_id"])
    return deposit


async def get_user_deposits(
    user_id: int,
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[dict], int]:
    """Get paginated deposits for a user."""
    col = deposits_col()
    total = await col.count_documents({"user_id": user_id})
    skip = (page - 1) * per_page
    cursor = col.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(per_page)
    deps = await cursor.to_list(length=per_page)
    return deps, total


async def get_deposits_by_status(
    status: str,
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[dict], int]:
    """Admin: get deposits filtered by status, paginated."""
    col = deposits_col()
    total = await col.count_documents({"status": status})
    skip = (page - 1) * per_page
    cursor = col.find({"status": status}).sort("created_at", -1).skip(skip).limit(per_page)
    deps = await cursor.to_list(length=per_page)
    return deps, total


async def get_deposit_by_id(deposit_id: str) -> Optional[dict]:
    """Fetch a single deposit by ID."""
    try:
        oid = ObjectId(deposit_id)
    except Exception:
        return None
    return await deposits_col().find_one({"_id": oid})
