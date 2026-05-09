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


# ---------------------------------------------------------------------------
# Support chat (Claude)

SUPPORT_INTRO = (
    "🤖 <b>Чат с виртуальным ассистентом</b>\n\n"
    "Спрашивай про меню, бронирование, часы работы, как добраться, "
    "детское меню, банкеты — постараюсь помочь.\n\n"
    "Чтобы выйти, нажми кнопку <b>🚪 Выйти из чата</b> или отправь /cancel."
)
SUPPORT_THINKING = "✍️ Печатаю ответ…"
SUPPORT_EMPTY_INPUT = "Напиши свой вопрос текстом — я не работаю с фото и файлами."
SUPPORT_UNAVAILABLE = (
    "🚧 Чат с ассистентом сейчас недоступен (исчерпан лимит запросов). "
    "Попробуй чуть позже или свяжись с заведением напрямую."
)
SUPPORT_BACKEND_ERROR = (
    "🤖 Что-то пошло не так на стороне ассистента. Попробуй ещё раз или выйди "
    "из чата командой /cancel."
)
SUPPORT_LEFT = "Окей, вышли из чата с ассистентом."


def support_system_prompt(tenant: Tenant) -> str:
    """Default system prompt — describes the venue Claude is supporting."""
    parts: list[str] = [
        "Ты — дружелюбный AI-ассистент в Telegram-боте заведения "
        f"<{tenant.name}>. Отвечай по-русски, кратко, по делу, без воды.",
        "Помогаешь гостям: подсказываешь по меню, объясняешь как забронировать "
        "столик через бот, отвечаешь про часы работы и расположение.",
        "Если гость просит сделать что-то, что бот умеет (бронь, посмотреть "
        "меню, контакты), скажи, какую кнопку нажать в главном меню.",
        "Никогда не выдумывай блюда, цены, часы работы или адрес, если их нет в "
        "контексте ниже — лучше скажи «уточни у заведения» и предложи кнопку "
        "«📍 Контакты».",
        "Не обсуждай темы, не связанные с этим заведением и общепитом.",
    ]
    info: list[str] = []
    if tenant.business_type:
        info.append(f"Тип заведения: {tenant.business_type}")
    if tenant.description:
        info.append(f"Описание: {tenant.description}")
    if tenant.address:
        info.append(f"Адрес: {tenant.address}")
    if tenant.phone:
        info.append(f"Телефон: {tenant.phone}")
    if tenant.working_hours:
        info.append(f"Часы работы: {tenant.working_hours}")
    if info:
        parts.append("Контекст про заведение:\n" + "\n".join(f"- {x}" for x in info))
    return "\n\n".join(parts)
