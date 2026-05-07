"""`/start` and `/help`."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...db import repo
from .. import keyboards, texts
from .common import owner_allowed

router = Router(name="factory.start")


@router.message(CommandStart())
async def handle_start(
    message: Message,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
    allowed_owner_ids: set[int],
) -> None:
    if message.from_user is None:
        return
    if not owner_allowed(message.from_user.id, allowed_owner_ids):
        await message.answer(texts.NOT_ALLOWED)
        return

    await state.clear()
    async with sessionmaker() as session:
        await repo.get_or_create_owner(
            session,
            telegram_user_id=message.from_user.id,
            full_name=message.from_user.full_name,
            username=message.from_user.username,
        )

    await message.answer(texts.START, reply_markup=keyboards.main_menu_kb())


@router.message(Command("help"))
@router.message(lambda m: isinstance(m.text, str) and m.text.strip() == "ℹ️ Помощь")
async def handle_help(message: Message, allowed_owner_ids: set[int]) -> None:
    if message.from_user is None or not owner_allowed(
        message.from_user.id, allowed_owner_ids
    ):
        await message.answer(texts.NOT_ALLOWED)
        return
    await message.answer(texts.HELP)


@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Окей, отменил. Что делаем дальше?", reply_markup=keyboards.main_menu_kb()
    )
