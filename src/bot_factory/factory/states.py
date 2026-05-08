"""FSM states for the constructor bot."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class CreateBot(StatesGroup):
    """Wizard: create a new venue + child bot."""

    waiting_for_token = State()
    waiting_for_type = State()
    waiting_for_name = State()
    waiting_for_address = State()
    waiting_for_phone = State()
    waiting_for_hours = State()
    waiting_for_description = State()
    waiting_for_confirm = State()


class EditField(StatesGroup):
    """Owner edits a single text field of an existing tenant."""

    waiting_for_value = State()


class AddMenuItem(StatesGroup):
    """Wizard: append a single item to a tenant's menu."""

    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_price = State()
    waiting_for_category = State()


class EditMenuItem(StatesGroup):
    """Owner edits a single field of an existing menu item."""

    waiting_for_value = State()
