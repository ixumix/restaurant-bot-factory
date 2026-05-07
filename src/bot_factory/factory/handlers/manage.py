"""List of tenants and per-tenant management screens."""

from __future__ import annotations

from collections.abc import Callable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...db import repo
from ...manager import BotManager
from .. import keyboards, texts
from ..states import EditField
from .common import owner_allowed

router = Router(name="factory.manage")


# ---------------------------------------------------------------------------
# Entry — show list of tenants


async def _show_tenants(
    target: Message, owner_id: int, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with sessionmaker() as session:
        tenants = await repo.get_tenants_by_owner(session, owner_id)
    if not tenants:
        await target.answer(texts.NO_TENANTS)
        return
    await target.answer(
        "Твои заведения:",
        reply_markup=keyboards.tenants_list_kb(tenants),
    )


@router.message(Command("bots"))
@router.message(F.text == "🤖 Мои боты")
async def show_tenants_message(
    message: Message,
    sessionmaker: async_sessionmaker[AsyncSession],
    allowed_owner_ids: set[int],
) -> None:
    if message.from_user is None or not owner_allowed(
        message.from_user.id, allowed_owner_ids
    ):
        await message.answer(texts.NOT_ALLOWED)
        return
    await _show_tenants(message, message.from_user.id, sessionmaker)


@router.callback_query(F.data == "tenants")
async def show_tenants_callback(
    call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    if call.from_user is None or not isinstance(call.message, Message):
        return
    await _show_tenants(call.message, call.from_user.id, sessionmaker)
    await call.answer()


# ---------------------------------------------------------------------------
# Single tenant


@router.callback_query(F.data.startswith("tenant:"))
async def show_tenant(
    call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    if (
        call.data is None
        or not isinstance(call.message, Message)
        or call.from_user is None
    ):
        return
    tenant_id = int(call.data.split(":", 1)[1])
    async with sessionmaker() as session:
        tenant = await repo.get_tenant(session, tenant_id)
    if tenant is None or tenant.owner_id != call.from_user.id:
        await call.answer("Не найдено")
        return
    await call.message.answer(
        texts.tenant_summary(tenant),
        reply_markup=keyboards.tenant_menu_kb(tenant),
    )
    await call.answer()


# ---------------------------------------------------------------------------
# Pause / resume


@router.callback_query(F.data.startswith("pause:"))
async def pause_tenant(
    call: CallbackQuery,
    sessionmaker: async_sessionmaker[AsyncSession],
    manager_provider: Callable[[], BotManager],
) -> None:
    if (
        call.data is None
        or not isinstance(call.message, Message)
        or call.from_user is None
    ):
        return
    tenant_id = int(call.data.split(":", 1)[1])
    async with sessionmaker() as session:
        tenant = await repo.get_tenant(session, tenant_id)
        if tenant is None or tenant.owner_id != call.from_user.id:
            await call.answer("Не найдено")
            return
        await repo.set_tenant_active(session, tenant_id, is_active=False)

    await manager_provider().stop_child(tenant_id)
    await call.message.answer(texts.TENANT_PAUSED)
    await call.answer()


@router.callback_query(F.data.startswith("resume:"))
async def resume_tenant(
    call: CallbackQuery,
    sessionmaker: async_sessionmaker[AsyncSession],
    manager_provider: Callable[[], BotManager],
) -> None:
    if (
        call.data is None
        or not isinstance(call.message, Message)
        or call.from_user is None
    ):
        return
    tenant_id = int(call.data.split(":", 1)[1])
    async with sessionmaker() as session:
        tenant = await repo.get_tenant(session, tenant_id)
        if tenant is None or tenant.owner_id != call.from_user.id:
            await call.answer("Не найдено")
            return
        tenant = await repo.set_tenant_active(session, tenant_id, is_active=True)

    if tenant is not None:
        await manager_provider().spawn_child(tenant)
    await call.message.answer(texts.TENANT_RESUMED)
    await call.answer()


# ---------------------------------------------------------------------------
# Delete tenant


@router.callback_query(F.data.startswith("delete:"))
async def confirm_delete(call: CallbackQuery) -> None:
    if call.data is None or not isinstance(call.message, Message):
        return
    tenant_id = int(call.data.split(":", 1)[1])
    await call.message.answer(
        texts.TENANT_DELETE_CONFIRM,
        reply_markup=keyboards.confirm_delete_kb(tenant_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("deleteconfirm:"))
async def do_delete(
    call: CallbackQuery,
    sessionmaker: async_sessionmaker[AsyncSession],
    manager_provider: Callable[[], BotManager],
) -> None:
    if (
        call.data is None
        or not isinstance(call.message, Message)
        or call.from_user is None
    ):
        return
    tenant_id = int(call.data.split(":", 1)[1])
    async with sessionmaker() as session:
        tenant = await repo.get_tenant(session, tenant_id)
        if tenant is None or tenant.owner_id != call.from_user.id:
            await call.answer("Не найдено")
            return
        await repo.delete_tenant(session, tenant_id)

    await manager_provider().stop_child(tenant_id)
    await call.message.answer(texts.TENANT_DELETED)
    await call.answer()


# ---------------------------------------------------------------------------
# Edit a single field


@router.callback_query(F.data.startswith("edit:"))
async def edit_menu(
    call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    if (
        call.data is None
        or not isinstance(call.message, Message)
        or call.from_user is None
    ):
        return
    tenant_id = int(call.data.split(":", 1)[1])
    async with sessionmaker() as session:
        tenant = await repo.get_tenant(session, tenant_id)
    if tenant is None or tenant.owner_id != call.from_user.id:
        await call.answer("Не найдено")
        return
    await call.message.answer(
        "Что отредактировать?",
        reply_markup=keyboards.edit_fields_kb(tenant_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("editfield:"))
async def start_edit_field(
    call: CallbackQuery,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    if (
        call.data is None
        or not isinstance(call.message, Message)
        or call.from_user is None
    ):
        return
    parts = call.data.split(":")
    if len(parts) != 3:
        await call.answer("Bad payload")
        return
    tenant_id = int(parts[1])
    field = parts[2]
    if field not in texts.EDIT_FIELD_PROMPTS:
        await call.answer("Unknown field")
        return
    async with sessionmaker() as session:
        tenant = await repo.get_tenant(session, tenant_id)
    if tenant is None or tenant.owner_id != call.from_user.id:
        await call.answer("Не найдено")
        return
    await state.set_state(EditField.waiting_for_value)
    await state.update_data(tenant_id=tenant_id, field=field)
    await call.message.answer(texts.EDIT_FIELD_PROMPTS[field])
    await call.answer()


@router.message(EditField.waiting_for_value)
async def receive_edit_value(
    message: Message,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
    manager_provider: Callable[[], BotManager],
) -> None:
    data = await state.get_data()
    tenant_id = int(data["tenant_id"])
    field = str(data["field"])
    new_value = (message.text or "").strip()
    if not new_value:
        return
    async with sessionmaker() as session:
        tenant = await repo.update_tenant_field(session, tenant_id, field, new_value)
    await state.clear()
    await message.answer(texts.EDIT_SAVED)
    if tenant is not None:
        await message.answer(
            texts.tenant_summary(tenant),
            reply_markup=keyboards.tenant_menu_kb(tenant),
        )
        # Restart the child bot so it picks up the new info on its next /start.
        if tenant.is_active:
            await manager_provider().restart_child(tenant)
