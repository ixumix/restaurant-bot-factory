"""All handlers for a single tenant's child bot.

The child bot's :class:`Dispatcher` is built per tenant — see
:func:`make_child_dispatcher` — so the tenant id can be captured in the closure
and reused by every handler.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import cast

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..claude import (
    ChatMessage,
    ClaudeAllKeysExhaustedError,
    ClaudeAPIError,
    ClaudeClient,
    ClaudeError,
)
from ..db import repo
from ..devin_chat import (
    DevinAllKeysExhaustedError,
    DevinAPIError,
    DevinChatClient,
    DevinError,
    DevinSessionExpiredError,
    DevinTimeoutError,
)
from ..factory import keyboards as factory_keyboards
from ..factory import texts as factory_texts  # for `new_reservation_notification`
from ..notifications import Notifier
from . import keyboards, texts
from .states import Booking, Support

logger = logging.getLogger(__name__)

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
    claude_client: ClaudeClient | None = None,
    claude_history_limit: int = 10,
    claude_system_prompt_override: str | None = None,
    devin_client: DevinChatClient | None = None,
) -> Router:
    """Return a :class:`Router` with all handlers bound to this tenant."""
    router = Router(name=f"child.tenant{tenant_id}")
    # At most one chat backend is active at a time. Claude takes precedence
    # when both are configured (the dispatcher factory resolves this).
    claude_enabled = claude_client is not None
    devin_enabled = devin_client is not None and not claude_enabled
    support_enabled = claude_enabled or devin_enabled

    def _menu_kb() -> ReplyKeyboardMarkup:
        return keyboards.main_menu_kb(with_support=support_enabled)

    async def _send_main_menu(target: Message) -> None:
        async with sessionmaker() as session:
            tenant = await repo.get_tenant(session, tenant_id)
        if tenant is None:
            await target.answer("Бот временно недоступен.")
            return
        await target.answer(texts.welcome(tenant), reply_markup=_menu_kb())

    @router.message(CommandStart())
    async def handle_start(message: Message, state: FSMContext) -> None:
        await state.clear()
        await _send_main_menu(message)

    @router.message(Command("cancel"))
    async def handle_cancel(message: Message, state: FSMContext) -> None:
        current = await state.get_state()
        await state.clear()
        if current == Support.chatting.state:
            await message.answer(texts.SUPPORT_LEFT, reply_markup=_menu_kb())
            return
        await message.answer("Окей, отменил.", reply_markup=_menu_kb())

    # ---------------- Menu ----------------

    @router.message(F.text == "🍽 Меню")
    async def show_menu(message: Message) -> None:
        async with sessionmaker() as session:
            tenant = await repo.get_tenant(session, tenant_id)
            if tenant is None:
                return
            items = list(
                await repo.get_menu_items(session, tenant_id, only_available=True)
            )
        await message.answer(texts.menu_text(tenant, items))

    # ---------------- Contacts / About ----------------

    @router.message(F.text == "📍 Контакты")
    async def show_contacts(message: Message) -> None:
        async with sessionmaker() as session:
            tenant = await repo.get_tenant(session, tenant_id)
        if tenant is None:
            return
        await message.answer(texts.contacts_text(tenant))

    @router.message(F.text == "💬 О нас")
    async def show_about(message: Message) -> None:
        async with sessionmaker() as session:
            tenant = await repo.get_tenant(session, tenant_id)
        if tenant is None:
            return
        await message.answer(texts.about_text(tenant))

    # ---------------- Support chat (Claude / Devin) ----------------

    if support_enabled:
        history_limit = max(1, claude_history_limit)
        # Each (user, assistant) pair is two messages.
        max_history_messages = history_limit * 2

        async def _resolve_system_prompt() -> str | None:
            """Build the support-chat system prompt for this tenant."""
            async with sessionmaker() as session:
                tenant = await repo.get_tenant(session, tenant_id)
            if tenant is None:
                return None
            return (
                claude_system_prompt_override
                if claude_system_prompt_override
                else texts.support_system_prompt(tenant)
            )

        @router.message(F.text == keyboards.SUPPORT_BUTTON_TEXT)
        async def enter_support(message: Message, state: FSMContext) -> None:
            await state.clear()
            await state.set_state(Support.chatting)
            await state.update_data(history=[])
            intro = (
                texts.SUPPORT_INTRO_DEVIN if devin_enabled else texts.SUPPORT_INTRO
            )
            await message.answer(intro, reply_markup=keyboards.support_chat_kb())

        @router.message(Support.chatting, F.text == keyboards.SUPPORT_EXIT_TEXT)
        async def exit_support(message: Message, state: FSMContext) -> None:
            await state.clear()
            await message.answer(texts.SUPPORT_LEFT, reply_markup=_menu_kb())

    if claude_enabled:
        client: ClaudeClient = cast(ClaudeClient, claude_client)

        @router.message(Support.chatting)
        async def claude_support_message(
            message: Message, state: FSMContext
        ) -> None:
            user_text = (message.text or "").strip()
            if not user_text:
                await message.answer(texts.SUPPORT_EMPTY_INPUT)
                return

            data = await state.get_data()
            raw_history = data.get("history") or []
            history: list[ChatMessage] = []
            for item in raw_history:
                if (
                    isinstance(item, dict)
                    and isinstance(item.get("role"), str)
                    and isinstance(item.get("content"), str)
                ):
                    history.append(
                        ChatMessage(role=item["role"], content=item["content"])
                    )

            history.append(ChatMessage(role="user", content=user_text))
            # Sliding window over the most recent N messages.
            trimmed = history[-max_history_messages:]

            system_prompt = await _resolve_system_prompt()
            if system_prompt is None:
                await state.clear()
                await message.answer(
                    "Бот временно недоступен.", reply_markup=_menu_kb()
                )
                return

            try:
                reply_text = await client.send(trimmed, system=system_prompt)
            except ClaudeAllKeysExhaustedError as exc:
                logger.warning(
                    "Claude keys exhausted for tenant %s: %s", tenant_id, exc
                )
                await message.answer(texts.SUPPORT_UNAVAILABLE)
                return
            except ClaudeAPIError as exc:
                logger.warning(
                    "Claude API error for tenant %s: %s", tenant_id, exc
                )
                await message.answer(texts.SUPPORT_BACKEND_ERROR)
                return
            except ClaudeError as exc:
                logger.warning(
                    "Claude error for tenant %s: %s", tenant_id, exc
                )
                await message.answer(texts.SUPPORT_BACKEND_ERROR)
                return

            trimmed.append(ChatMessage(role="assistant", content=reply_text))
            trimmed = trimmed[-max_history_messages:]
            await state.update_data(history=[m.to_api() for m in trimmed])
            await message.answer(reply_text)

    elif devin_enabled:
        dclient: DevinChatClient = cast(DevinChatClient, devin_client)

        @router.message(Support.chatting)
        async def devin_support_message(
            message: Message, state: FSMContext
        ) -> None:
            user_text = (message.text or "").strip()
            if not user_text:
                await message.answer(texts.SUPPORT_EMPTY_INPUT)
                return

            system_prompt = await _resolve_system_prompt()
            if system_prompt is None:
                await state.clear()
                await message.answer(
                    "Бот временно недоступен.", reply_markup=_menu_kb()
                )
                return

            data = await state.get_data()
            raw_session_id = data.get("devin_session_id")
            raw_key_index = data.get("devin_key_index")
            raw_last_event = data.get("devin_last_event_id")
            session_id = (
                raw_session_id if isinstance(raw_session_id, str) else None
            )
            key_index = (
                raw_key_index if isinstance(raw_key_index, int) else None
            )
            last_event_id = (
                raw_last_event if isinstance(raw_last_event, str) else None
            )

            # Tell the user we're working — Devin sessions are slow.
            try:
                thinking_msg = await message.answer(texts.SUPPORT_THINKING)
            except Exception:
                thinking_msg = None

            try:
                if session_id is None or key_index is None:
                    initial_prompt = (
                        f"{system_prompt}\n\n"
                        f"Первое сообщение гостя:\n{user_text}"
                    )
                    reply = await dclient.start_session(prompt=initial_prompt)
                else:
                    try:
                        reply = await dclient.send_message(
                            session_id=session_id,
                            message=user_text,
                            key_index=key_index,
                            last_event_id=last_event_id,
                        )
                    except DevinSessionExpiredError as exc:
                        logger.info(
                            "Devin session %s expired for tenant %s, restarting",
                            exc.session_id,
                            tenant_id,
                        )
                        initial_prompt = (
                            f"{system_prompt}\n\n"
                            f"Первое сообщение гостя:\n{user_text}"
                        )
                        reply = await dclient.start_session(prompt=initial_prompt)
            except DevinAllKeysExhaustedError as exc:
                logger.warning(
                    "Devin keys exhausted for tenant %s: %s", tenant_id, exc
                )
                await message.answer(texts.SUPPORT_UNAVAILABLE)
                return
            except DevinTimeoutError as exc:
                logger.warning(
                    "Devin response timeout for tenant %s: %s", tenant_id, exc
                )
                await message.answer(texts.SUPPORT_TIMEOUT)
                return
            except DevinAPIError as exc:
                logger.warning(
                    "Devin API error for tenant %s: %s", tenant_id, exc
                )
                await message.answer(texts.SUPPORT_BACKEND_ERROR)
                return
            except DevinError as exc:
                logger.warning(
                    "Devin error for tenant %s: %s", tenant_id, exc
                )
                await message.answer(texts.SUPPORT_BACKEND_ERROR)
                return
            finally:
                if thinking_msg is not None:
                    try:
                        await thinking_msg.delete()
                    except Exception:
                        pass

            await state.update_data(
                devin_session_id=reply.session_id,
                devin_key_index=reply.key_index,
                devin_last_event_id=reply.last_event_id,
            )
            await message.answer(reply.text)

    # ---------------- Booking ----------------

    @router.message(F.text == "📅 Забронировать")
    async def start_booking(message: Message, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(Booking.waiting_for_date)
        await message.answer(texts.BOOK_ASK_DATE)

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
        if chosen < datetime.utcnow().date():
            await message.answer(texts.BOOK_DATE_PAST)
            return
        await state.update_data(date_iso=raw)
        await state.set_state(Booking.waiting_for_time)
        await message.answer(texts.BOOK_ASK_TIME)

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
    claude_client: ClaudeClient | None = None,
    claude_history_limit: int = 10,
    claude_system_prompt_override: str | None = None,
    devin_client: DevinChatClient | None = None,
) -> Callable[[int], Dispatcher]:
    """Return a callable that builds a fresh :class:`Dispatcher` per tenant."""

    def factory(tenant_id: int) -> Dispatcher:
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(
            _build_router(
                tenant_id=tenant_id,
                sessionmaker=sessionmaker,
                notifier=notifier,
                claude_client=claude_client,
                claude_history_limit=claude_history_limit,
                claude_system_prompt_override=claude_system_prompt_override,
                devin_client=devin_client,
            )
        )
        return dp

    return factory
