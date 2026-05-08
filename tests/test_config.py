"""Tests for :mod:`bot_factory.config`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bot_factory.config import Settings


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FACTORY_BOT_TOKEN", "1:abc")
    monkeypatch.setenv("ALLOWED_OWNER_IDS", " 111 , 222,333 ")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("TELEGRAM_PROXY_URL", " socks5://127.0.0.1:1080 ")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.factory_bot_token == "1:abc"
    assert s.allowed_owner_id_set == {111, 222, 333}
    assert s.log_level == "DEBUG"
    assert s.database_url.startswith("sqlite+aiosqlite")
    assert s.telegram_proxy_url_value == "socks5://127.0.0.1:1080"


def test_settings_empty_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FACTORY_BOT_TOKEN", "1:abc")
    monkeypatch.delenv("ALLOWED_OWNER_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_PROXY_URL", raising=False)

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.allowed_owner_id_set == set()
    assert s.telegram_proxy_url_value is None


def test_settings_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FACTORY_BOT_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
