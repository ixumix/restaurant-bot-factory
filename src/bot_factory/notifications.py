"""Owner notifications routed through the constructor bot.

Both the constructor bot and any child bot can call :class:`Notifier` to send a
message to a venue owner — the owner has already started the constructor bot
(that's how they registered), so we are guaranteed to be able to reach them.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)


class Notifier:
    """Send messages to venue owners using the constructor bot."""

    def __init__(self, factory_bot: Bot) -> None:
        self._bot = factory_bot

    async def notify_owner(self, owner_telegram_id: int, text: str) -> None:
        """Best-effort delivery — log and swallow Telegram errors."""
        try:
            await self._bot.send_message(owner_telegram_id, text)
        except TelegramAPIError as exc:
            logger.warning(
                "Failed to notify owner %s: %s", owner_telegram_id, exc
            )
