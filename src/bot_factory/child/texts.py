"""User-facing strings for child (venue-customer) bots."""

from __future__ import annotations

from ..db.models import MenuItem, Tenant
from ..factory.common_format import format_price


def welcome(tenant: Tenant) -> str:
    """Greeting text shown on `/start`."""
    parts = [f"👋 Добро пожаловать в <b>{tenant.name}</b>!"]
    if tenant.description:
        parts.append(tenant.description)
    parts.append("Выбери раздел ниже:")
    return "\n\n".join(parts)


def menu_text(tenant: Tenant, items: list[MenuItem]) -> str:
    if not items:
        return f"🍽 Меню заведения <b>{tenant.name}</b> пока в разработке."

    lines: list[str] = [f"🍽 <b>Меню — {tenant.name}</b>"]
    last_category: str | None = None
    for item in items:
        if item.category != last_category:
            last_category = item.category
            if item.category:
                lines.append(f"\n<b>{item.category}</b>")
        line = f"• {item.title} — {format_price(item.price_minor, item.currency)}"
        if item.description:
            line += f"\n   <i>{item.description}</i>"
        lines.append(line)
    return "\n".join(lines)


def contacts_text(tenant: Tenant) -> str:
    parts = [f"📍 <b>{tenant.name}</b>"]
    if tenant.address:
        parts.append(f"Адрес: {tenant.address}")
    if tenant.phone:
        parts.append(f"📞 Телефон: {tenant.phone}")
    if tenant.working_hours:
        parts.append(f"🕒 {tenant.working_hours}")
    if len(parts) == 1:
        parts.append(
            "Контакты пока не заполнены. Загляни попозже — заведение их добавит."
        )
    return "\n".join(parts)


def about_text(tenant: Tenant) -> str:
    if tenant.description:
        return f"💬 <b>{tenant.name}</b>\n\n{tenant.description}"
    return f"💬 <b>{tenant.name}</b>\n\nОписание скоро появится."


# ---------------------------------------------------------------------------
# Booking flow

BOOK_ASK_DATE = (
    "📅 На какую дату бронируем? Введи в формате <code>ГГГГ-ММ-ДД</code>, "
    "например <code>2026-05-15</code>."
)
BOOK_DATE_INVALID = (
    "❌ Не похоже на дату. Введи в формате <code>ГГГГ-ММ-ДД</code>, "
    "например <code>2026-05-15</code>."
)
BOOK_DATE_PAST = "❌ Дата в прошлом. Введи будущую дату."

BOOK_ASK_TIME = "🕒 Во сколько? Введи в формате <code>ЧЧ:ММ</code>, например <code>19:30</code>."
BOOK_TIME_INVALID = (
    "❌ Не похоже на время. Введи в формате <code>ЧЧ:ММ</code>, например <code>19:30</code>."
)

BOOK_ASK_PARTY = "👥 Сколько гостей? Введи число (1–50)."
BOOK_PARTY_INVALID = "❌ Введи число от 1 до 50."

BOOK_ASK_NAME = "👤 На какое имя бронируем?"
BOOK_NAME_INVALID = "❌ Слишком короткое имя. Минимум 2 символа."

BOOK_ASK_PHONE = (
    "📞 Контактный телефон, по которому с тобой свяжутся для подтверждения "
    "(например, <code>+7 999 123-45-67</code>)."
)
BOOK_PHONE_INVALID = "❌ Не похоже на телефон. Минимум 7 цифр."

BOOK_ASK_COMMENT = (
    "💬 Комментарий к бронированию (особый повод, аллергии, рассадка). "
    "Можно пропустить — напиши <i>пропустить</i>."
)


def book_summary(
    *,
    venue_name: str,
    date_iso: str,
    time_iso: str,
    party_size: int,
    customer_name: str,
    customer_phone: str,
    comment: str | None,
) -> str:
    parts = [
        f"<b>Проверь бронирование — {venue_name}</b>",
        f"📅 Дата: {date_iso}",
        f"🕒 Время: {time_iso}",
        f"👥 Гостей: {party_size}",
        f"👤 Имя: {customer_name}",
        f"📞 Телефон: {customer_phone}",
    ]
    if comment:
        parts.append(f"💬 Комментарий: {comment}")
    parts.append("\nОтправляем заявку?")
    return "\n".join(parts)


BOOK_OK = (
    "✅ Заявка отправлена! Сотрудник свяжется с тобой по указанному номеру для "
    "подтверждения. Спасибо!"
)
BOOK_CANCELLED = "❌ Бронирование отменено."
