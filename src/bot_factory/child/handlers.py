"""All handlers for a single tenant's child bot.

The child bot's :class:`Dispatcher` is built per tenant — see
:func:`make_child_dispatcher` — so the tenant id can be captured in the closure
and reused by every handler.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db import repo
from ..factory import keyboards as factory_keyboards
from ..factory import texts as factory_texts  # for `new_reservation_notification`
from ..notifications import Notifier
from . import keyboards, texts
from .states import Booking

# Regex helpers
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
_PHONE_DIGITS_RE = re.compile(r"\D+")


def _phone_is_valid(text: str) -> bool:
    digits = _PHONE_DIGITS_RE.sub("", text)
    return len(digits) >= 7


def _is_skip(text: str) -> bool:
    return text.strip().lower() in {"пропустить", "skip", "-", "—", "нет"}


def _build_router(
    *,
    tenant_id: int,
    sessionmaker: async_sessionmaker[AsyncSession],
    notifier: Notifier,
) -> Router:
    """Return a :class:`Router` with all handlers bound to this tenant."""
    router = Router(name=f"child.tenant{tenant_id}")

    async def _send_main_menu(target: Message) -> None:
        async with sessionmaker() as session:
            tenant = await repo.get_tenant(session, tenant_id)
        if tenant is None:
            await target.answer("Бот временно недоступен.")
            return
        await target.answer(texts.welcome(tenant), reply_markup=keyboards.main_menu_kb())

    @router.message(CommandStart())
    async def handle_start(message: Message, state: FSMContext) -> None:
        await state.clear()
        await _send_main_menu(message)

    @router.message(Command("cancel"))
    async def handle_cancel(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(
            "Окей, отменил.", reply_markup=keyboards.main_menu_kb()
        )

    # ---------------- Menu ----------------

    async def _send_menu(message: Message) -> None:
        async with sessionmaker() as session:
            tenant = await repo.get_tenant(session, tenant_id)
            if tenant is None:
                return
            items = list(
                await repo.get_menu_items(session, tenant_id, only_available=True)
            )
        await message.answer(texts.menu_text(tenant, items))

    @router.message(Command("menu"))
    @router.message(F.text == "🍽 Меню")
    async def show_menu(message: Message) -> None:
        await _send_menu(message)

    # ---------------- Contacts / About ----------------

    @router.message(Command("contacts"))
    @router.message(F.text == "📍 Контакты")
    async def show_contacts(message: Message) -> None:
        async with sessionmaker() as session:
            tenant = await repo.get_tenant(session, tenant_id)
        if tenant is None:
            return
        await message.answer(texts.contacts_text(tenant))

    @router.message(Command("about"))
    @router.message(F.text == "💬 О нас")
    async def show_about(message: Message) -> None:
        async with sessionmaker() as session:
            tenant = await repo.get_tenant(session, tenant_id)
        if tenant is None:
            return
        await message.answer(texts.about_text(tenant))

    # ---------------- Booking ----------------

    async def _ask_date(message: Message, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(Booking.waiting_for_date)
        await message.answer(
            texts.BOOK_ASK_DATE,
            reply_markup=keyboards.booking_date_kb(),
        )

    @router.message(Command("book"))
    @router.message(F.text == "📅 Забронировать")
    async def start_booking(message: Message, state: FSMContext) -> None:
        await _ask_date(message, state)

    @router.callback_query(Booking.waiting_for_date, F.data.startswith("bookdate:"))
    async def receive_date_callback(call: CallbackQuery, state: FSMContext) -> None:
        if call.data is None or call.message is None:
            return
        raw = call.data.split(":", 1)[1]
        if not _DATE_RE.match(raw):
            await call.answer(texts.BOOK_DATE_INVALID, show_alert=True)
            return
        try:
            chosen = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            await call.answer(texts.BOOK_DATE_INVALID, show_alert=True)
            return
        if chosen < datetime.now(UTC).date():
            await call.answer(texts.BOOK_DATE_PAST, show_alert=True)
            return
        await state.update_data(date_iso=raw)
        await state.set_state(Booking.waiting_for_time)
        await call.message.answer(
            texts.BOOK_ASK_TIME, reply_markup=keyboards.cancel_booking_kb()
        )
        await call.answer()

    @router.message(Booking.waiting_for_date)
    async def receive_date(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        if not _DATE_RE.match(raw):
            await message.answer(texts.BOOK_DATE_INVALID)
            return
        try:
            chosen = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            await message.answer(texts.BOOK_DATE_INVALID)
            return
        if chosen < datetime.now(UTC).date():
            await message.answer(texts.BOOK_DATE_PAST)
            return
        await state.update_data(date_iso=raw)
        await state.set_state(Booking.waiting_for_time)
        await message.answer(
            texts.BOOK_ASK_TIME, reply_markup=keyboards.cancel_booking_kb()
        )

    @router.message(Booking.waiting_for_time)
    async def receive_time(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        if not _TIME_RE.match(raw):
            await message.answer(texts.BOOK_TIME_INVALID)
            return
        try:
            datetime.strptime(raw, "%H:%M")
        except ValueError:
            await message.answer(texts.BOOK_TIME_INVALID)
            return
        # Re-format to canonical "HH:MM".
        hh, mm = raw.split(":")
        canonical = f"{int(hh):02d}:{int(mm):02d}"
        await state.update_data(time_iso=canonical)
        await state.set_state(Booking.waiting_for_party)
        await message.answer(texts.BOOK_ASK_PARTY)

    @router.message(Booking.waiting_for_party)
    async def receive_party(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        try:
            n = int(raw)
        except ValueError:
            await message.answer(texts.BOOK_PARTY_INVALID)
            return
        if not 1 <= n <= 50:
            await message.answer(texts.BOOK_PARTY_INVALID)
            return
        await state.update_data(party_size=n)
        await state.set_state(Booking.waiting_for_name)
        await message.answer(texts.BOOK_ASK_NAME)

    @router.message(Booking.waiting_for_name)
    async def receive_name(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        if len(raw) < 2:
            await message.answer(texts.BOOK_NAME_INVALID)
            return
        await state.update_data(customer_name=raw)
        await state.set_state(Booking.waiting_for_phone)
        await message.answer(texts.BOOK_ASK_PHONE)

    @router.message(Booking.waiting_for_phone)
    async def receive_phone(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        if not _phone_is_valid(raw):
            await message.answer(texts.BOOK_PHONE_INVALID)
            return
        await state.update_data(customer_phone=raw)
        await state.set_state(Booking.waiting_for_comment)
        await message.answer(texts.BOOK_ASK_COMMENT)

    @router.message(Booking.waiting_for_comment)
    async def receive_comment(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        comment = None if not raw or _is_skip(raw) else raw
        await state.update_data(comment=comment)
        data = await state.get_data()
        async with sessionmaker() as session:
            tenant = await repo.get_tenant(session, tenant_id)
        if tenant is None:
            await state.clear()
            return
        summary = texts.book_summary(
            venue_name=tenant.name,
            date_iso=data["date_iso"],
            time_iso=data["time_iso"],
            party_size=int(data["party_size"]),
            customer_name=str(data["customer_name"]),
            customer_phone=str(data["customer_phone"]),
            comment=comment,
        )
        await state.set_state(Booking.waiting_for_confirm)
        await message.answer(summary, reply_markup=keyboards.confirm_booking_kb())

    @router.callback_query(Booking.waiting_for_confirm, F.data == "book:cancel")
    async def cancel_booking(call: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        if call.message is not None:
            await call.message.answer(
                texts.BOOK_CANCELLED, reply_markup=keyboards.main_menu_kb()
            )
        await call.answer()

    @router.callback_query(Booking.waiting_for_confirm, F.data == "book:confirm")
    async def confirm_booking(call: CallbackQuery, state: FSMContext) -> None:
        if call.message is None or call.from_user is None:
            return
        data = await state.get_data()
        await state.clear()
        async with sessionmaker() as session:
            tenant = await repo.get_tenant(session, tenant_id)
            if tenant is None:
                await call.answer("Бот временно недоступен")
                return
            reservation = await repo.create_reservation(
                session,
                tenant_id=tenant_id,
                customer_telegram_id=call.from_user.id,
                customer_name=str(data["customer_name"]),
                customer_phone=str(data["customer_phone"]),
                date_iso=str(data["date_iso"]),
                time_iso=str(data["time_iso"]),
                party_size=int(data["party_size"]),
                comment=data.get("comment"),
            )
            owner_id = tenant.owner_id
            venue_name = tenant.name

        await call.message.answer(
            texts.BOOK_OK, reply_markup=keyboards.main_menu_kb()
        )
        await call.answer()

        # Notify the venue owner via the constructor bot.
        await notifier.notify_owner(
            owner_id,
            factory_texts.new_reservation_notification(
                venue_name=venue_name,
                date_iso=str(data["date_iso"]),
                time_iso=str(data["time_iso"]),
                party_size=int(data["party_size"]),
                customer_name=str(data["customer_name"]),
                customer_phone=str(data["customer_phone"]),
                comment=data.get("comment"),
            ),
            reply_markup=factory_keyboards.reservation_actions_kb(
                reservation,
                include_back=False,
            ),
        )

    return router


def make_child_dispatcher_factory(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    notifier: Notifier,
) -> Callable[[int], Dispatcher]:
    """Return a callable that builds a fresh :class:`Dispatcher` per tenant."""

    def factory(tenant_id: int) -> Dispatcher:
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(
            _build_router(
                tenant_id=tenant_id,
                sessionmaker=sessionmaker,
                notifier=notifier,
            )
        )
        return dp

    return factory
