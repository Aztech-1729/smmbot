"""
Formatting utilities for currency, numbers, and dates.
"""

from __future__ import annotations

from datetime import datetime
from typing import Union

# Visual separator used across all detail views
SEPARATOR = "━━━━━━━━━━━━━━━━━━━━━━━━"


def format_currency(amount: Union[float, int], currency: str = "INR") -> str:
    """
    Format an amount with currency symbol.
    Uses Indian numbering system for INR (e.g. ₹1,24,500.00).
    """
    symbol_map = {
        "INR": "₹",
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
    }
    symbol = symbol_map.get(currency, currency + " ")

    if currency == "INR":
        return f"{symbol}{_indian_format(amount)}"
    else:
        return f"{symbol}{amount:,.2f}"


def _indian_format(amount: Union[float, int]) -> str:
    """Format a number in Indian numbering system (e.g., 1,24,500.00)."""
    amount = float(amount)
    is_negative = amount < 0
    amount = abs(amount)

    integer_part = int(amount)
    decimal_part = f"{amount:.2f}".split(".")[1]

    s = str(integer_part)
    if len(s) <= 3:
        formatted = s
    else:
        last_three = s[-3:]
        remaining = s[:-3]
        # Group remaining digits in pairs from right
        groups = []
        while remaining:
            groups.append(remaining[-2:])
            remaining = remaining[:-2]
        groups.reverse()
        formatted = ",".join(groups) + "," + last_three

    result = f"{formatted}.{decimal_part}"
    return f"-{result}" if is_negative else result


def format_number(n: Union[int, float]) -> str:
    """Format a number with comma separators (e.g., 1,250)."""
    if isinstance(n, float):
        return f"{n:,.2f}"
    return f"{n:,}"


def format_date(dt: datetime) -> str:
    """Format a datetime as 'Jan 1, 2024'."""
    if dt is None:
        return "N/A"
    return dt.strftime("%b %d, %Y")


def format_datetime(dt: datetime) -> str:
    """Format a datetime as 'Jan 1, 2024 14:30'."""
    if dt is None:
        return "N/A"
    return dt.strftime("%b %d, %Y %H:%M")


def truncate_text(text: str, max_length: int = 30) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"
