"""Keyboards for child (customer-facing) bots."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍽 Меню")],
            [KeyboardButton(text="📅 Забронировать")],
            [KeyboardButton(text="📍 Контакты"), KeyboardButton(text="💬 О нас")],
        ],
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
