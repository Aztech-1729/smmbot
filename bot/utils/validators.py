"""
Input validation utilities.
"""

from __future__ import annotations

import re
from typing import Tuple, Optional

# URL pattern — accepts http/https URLs
_URL_PATTERN = re.compile(
    r"^https?://"
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
    r"localhost|"
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    r"(?::\d+)?"
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)


def validate_url(url: str) -> bool:
    """Validate whether a string is a properly formatted URL."""
    if not url or not isinstance(url, str):
        return False
    return bool(_URL_PATTERN.match(url.strip()))


def validate_quantity(
    qty_str: str, min_val: int, max_val: int
) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Validate a quantity string.
    Returns (is_valid, parsed_quantity, error_message).
    """
    try:
        qty = int(qty_str.strip().replace(",", ""))
    except (ValueError, AttributeError):
        return False, None, "❌ Please enter a valid number."

    if qty < min_val:
        return False, None, f"❌ Minimum quantity is {min_val:,}."

    if qty > max_val:
        return False, None, f"❌ Maximum quantity is {max_val:,}."

    return True, qty, None


def validate_amount(amount_str: str, min_val: float = 1.0) -> Tuple[bool, Optional[float], Optional[str]]:
    """
    Validate a monetary amount string.
    Returns (is_valid, parsed_amount, error_message).
    """
    try:
        amount = float(amount_str.strip().replace(",", ""))
    except (ValueError, AttributeError):
        return False, None, "❌ Please enter a valid amount."

    if amount < min_val:
        return False, None, f"❌ Minimum amount is {min_val:.2f}."

    if amount > 1_000_000:
        return False, None, "❌ Amount too large."

    return True, round(amount, 2), None


def sanitize_text(text: str, max_length: int = 500) -> str:
    """Sanitize user input text — strip and truncate."""
    if not text or not isinstance(text, str):
        return ""
    return text.strip()[:max_length]
