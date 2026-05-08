"""Tests for Telegram bot helpers."""

from __future__ import annotations

from bot_factory.telegram import make_telegram_bot

_TOKEN = "123456789:" + "x" * 40


async def test_make_telegram_bot_accepts_proxy_url() -> None:
    bot = make_telegram_bot(_TOKEN, "socks5://127.0.0.1:1080")
    try:
        assert bot.session is not None
    finally:
        await bot.session.close()
