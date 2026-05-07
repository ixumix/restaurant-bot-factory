"""Menu editor inside the constructor bot."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...db import repo
from ...db.models import MenuItem
from .. import keyboards, texts
from ..states import AddMenuItem
from .common import format_price, is_skip, parse_price_to_minor

router = Router(name="factory.menu_edit")


def _format_menu(items: list[MenuItem]) -> str:
    if not items:
        return texts.MENU_EMPTY
    lines = ["<b>Меню:</b>"]
    for item in items:
        line = f"• {item.title} — {format_price(item.price_minor, item.currency)}"
        if item.description:
            line += f"\n   <i>{item.description}</i>"
        lines.append(line)
    return "\n".join(lines)


@router.callback_query(F.data.startswith("menu:"))
async def show_menu(
    call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    if call.data is None or call.message is None or call.from_user is None:
        return
    tenant_id = int(call.data.split(":", 1)[1])
    async with sessionmaker() as session:
        tenant = await repo.get_tenant(session, tenant_id)
        if tenant is None or tenant.owner_id != call.from_user.id:
            await call.answer("Не найдено")
            return
        items = list(await repo.get_menu_items(session, tenant_id))
    await call.message.answer(
        _format_menu(items),
        reply_markup=keyboards.menu_editor_kb(tenant_id, items),
    )
    await call.answer()


@router.callback_query(F.data.startswith("menuadd:"))
async def start_add_item(call: CallbackQuery, state: FSMContext) -> None:
    if call.data is None or call.message is None:
        return
    tenant_id = int(call.data.split(":", 1)[1])
    await state.set_state(AddMenuItem.waiting_for_title)
    await state.update_data(tenant_id=tenant_id)
    await call.message.answer(texts.MENU_ADD_TITLE)
    await call.answer()


@router.message(AddMenuItem.waiting_for_title)
async def receive_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        return
    await state.update_data(title=title)
    await state.set_state(AddMenuItem.waiting_for_description)
    await message.answer(texts.MENU_ADD_DESCRIPTION)


@router.message(AddMenuItem.waiting_for_description)
async def receive_description(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    description = None if not raw or is_skip(raw) else raw
    await state.update_data(description=description)
    await state.set_state(AddMenuItem.waiting_for_price)
    await message.answer(texts.MENU_ADD_PRICE)


@router.message(AddMenuItem.waiting_for_price)
async def receive_price(
    message: Message,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    raw = (message.text or "").strip()
    price_minor = parse_price_to_minor(raw)
    if price_minor is None:
        await message.answer(texts.MENU_ADD_PRICE_INVALID)
        return
    data = await state.get_data()
    tenant_id = int(data["tenant_id"])
    title = str(data["title"])
    description = data.get("description")

    async with sessionmaker() as session:
        await repo.add_menu_item(
            session,
            tenant_id=tenant_id,
            title=title,
            price_minor=price_minor,
            description=description,
        )
        items = list(await repo.get_menu_items(session, tenant_id))

    await state.clear()
    await message.answer(texts.MENU_ADD_OK)
    await message.answer(
        _format_menu(items),
        reply_markup=keyboards.menu_editor_kb(tenant_id, items),
    )


@router.callback_query(F.data.startswith("menudel:"))
async def delete_item(
    call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    if call.data is None or call.message is None or call.from_user is None:
        return
    item_id = int(call.data.split(":", 1)[1])
    async with sessionmaker() as session:
        from ...db.models import MenuItem  # local import to avoid a cycle

        item = await session.get(MenuItem, item_id)
        if item is None:
            await call.answer("Уже удалено")
            return
        tenant = await repo.get_tenant(session, item.tenant_id)
        if tenant is None or tenant.owner_id != call.from_user.id:
            await call.answer("Не найдено")
            return
        await repo.delete_menu_item(session, item_id)
        items = list(await repo.get_menu_items(session, item.tenant_id))
        tenant_id = item.tenant_id

    await call.message.answer(texts.MENU_ITEM_DELETED)
    await call.message.answer(
        _format_menu(items),
        reply_markup=keyboards.menu_editor_kb(tenant_id, items),
    )
    await call.answer()
