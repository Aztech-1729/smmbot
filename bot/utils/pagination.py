"""
Generic pagination utility for inline keyboard list views.
"""

from __future__ import annotations

from math import ceil
from typing import List, Any

from aiogram.types import InlineKeyboardButton


class Paginator:
    """
    Reusable paginator for list views.

    Usage:
        p = Paginator(items, page=1, per_page=10)
        for item in p.items:
            ...
        buttons = p.get_nav_buttons("svc_page")
    """

    def __init__(self, all_items: List[Any], page: int = 1, per_page: int = 10):
        self.all_items = all_items
        self.per_page = per_page
        self.total_pages = max(1, ceil(len(all_items) / per_page))
        self.page = max(1, min(page, self.total_pages))

        start = (self.page - 1) * per_page
        end = start + per_page
        self.items = all_items[start:end]

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    def get_nav_buttons(self, callback_prefix: str) -> List[InlineKeyboardButton]:
        """
        Return a row of pagination buttons.
        callback_prefix is used to build callback data like 'prefix:page_num'.
        """
        buttons = []

        if self.has_prev:
            buttons.append(
                InlineKeyboardButton(
                    text="◀ Prev",
                    callback_data=f"{callback_prefix}:{self.page - 1}",
                    style="primary"
                )
            )

        buttons.append(
            InlineKeyboardButton(
                text=f"Page {self.page}/{self.total_pages}",
                callback_data="noop",
                style="primary"
            )
        )

        if self.has_next:
            buttons.append(
                InlineKeyboardButton(
                    text="Next ▶",
                    callback_data=f"{callback_prefix}:{self.page + 1}",
                    style="primary"
                )
            )

        return buttons
