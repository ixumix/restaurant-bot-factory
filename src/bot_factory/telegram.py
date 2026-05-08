"""Telegram Bot construction helpers."""

from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode


def make_telegram_bot(token: str, proxy_url: str | None = None) -> Bot:
    """Create a Telegram bot with shared defaults and optional proxy."""
    session = AiohttpSession(proxy=proxy_url) if proxy_url else None
    return Bot(
        token=token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
