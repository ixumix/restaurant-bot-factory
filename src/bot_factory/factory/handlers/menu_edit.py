"""Menu editor inside the constructor bot."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...db import repo
from ...db.models import MenuItem
from .. import keyboards, texts
from ..states import AddMenuItem, EditMenuItem
from .common import format_price, is_skip, parse_price_to_minor

router = Router(name="factory.menu_edit")


def _format_menu(items: list[MenuItem]) -> str:
    if not items:
        return texts.MENU_EMPTY
    lines = ["<b>Меню:</b>"]
    last_category: str | None = None
    for item in items:
        category = item.category or None
        if category != last_category:
            if category:
                lines.append(f"\n<b>{category}</b>")
            last_category = category
        flag = "" if item.is_available else " · 🚫 скрыта"
        line = f"• {item.title} — {format_price(item.price_minor, item.currency)}{flag}"
        if item.description:
            line += f"\n   <i>{item.description}</i>"
        lines.append(line)
    return "\n".join(lines)


def _format_item_card(item: MenuItem) -> str:
    return texts.menu_item_card(
        title=item.title,
        description=item.description,
        price_pretty=format_price(item.price_minor, item.currency),
        category=item.category,
        is_available=item.is_available,
    )


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


# ---------------------------------------------------------------------------
# Add new menu item


@router.callback_query(F.data.startswith("menuadd:"))
async def start_add_item(call: CallbackQuery, state: FSMContext) -> None:
    if call.data is None or call.message is None:
        return
    tenant_id = int(call.data.split(":", 1)[1])
    await state.clear()
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
async def receive_price(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    price_minor = parse_price_to_minor(raw)
    if price_minor is None:
        await message.answer(texts.MENU_ADD_PRICE_INVALID)
        return
    await state.update_data(price_minor=price_minor)
    await state.set_state(AddMenuItem.waiting_for_category)
    await message.answer(texts.MENU_ADD_CATEGORY)


@router.message(AddMenuItem.waiting_for_category)
async def receive_category(
    message: Message,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    raw = (message.text or "").strip()
    category = None if not raw or is_skip(raw) else raw
    data = await state.get_data()
    tenant_id = int(data["tenant_id"])
    title = str(data["title"])
    description = data.get("description")
    price_minor = int(data["price_minor"])

    async with sessionmaker() as session:
        await repo.add_menu_item(
            session,
            tenant_id=tenant_id,
            title=title,
            price_minor=price_minor,
            description=description,
            category=category,
        )
        items = list(await repo.get_menu_items(session, tenant_id))

    await state.clear()
    await message.answer(texts.MENU_ADD_OK)
    await message.answer(
        _format_menu(items),
        reply_markup=keyboards.menu_editor_kb(tenant_id, items),
    )


# ---------------------------------------------------------------------------
# Edit existing menu item


@router.callback_query(F.data.startswith("menuedit:"))
async def open_item_editor(
    call: CallbackQuery,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    if call.data is None or call.message is None or call.from_user is None:
        return
    item_id = int(call.data.split(":", 1)[1])
    async with sessionmaker() as session:
        item = await repo.get_menu_item(session, item_id)
        if item is None:
            await call.answer(texts.MENU_ITEM_NOT_FOUND, show_alert=True)
            return
        tenant = await repo.get_tenant(session, item.tenant_id)
        if tenant is None or tenant.owner_id != call.from_user.id:
            await call.answer("Не найдено")
            return
        tenant_id = item.tenant_id
        card = _format_item_card(item)
    await call.message.answer(
        card, reply_markup=keyboards.menu_item_edit_kb(item_id, tenant_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("menufield:"))
async def start_edit_field(
    call: CallbackQuery,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    if call.data is None or call.message is None or call.from_user is None:
        return
    parts = call.data.split(":")
    if len(parts) != 3:
        await call.answer("Bad payload")
        return
    _, item_id_raw, field = parts
    if field not in texts.MENU_EDIT_FIELD_PROMPTS:
        await call.answer("Bad payload")
        return
    try:
        item_id = int(item_id_raw)
    except ValueError:
        await call.answer("Bad payload")
        return

    async with sessionmaker() as session:
        item = await repo.get_menu_item(session, item_id)
        if item is None:
            await call.answer(texts.MENU_ITEM_NOT_FOUND, show_alert=True)
            return
        tenant = await repo.get_tenant(session, item.tenant_id)
        if tenant is None or tenant.owner_id != call.from_user.id:
            await call.answer("Не найдено")
            return

    await state.clear()
    await state.set_state(EditMenuItem.waiting_for_value)
    await state.update_data(item_id=item_id, field=field)
    await call.message.answer(texts.MENU_EDIT_FIELD_PROMPTS[field])
    await call.answer()


@router.message(EditMenuItem.waiting_for_value)
async def apply_field_edit(
    message: Message,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    item_id_raw = data.get("item_id")
    field = data.get("field")
    if not isinstance(item_id_raw, int) or not isinstance(field, str):
        await state.clear()
        return
    item_id = item_id_raw
    raw = (message.text or "").strip()

    # Normalize the value to whatever the column expects.
    value: object
    if field == "title":
        if not raw:
            return
        value = raw
    elif field in {"description", "category"}:
        value = None if not raw or is_skip(raw) else raw
    elif field == "price_minor":
        parsed_price = parse_price_to_minor(raw)
        if parsed_price is None:
            await message.answer(texts.MENU_ADD_PRICE_INVALID)
            return
        value = parsed_price
    else:
        await state.clear()
        return

    async with sessionmaker() as session:
        item = await repo.get_menu_item(session, item_id)
        if item is None:
            await state.clear()
            await message.answer(texts.MENU_ITEM_NOT_FOUND)
            return
        tenant = await repo.get_tenant(session, item.tenant_id)
        if tenant is None or tenant.owner_id != message.from_user.id:
            await state.clear()
            return
        updated = await repo.update_menu_item_field(session, item_id, field, value)
        tenant_id = item.tenant_id
        items = list(await repo.get_menu_items(session, tenant_id))

    await state.clear()
    await message.answer(texts.MENU_EDIT_SAVED)
    if updated is not None:
        await message.answer(
            _format_item_card(updated),
            reply_markup=keyboards.menu_item_edit_kb(item_id, tenant_id),
        )
    await message.answer(
        _format_menu(items),
        reply_markup=keyboards.menu_editor_kb(tenant_id, items),
    )


@router.callback_query(F.data.startswith("menutoggle:"))
async def toggle_availability(
    call: CallbackQuery,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    if call.data is None or call.message is None or call.from_user is None:
        return
    item_id = int(call.data.split(":", 1)[1])
    async with sessionmaker() as session:
        item = await repo.get_menu_item(session, item_id)
        if item is None:
            await call.answer(texts.MENU_ITEM_NOT_FOUND, show_alert=True)
            return
        tenant = await repo.get_tenant(session, item.tenant_id)
        if tenant is None or tenant.owner_id != call.from_user.id:
            await call.answer("Не найдено")
            return
        updated = await repo.toggle_menu_item_availability(session, item_id)
        tenant_id = item.tenant_id
        items = list(await repo.get_menu_items(session, tenant_id))

    if updated is None:
        await call.answer(texts.MENU_ITEM_NOT_FOUND, show_alert=True)
        return
    notice = (
        texts.MENU_ITEM_TOGGLE_VISIBLE
        if updated.is_available
        else texts.MENU_ITEM_TOGGLE_HIDDEN
    )
    await call.answer(notice)
    await call.message.answer(
        _format_menu(items),
        reply_markup=keyboards.menu_editor_kb(tenant_id, items),
    )


# ---------------------------------------------------------------------------
# Delete menu item


@router.callback_query(F.data.startswith("menudel:"))
async def delete_item(
    call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    if call.data is None or call.message is None or call.from_user is None:
        return
    item_id = int(call.data.split(":", 1)[1])
    async with sessionmaker() as session:
        item = await repo.get_menu_item(session, item_id)
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
