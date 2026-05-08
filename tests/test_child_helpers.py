"""Tests for the child bot's small helpers and the booking date keyboard."""

from __future__ import annotations

from datetime import date, timedelta

from bot_factory.child import keyboards as child_keyboards
from bot_factory.child.handlers import _is_skip, _phone_is_valid


def test_phone_is_valid_accepts_long_enough_digits() -> None:
    assert _phone_is_valid("+7 (999) 123-45-67")
    assert _phone_is_valid("89991234567")
    assert _phone_is_valid("+1 415 555 0100")


def test_phone_is_valid_rejects_short_or_garbage() -> None:
    assert not _phone_is_valid("12-3")
    assert not _phone_is_valid("")
    assert not _phone_is_valid("phone please")
    assert not _phone_is_valid("+++")


def test_child_is_skip_recognises_variants() -> None:
    assert _is_skip("пропустить")
    assert _is_skip(" Skip ")
    assert _is_skip("—")
    assert _is_skip("-")
    assert _is_skip("Нет")
    assert not _is_skip("with bbq sauce please")


def test_booking_date_kb_offers_today_through_next_week() -> None:
    today = date(2030, 1, 6)  # a Sunday — exercises the weekday formatter
    kb = child_keyboards.booking_date_kb(today=today)

    # 4 quick-pick rows + 1 cancel row.
    assert len(kb.inline_keyboard) == 5

    expected_dates = [today + timedelta(days=offset) for offset in (0, 1, 2, 7)]
    actual_dates: list[str] = []
    for row in kb.inline_keyboard[:4]:
        assert len(row) == 1
        button = row[0]
        assert button.callback_data is not None
        assert button.callback_data.startswith("bookdate:")
        actual_dates.append(button.callback_data.split(":", 1)[1])

    assert actual_dates == [d.isoformat() for d in expected_dates]
    # The last row is a single cancel button.
    cancel_row = kb.inline_keyboard[-1]
    assert len(cancel_row) == 1
    assert cancel_row[0].callback_data == "book:cancel"


def test_quick_date_label_includes_human_readable_weekday() -> None:
    monday = date(2030, 1, 7)
    kb = child_keyboards.booking_date_kb(today=monday)
    today_button = kb.inline_keyboard[0][0]
    assert today_button.text is not None
    # Russian "Пн" is "Monday".
    assert "Пн" in today_button.text
    assert "07.01" in today_button.text
