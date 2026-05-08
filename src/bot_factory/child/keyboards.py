"""Keyboards for child (customer-facing) bots."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

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


_RU_WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def _format_quick_date(label: str, target: date) -> str:
    return f"{label} ({target.day:02d}.{target.month:02d}, {_RU_WEEKDAYS[target.weekday()]})"


def booking_date_kb(today: date | None = None) -> InlineKeyboardMarkup:
    """Quick-pick keyboard for booking dates: today, tomorrow, +2, +1 week."""
    if today is None:
        today = datetime.now(UTC).date()
    options: list[tuple[str, date]] = [
        ("Сегодня", today),
        ("Завтра", today + timedelta(days=1)),
        ("Послезавтра", today + timedelta(days=2)),
        ("Через неделю", today + timedelta(days=7)),
    ]
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=_format_quick_date(label, target),
                callback_data=f"bookdate:{target.isoformat()}",
            )
        ]
        for label, target in options
    ]
    rows.append(
        [InlineKeyboardButton(text="❌ Отмена", callback_data="book:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_booking_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="book:cancel")]
        ]
    )
