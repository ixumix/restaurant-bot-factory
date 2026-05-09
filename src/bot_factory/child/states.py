"""FSM states for the child booking flow."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Booking(StatesGroup):
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_party = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_comment = State()
    waiting_for_confirm = State()


class Support(StatesGroup):
    """Live support chat with the AI assistant (Claude)."""

    chatting = State()
