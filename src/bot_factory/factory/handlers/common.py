"""Helpers shared by multiple factory handlers."""

from __future__ import annotations

import logging
import re

from aiogram.exceptions import TelegramAPIError

from ...telegram import make_telegram_bot

logger = logging.getLogger(__name__)

# Telegram bot tokens look like ``<bot_id>:<35-character-base64-secret>``.
_TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")


def owner_allowed(user_id: int, allowed_ids: set[int]) -> bool:
    """Empty allowlist means "everyone is allowed"."""
    if not allowed_ids:
        return True
    return user_id in allowed_ids


def looks_like_token(text: str) -> bool:
    """Quick syntactic check before bothering Telegram."""
    return bool(_TOKEN_RE.match(text.strip()))


async def fetch_bot_info(
    token: str, proxy_url: str | None = None
) -> tuple[str, str] | None:
    """Call ``getMe`` for ``token``. Returns ``(username, first_name)`` or ``None``."""
    bot = make_telegram_bot(token, proxy_url)
    try:
        me = await bot.get_me()
    except TelegramAPIError as exc:
        logger.warning("getMe failed: %s", exc)
        return None
    finally:
        await bot.session.close()
    if me.username is None:
        return None
    return me.username, me.first_name


def is_skip(text: str) -> bool:
    """Did the user type something that means "пропустить"?"""
    return text.strip().lower() in {"пропустить", "skip", "-", "—", "нет"}


def parse_price_to_minor(text: str) -> int | None:
    """Parse "450" / "450.5" / "450,50" → minor units (kopecks)."""
    cleaned = text.strip().replace(",", ".").replace(" ", "")
    if not cleaned:
        return None
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    if amount < 0:
        return None
    return round(amount * 100)


def format_price(price_minor: int, currency: str) -> str:
    major = price_minor // 100
    minor = price_minor % 100
    body = f"{major}" if minor == 0 else f"{major}.{minor:02d}"
    suffix = "₽" if currency == "RUB" else currency
    return f"{body} {suffix}"
