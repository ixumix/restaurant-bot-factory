"""User-facing strings for the constructor bot. All Russian by design."""

from __future__ import annotations

from ..db.models import Tenant

# ---------------------------------------------------------------------------
# Business types

BUSINESS_TYPE_LABELS: dict[str, str] = {
    "restaurant": "Ресторан",
    "bar": "Бар",
    "cafe": "Кафе",
    "banquet": "Банкетный зал",
}


def business_type_label(code: str) -> str:
    return BUSINESS_TYPE_LABELS.get(code, code)


RESERVATION_STATUS_LABELS: dict[str, str] = {
    "new": "новая",
    "confirmed": "подтверждена",
    "declined": "отклонена",
    "cancelled": "отменена",
    "done": "выполнена",
}


RESERVATION_STATUS_ACTIONS: dict[str, str] = {
    "confirmed": "подтвердил",
    "declined": "отклонил",
}


def reservation_status_label(status: str) -> str:
    return RESERVATION_STATUS_LABELS.get(status, status)


# ---------------------------------------------------------------------------
# Static texts

START = (
    "👋 Привет! Это бот-конструктор для ресторанов, баров, кафе и банкетных залов.\n\n"
    "Здесь ты можешь за пару минут собрать собственного Telegram-бота для своего "
    "заведения — с меню, бронированием стола и контактами. Без кода и серверов.\n\n"
    "Что хочешь сделать?"
)

HELP = (
    "ℹ️ <b>Что умеет конструктор</b>\n\n"
    "• <b>Создать бота</b> — пройди мастер: токен от @BotFather, тип заведения, "
    "название, адрес, часы работы, контакты. Готового бота можно сразу запустить.\n"
    "• <b>Мои боты</b> — список твоих заведений. Внутри каждого: редактирование "
    "информации, меню, просмотр бронирований и пауза/удаление бота.\n"
    "• <b>Уведомления</b> — каждое новое бронирование приходит сюда, в чат с "
    "конструктором.\n\n"
    "Для нового бота тебе понадобится свой токен от @BotFather "
    "(в Telegram открой @BotFather → /newbot)."
)

NOT_ALLOWED = (
    "🚫 Доступ к этому конструктору ограничен. Свяжись с администратором, чтобы он "
    "добавил твой Telegram ID в список владельцев."
)

# ---------------------------------------------------------------------------
# Create-bot wizard

CREATE_ASK_TOKEN = (
    "Шаг 1/6. Пришли токен бота, который ты получил у @BotFather.\n\n"
    "Должен выглядеть так: <code>123456789:AA...</code>\n\n"
    "Если у тебя его ещё нет — открой @BotFather, отправь /newbot, "
    "придумай имя и username, и пришли мне токен из ответа."
)
CREATE_TOKEN_INVALID = (
    "❌ Это не похоже на токен. Должно быть что-то вида "
    "<code>123456789:AA...</code>. Попробуй ещё раз."
)
CREATE_TOKEN_TAKEN = "❌ Этот бот уже подключён к конструктору. Используй другой токен."
CREATE_TOKEN_BAD = (
    "❌ Telegram не принял этот токен (getMe вернул ошибку). Проверь, что ты "
    "скопировал токен полностью и из @BotFather. Попробуй ещё раз."
)

CREATE_ASK_TYPE = "Шаг 2/6. Что у тебя за заведение?"

CREATE_ASK_NAME = "Шаг 3/6. Как называется заведение?"
CREATE_NAME_TOO_LONG = "❌ Слишком длинное название. Уложись в 100 символов."

CREATE_ASK_ADDRESS = (
    "Шаг 4/6. Адрес заведения (улица, дом, город). Если адреса пока нет — "
    "напиши <i>пропустить</i>."
)
CREATE_ASK_PHONE = (
    "Шаг 5/6. Телефон для связи (например, <code>+7 999 123-45-67</code>). "
    "Можно <i>пропустить</i>."
)
CREATE_ASK_HOURS = (
    "Шаг 6/6. Часы работы — одной строкой, например <code>Пн–Вс 12:00–23:00</code>. "
    "Можно <i>пропустить</i>."
)
CREATE_ASK_DESCRIPTION = (
    "Последний штрих — короткое описание заведения (1–3 предложения). Появится "
    "в разделе «О нас». Можно <i>пропустить</i>."
)


def create_summary(
    *,
    bot_username: str,
    business_type: str,
    name: str,
    address: str | None,
    phone: str | None,
    working_hours: str | None,
    description: str | None,
) -> str:
    parts = [
        "<b>Проверь данные:</b>",
        f"🤖 Бот: @{bot_username}",
        f"🏷 Тип: {business_type_label(business_type)}",
        f"📍 Название: {name}",
    ]
    if address:
        parts.append(f"🗺 Адрес: {address}")
    if phone:
        parts.append(f"📞 Телефон: {phone}")
    if working_hours:
        parts.append(f"🕒 Часы работы: {working_hours}")
    if description:
        parts.append(f"💬 Описание: {description}")
    parts.append("\nСохраняем и запускаем бота?")
    return "\n".join(parts)


def created_ok(bot_username: str) -> str:
    return (
        f"✅ Готово! Твой бот @{bot_username} запущен.\n\n"
        "Открой его в Telegram и нажми /start, чтобы посмотреть, что увидят гости.\n"
        "Чтобы добавить блюда в меню или поменять данные — открой раздел «🤖 Мои боты»."
    )


