"""Inline / reply keyboards for the constructor bot."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from ..db.models import MenuItem, Reservation, Tenant
from . import texts

# ---------------------------------------------------------------------------
# Main reply keyboard


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Создать бота")],
            [KeyboardButton(text="🤖 Мои боты")],
            [KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


# ---------------------------------------------------------------------------
# Create-bot wizard


def business_type_kb() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=label, callback_data=f"type:{code}"),
        ]
        for code, label in texts.BUSINESS_TYPE_LABELS.items()
    ]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="create:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_create_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, создать", callback_data="create:save"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="create:cancel"),
            ]
        ]
    )


# ---------------------------------------------------------------------------
# Tenant list / single tenant menu


def tenants_list_kb(tenants: Sequence[Tenant]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for tenant in tenants:
        flag = "🟢" if tenant.is_active else "⏸"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{flag} {tenant.name}",
                    callback_data=f"tenant:{tenant.id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tenant_menu_kb(tenant: Tenant) -> InlineKeyboardMarkup:
    pause_text = "▶️ Активировать" if not tenant.is_active else "⏸ Поставить на паузу"
    pause_action = "resume" if not tenant.is_active else "pause"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Редактировать", callback_data=f"edit:{tenant.id}")],
            [InlineKeyboardButton(text="🍽 Меню", callback_data=f"menu:{tenant.id}")],
            [InlineKeyboardButton(text="📅 Брони", callback_data=f"res:{tenant.id}")],
            [InlineKeyboardButton(text=pause_text, callback_data=f"{pause_action}:{tenant.id}")],
            [InlineKeyboardButton(text="🗑 Удалить бота", callback_data=f"delete:{tenant.id}")],
            [InlineKeyboardButton(text="« Назад к списку", callback_data="tenants")],
        ]
    )


def edit_fields_kb(tenant_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"📝 {label}",
                callback_data=f"editfield:{tenant_id}:{field}",
            )
        ]
        for field, label in texts.FIELD_LABELS.items()
    ]
    rows.append(
        [InlineKeyboardButton(text="« Назад", callback_data=f"tenant:{tenant_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_kb(tenant_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Да, удалить",
                    callback_data=f"deleteconfirm:{tenant_id}",
                ),
                InlineKeyboardButton(
                    text="« Отмена",
                    callback_data=f"tenant:{tenant_id}",
                ),
            ]
        ]
    )


# ---------------------------------------------------------------------------
# Menu editor


def menu_editor_kb(tenant_id: int, items: Sequence[MenuItem]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        avail_label = "✅" if item.is_available else "🚫"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📝 {item.title}",
                    callback_data=f"menuedit:{item.id}",
                ),
                InlineKeyboardButton(
                    text=avail_label,
                    callback_data=f"menutoggle:{item.id}",
                ),
                InlineKeyboardButton(
                    text="🗑",
                    callback_data=f"menudel:{item.id}",
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="➕ Добавить позицию",
                callback_data=f"menuadd:{tenant_id}",
            )
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="« Назад", callback_data=f"tenant:{tenant_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def menu_item_edit_kb(item_id: int, tenant_id: int) -> InlineKeyboardMarkup:
    """Inline menu shown when the owner taps a single menu item to edit it."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Название",
                    callback_data=f"menufield:{item_id}:title",
                ),
                InlineKeyboardButton(
                    text="✏️ Описание",
                    callback_data=f"menufield:{item_id}:description",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Цена",
                    callback_data=f"menufield:{item_id}:price_minor",
                ),
                InlineKeyboardButton(
                    text="✏️ Категория",
                    callback_data=f"menufield:{item_id}:category",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Доступность",
                    callback_data=f"menutoggle:{item_id}",
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"menudel:{item_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="« К меню",
                    callback_data=f"menu:{tenant_id}",
                )
            ],
        ]
    )


def back_to_tenant_kb(tenant_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="« Назад",
                    callback_data=f"tenant:{tenant_id}",
                )
            ]
        ]
    )


# ---------------------------------------------------------------------------
# Reservations list


def reservation_actions_kb(
    reservation: Reservation,
    *,
    include_back: bool = True,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if reservation.status == "new":
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"resstatus:{reservation.id}:confirmed",
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"resstatus:{reservation.id}:declined",
                ),
            ]
        )
    if reservation.status == "confirmed":
        rows.append(
            [
                InlineKeyboardButton(
                    text="🍽 Гости пришли",
                    callback_data=f"resstatus:{reservation.id}:done",
                ),
                InlineKeyboardButton(
                    text="🚫 Отменить",
                    callback_data=f"resstatus:{reservation.id}:cancelled",
                ),
            ]
        )
    if include_back:
        rows.append(
            [InlineKeyboardButton(text="« Назад", callback_data=f"res:{reservation.tenant_id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reservations_kb(
    tenant_id: int,
    reservations: Sequence[Reservation],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for reservation in reservations:
        if reservation.status == "new":
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"✅ #{reservation.id}",
                        callback_data=f"resstatus:{reservation.id}:confirmed",
                    ),
                    InlineKeyboardButton(
                        text=f"❌ #{reservation.id}",
                        callback_data=f"resstatus:{reservation.id}:declined",
                    ),
                ]
            )
        elif reservation.status == "confirmed":
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🍽 #{reservation.id}",
                        callback_data=f"resstatus:{reservation.id}:done",
                    ),
                    InlineKeyboardButton(
                        text=f"🚫 #{reservation.id}",
                        callback_data=f"resstatus:{reservation.id}:cancelled",
                    ),
                ]
            )
    rows.append([InlineKeyboardButton(text="« Назад", callback_data=f"tenant:{tenant_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
