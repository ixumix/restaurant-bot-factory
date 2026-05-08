"""``/`` command lists registered with Telegram via ``set_my_commands``.

Telegram clients show this list in the blue ``/`` menu next to the chat input —
giving users a discoverable surface area without bloating the message history.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand

logger = logging.getLogger(__name__)


FACTORY_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="new", description="Создать нового бота"),
    BotCommand(command="bots", description="Мои боты"),
    BotCommand(command="help", description="Справка"),
    BotCommand(command="whoami", description="Мой Telegram ID"),
    BotCommand(command="cancel", description="Отменить текущий шаг"),
]


CHILD_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Открыть меню заведения"),
    BotCommand(command="book", description="Забронировать"),
    BotCommand(command="menu", description="Посмотреть меню"),
    BotCommand(command="contacts", description="Контакты"),
    BotCommand(command="about", description="О заведении"),
    BotCommand(command="cancel", description="Отменить текущий шаг"),
]


async def set_bot_commands(bot: Bot, commands: list[BotCommand]) -> None:
    """Install ``commands`` as the bot's ``/`` menu. Best-effort — log + ignore."""
    try:
        await bot.set_my_commands(commands)
    except TelegramAPIError as exc:
        logger.warning("Failed to set bot commands: %s", exc)
