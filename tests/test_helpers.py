"""Tests for small pure helpers."""

from __future__ import annotations

from bot_factory.factory import texts
from bot_factory.factory.common_format import format_price
from bot_factory.factory.handlers.common import (
    is_skip,
    looks_like_token,
    owner_allowed,
    parse_price_to_minor,
)


def test_owner_allowed_empty_allowlist() -> None:
    assert owner_allowed(123, set()) is True


def test_owner_allowed_specific_user() -> None:
    assert owner_allowed(1, {1, 2}) is True
    assert owner_allowed(99, {1, 2}) is False


def test_looks_like_token_accepts_real_shape() -> None:
    assert looks_like_token("123456789:AAEhBOweik6ad9r-someTokenXYZxyzABCDEFGHI")
    assert looks_like_token("12345678:" + "x" * 40)


def test_looks_like_token_rejects_garbage() -> None:
    assert not looks_like_token("hello")
    assert not looks_like_token("12:short")
    assert not looks_like_token("")
    assert not looks_like_token("123:AAA")


def test_is_skip_recognises_variants() -> None:
    assert is_skip("пропустить")
    assert is_skip("Skip")
    assert is_skip(" - ")
    assert is_skip("—")
    assert not is_skip("no, thanks")


def test_parse_price_to_minor_integer_and_decimal() -> None:
    assert parse_price_to_minor("450") == 45000
    assert parse_price_to_minor("450.50") == 45050
    assert parse_price_to_minor("450,5") == 45050
    assert parse_price_to_minor(" 1 000 ") == 100000


def test_parse_price_to_minor_invalid() -> None:
    assert parse_price_to_minor("abc") is None
    assert parse_price_to_minor("-5") is None
    assert parse_price_to_minor("") is None


def test_format_price_rounding() -> None:
    assert format_price(45000, "RUB") == "450 ₽"
    assert format_price(45050, "RUB") == "450.50 ₽"
    assert format_price(100, "USD") == "1 USD"


def test_reservation_line_includes_status_and_id() -> None:
    line = texts.reservation_line(
        "2030-01-01",
        "19:00",
        4,
        "Alice",
        "+7 999 000",
        "confirmed",
        reservation_id=15,
    )
    assert line == "#15 · 📅 2030-01-01 19:00 · 4 гост. · Alice · +7 999 000 · подтверждена"


def test_customer_reservation_status_notification() -> None:
    message = texts.customer_reservation_status_notification(
        venue_name="Joe's Pizza",
        date_iso="2030-01-01",
        time_iso="19:00",
        party_size=4,
        status="declined",
    )
    assert "не смогло подтвердить" in message
    assert "Joe's Pizza" in message
