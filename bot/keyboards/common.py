"""
Common keyboard components — Back / Home / Close footer, shared buttons.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def back_button(target: str = "home") -> InlineKeyboardButton:
    """A Back button pointing to a specific callback target. Primary style."""
    return InlineKeyboardButton(text="◀ Back", callback_data=f"back:{target}", style="primary")


def home_button() -> InlineKeyboardButton:
    """A Home button returning to the main menu. Primary style."""
    return InlineKeyboardButton(text="🏠 Home", callback_data="home", style="primary")


def close_button() -> InlineKeyboardButton:
    """A Close button that dismisses the message. Danger style."""
    return InlineKeyboardButton(text="✖ Close", callback_data="close", style="danger")


def back_home_close(back_target: str = "home") -> list:
    """Standard footer row: [◀ Back] [🏠 Home] [✖ Close]."""
    return [back_button(back_target), home_button(), close_button()]


def confirm_cancel_row(
    confirm_data: str = "confirm",
    cancel_data: str = "cancel",
) -> list:
    """Confirm / Cancel button row."""
    return [
        InlineKeyboardButton(text="Confirm", callback_data=confirm_data, style="success"),
        InlineKeyboardButton(text="Cancel", callback_data=cancel_data, style="danger"),
    ]


def add_footer(
    keyboard: list,
    back_target: str = "home",
) -> InlineKeyboardMarkup:
    """Add the standard footer to a keyboard layout and return InlineKeyboardMarkup."""
    keyboard.append(back_home_close(back_target))
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
