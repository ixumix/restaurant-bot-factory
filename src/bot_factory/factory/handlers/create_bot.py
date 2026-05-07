"""Wizard: create a new venue + child bot."""

from __future__ import annotations

import logging
from collections.abc import Callable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...db import repo
from ...manager import BotManager
from .. import keyboards, texts
from ..states import CreateBot
from .common import (
    fetch_bot_info,
    is_skip,
    looks_like_token,
    owner_allowed,
)

router = Router(name="factory.create_bot")
logger = logging.getLogger(__name__)


@router.message(Command("new"))
@router.message(F.text == "➕ Создать бота")
async def start_create_flow(
    message: Message,
    state: FSMContext,
    allowed_owner_ids: set[int],
) -> None:
    if message.from_user is None or not owner_allowed(
        message.from_user.id, allowed_owner_ids
    ):
        await message.answer(texts.NOT_ALLOWED)
        return
    await state.clear()
    await state.set_state(CreateBot.waiting_for_token)
    await message.answer(texts.CREATE_ASK_TOKEN)


@router.message(CreateBot.waiting_for_token)
async def receive_token(
    message: Message,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    raw = (message.text or "").strip()
    if not looks_like_token(raw):
        await message.answer(texts.CREATE_TOKEN_INVALID)
        return

    async with sessionmaker() as session:
        existing = await repo.get_tenant_by_token(session, raw)
    if existing is not None:
        await message.answer(texts.CREATE_TOKEN_TAKEN)
        return

    info = await fetch_bot_info(raw)
    if info is None:
        await message.answer(texts.CREATE_TOKEN_BAD)
        return
    bot_username, _ = info

    await state.update_data(bot_token=raw, bot_username=bot_username)
    await state.set_state(CreateBot.waiting_for_type)
    await message.answer(texts.CREATE_ASK_TYPE, reply_markup=keyboards.business_type_kb())


@router.callback_query(CreateBot.waiting_for_type, F.data.startswith("type:"))
async def receive_type(call: CallbackQuery, state: FSMContext) -> None:
    if call.data is None or call.message is None:
        return
    code = call.data.split(":", 1)[1]
    if code not in texts.BUSINESS_TYPE_LABELS:
        await call.answer("Неизвестный тип")
        return
    await state.update_data(business_type=code)
    await state.set_state(CreateBot.waiting_for_name)
    await call.message.answer(texts.CREATE_ASK_NAME)
    await call.answer()


@router.callback_query(F.data == "create:cancel")
async def cancel_create(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if call.message is not None:
        await call.message.answer(
            texts.CREATE_CANCELLED, reply_markup=keyboards.main_menu_kb()
        )
    await call.answer()


@router.message(CreateBot.waiting_for_name)
async def receive_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        return
    if len(name) > 100:
        await message.answer(texts.CREATE_NAME_TOO_LONG)
        return
    await state.update_data(name=name)
    await state.set_state(CreateBot.waiting_for_address)
    await message.answer(texts.CREATE_ASK_ADDRESS)


def _maybe(text: str) -> str | None:
    text = text.strip()
    if not text or is_skip(text):
        return None
    return text


@router.message(CreateBot.waiting_for_address)
async def receive_address(message: Message, state: FSMContext) -> None:
    await state.update_data(address=_maybe(message.text or ""))
    await state.set_state(CreateBot.waiting_for_phone)
    await message.answer(texts.CREATE_ASK_PHONE)


@router.message(CreateBot.waiting_for_phone)
async def receive_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=_maybe(message.text or ""))
    await state.set_state(CreateBot.waiting_for_hours)
    await message.answer(texts.CREATE_ASK_HOURS)


@router.message(CreateBot.waiting_for_hours)
async def receive_hours(message: Message, state: FSMContext) -> None:
    await state.update_data(working_hours=_maybe(message.text or ""))
    await state.set_state(CreateBot.waiting_for_description)
    await message.answer(texts.CREATE_ASK_DESCRIPTION)


@router.message(CreateBot.waiting_for_description)
async def receive_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=_maybe(message.text or ""))
    data = await state.get_data()
    summary = texts.create_summary(
        bot_username=data["bot_username"],
        business_type=data["business_type"],
        name=data["name"],
        address=data.get("address"),
        phone=data.get("phone"),
        working_hours=data.get("working_hours"),
        description=data.get("description"),
    )
    await state.set_state(CreateBot.waiting_for_confirm)
    await message.answer(summary, reply_markup=keyboards.confirm_create_kb())


@router.callback_query(CreateBot.waiting_for_confirm, F.data == "create:save")
async def confirm_create(
    call: CallbackQuery,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
    manager_provider: Callable[[], BotManager],
) -> None:
    if call.from_user is None or call.message is None:
        return
    data = await state.get_data()
    await state.clear()

    try:
        async with sessionmaker() as session:
            await repo.get_or_create_owner(
                session,
                telegram_user_id=call.from_user.id,
                full_name=call.from_user.full_name,
                username=call.from_user.username,
            )
            tenant = await repo.create_tenant(
                session,
                owner_id=call.from_user.id,
                bot_token=data["bot_token"],
                bot_username=data["bot_username"],
                business_type=data["business_type"],
                name=data["name"],
                address=data.get("address"),
                phone=data.get("phone"),
                working_hours=data.get("working_hours"),
                description=data.get("description"),
            )
    except IntegrityError:
        await call.message.answer(texts.CREATE_TOKEN_TAKEN)
        await call.answer()
        return
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to create tenant")
        await call.message.answer(texts.CREATE_DB_ERROR)
        await call.answer()
        return

    manager = manager_provider()
    await manager.spawn_child(tenant)

    await call.message.answer(
        texts.created_ok(tenant.bot_username),
        reply_markup=keyboards.main_menu_kb(),
    )
    await call.answer("Готово!")
