"""
Common keyboard components — Back / Home / Close footer, shared buttons.
"""

from __future__ import annotations

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def back_button(target: str = "home") -> InlineKeyboardButton:
    """A ◀ Back button pointing to a specific callback target."""
    return InlineKeyboardButton("◀ Back", callback_data=f"back:{target}")


def home_button() -> InlineKeyboardButton:
    """A 🏠 Home button returning to the main menu."""
    return InlineKeyboardButton("🏠 Home", callback_data="home")


def close_button() -> InlineKeyboardButton:
    """A ✖ Close button that dismisses the message."""
    return InlineKeyboardButton("✖ Close", callback_data="close")


def back_home_close(back_target: str = "home") -> list:
    """Standard footer row: [◀ Back] [🏠 Home] [✖ Close]."""
    return [back_button(back_target), home_button(), close_button()]


def confirm_cancel_row(
    confirm_data: str = "confirm",
    cancel_data: str = "cancel",
) -> list:
    """Confirm / Cancel button row."""
    return [
        InlineKeyboardButton("🟩 Confirm", callback_data=confirm_data),
        InlineKeyboardButton("🟥 Cancel", callback_data=cancel_data),
    ]


def add_footer(
    keyboard: list,
    back_target: str = "home",
) -> InlineKeyboardMarkup:
    """Add the standard footer to a keyboard layout and return InlineKeyboardMarkup."""
    keyboard.append(back_home_close(back_target))
    return InlineKeyboardMarkup(keyboard)