CREATE_CANCELLED = "❌ Создание бота отменено."
CREATE_DB_ERROR = (
    "❌ Не получилось сохранить — внутренняя ошибка. Попробуй ещё раз "
    "или напиши администратору."
)


# ---------------------------------------------------------------------------
# Manage flow

NO_TENANTS = (
    "Пока нет ни одного заведения. Нажми «➕ Создать бота», чтобы добавить первое."
)


def tenant_summary(tenant: Tenant) -> str:
    parts = [
        f"<b>{tenant.name}</b> — {business_type_label(tenant.business_type)}",
        f"🤖 @{tenant.bot_username}",
        f"Статус: {'🟢 активен' if tenant.is_active else '⏸ на паузе'}",
    ]
    if tenant.address:
        parts.append(f"📍 {tenant.address}")
    if tenant.phone:
        parts.append(f"📞 {tenant.phone}")
    if tenant.working_hours:
        parts.append(f"🕒 {tenant.working_hours}")
    if tenant.description:
        parts.append(f"\n{tenant.description}")
    return "\n".join(parts)


EDIT_FIELD_PROMPTS: dict[str, str] = {
    "name": "Введи новое название заведения.",
    "description": "Введи новое описание (1–3 предложения).",
    "address": "Введи новый адрес.",
    "phone": "Введи новый телефон.",
    "working_hours": "Введи новые часы работы (например, <code>Пн–Вс 12:00–23:00</code>).",
}

FIELD_LABELS: dict[str, str] = {
    "name": "Название",
    "description": "Описание",
    "address": "Адрес",
    "phone": "Телефон",
    "working_hours": "Часы работы",
}

EDIT_SAVED = "✅ Сохранил."
TENANT_PAUSED = "⏸ Бот поставлен на паузу — он больше не отвечает гостям."
TENANT_RESUMED = "▶️ Бот снова активен."
TENANT_DELETED = "🗑 Бот удалён вместе с меню и бронированиями."
TENANT_DELETE_CONFIRM = (
    "Точно удалить этого бота? Удалятся также все позиции меню и история бронирований."
)


# ---------------------------------------------------------------------------
# Menu editor

MENU_EMPTY = "Меню пока пустое. Нажми «➕ Добавить позицию»."

MENU_ADD_TITLE = "Введи название позиции (например, <i>Цезарь с курицей</i>)."
MENU_ADD_DESCRIPTION = (
    "Короткое описание (состав / порция). Можно <i>пропустить</i>."
)
MENU_ADD_PRICE = (
    "Цена в рублях. Целое число или с копейками через запятую/точку (например, "
    "<code>450</code> или <code>450.50</code>)."
)
MENU_ADD_PRICE_INVALID = "❌ Не понял цену. Введи число, например <code>450</code>."
MENU_ADD_OK = "✅ Позиция добавлена."
MENU_ITEM_DELETED = "🗑 Позиция удалена."

# ---------------------------------------------------------------------------
# Reservations

NO_RESERVATIONS = "Бронирований пока нет."
RESERVATION_STATUS_UPDATED = "Статус бронирования обновлён."
RESERVATION_ALREADY_PROCESSED = "Это бронирование уже обработано."
RESERVATION_NOT_FOUND = "Бронирование не найдено."


def reservation_line(
    date_iso: str,
    time_iso: str,
    party_size: int,
    name: str,
    phone: str,
    status: str,
    reservation_id: int | None = None,
) -> str:
    prefix = f"#{reservation_id} · " if reservation_id is not None else ""
    return (
        f"{prefix}📅 {date_iso} {time_iso} · {party_size} гост. · "
        f"{name} · {phone} · {reservation_status_label(status)}"
    )


def reservation_status_owner_line(
    venue_name: str,
    date_iso: str,
    time_iso: str,
    status: str,
    *,
    customer_notified: bool,
) -> str:
    action = RESERVATION_STATUS_ACTIONS.get(status, "обновил")
    notify_text = (
        "Гостю отправлено уведомление."
        if customer_notified
        else "Гостю не удалось отправить уведомление автоматически."
    )
    return (
        f"Ты {action} бронь в <b>{venue_name}</b> "
        f"на {date_iso} в {time_iso}. {notify_text}"
    )


def customer_reservation_status_notification(
    *,
    venue_name: str,
    date_iso: str,
    time_iso: str,
    party_size: int,
    status: str,
) -> str:
    label = reservation_status_label(status)
    if status == "confirmed":
        lead = "Ваша бронь подтверждена. Ждём вас!"
    elif status == "declined":
        lead = "К сожалению, заведение не смогло подтвердить эту бронь."
    else:
        lead = f"Статус вашей брони изменён: {label}."
    return "\n".join(
        [
            f"<b>{lead}</b>",
            f"Заведение: {venue_name}",
            f"Дата и время: {date_iso} {time_iso}",
            f"Гостей: {party_size}",
        ]
    )


# ---------------------------------------------------------------------------
# Owner notification when a new reservation arrives

def new_reservation_notification(
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
        f"🔔 <b>Новое бронирование — {venue_name}</b>",
        f"📅 Дата: {date_iso}",
        f"🕒 Время: {time_iso}",
        f"👥 Гостей: {party_size}",
        f"👤 Имя: {customer_name}",
        f"📞 Телефон: {customer_phone}",
        f"Статус: {reservation_status_label('new')}",
    ]
    if comment:
        parts.append(f"💬 Комментарий: {comment}")
    parts.append("Подтверди или отклони заявку кнопками ниже.")
    return "\n".join(parts)
