"""Keyboards for child (customer-facing) bots."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

SUPPORT_BUTTON_TEXT = "🤖 Поддержка"
SUPPORT_EXIT_TEXT = "🚪 Выйти из чата"


def main_menu_kb(*, with_support: bool = False) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text="🍽 Меню")],
        [KeyboardButton(text="📅 Забронировать")],
        [KeyboardButton(text="📍 Контакты"), KeyboardButton(text="💬 О нас")],
    ]
    if with_support:
        rows.append([KeyboardButton(text=SUPPORT_BUTTON_TEXT)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def support_chat_kb() -> ReplyKeyboardMarkup:
    """Keyboard shown while the user is in the live support chat."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=SUPPORT_EXIT_TEXT)]],
        resize_keyboard=True,
    )


def confirm_booking_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data="book:confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="book:cancel"),
            ]
        ]
    )
