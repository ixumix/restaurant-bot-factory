"""Constructor bot's :class:`Dispatcher` factory."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from .handlers import create_bot, manage, menu_edit, reservations, start

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from ..manager import BotManager


def make_factory_bot(token: str) -> Bot:
    """Create the factory :class:`Bot` instance."""
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def make_factory_dispatcher(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    allowed_owner_ids: set[int],
    manager_provider: Callable[[], BotManager],
) -> Dispatcher:
    """Build a :class:`Dispatcher` for the constructor bot.

    ``manager_provider`` is a callable returning the :class:`BotManager` — we
    pass a callable rather than the instance directly because the manager and
    dispatcher are constructed as a pair and one needs a reference to the other.
    """
    dp = Dispatcher(storage=MemoryStorage())

    # Inject shared dependencies into every handler via aiogram's data dict.
    dp["sessionmaker"] = sessionmaker
    dp["allowed_owner_ids"] = allowed_owner_ids
    dp["manager_provider"] = manager_provider

    dp.include_router(start.router)
    dp.include_router(create_bot.router)
    dp.include_router(manage.router)
    dp.include_router(menu_edit.router)
    dp.include_router(reservations.router)

    return dp
