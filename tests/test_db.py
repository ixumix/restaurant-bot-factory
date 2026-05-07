"""End-to-end tests for the repository layer using an in-memory SQLite DB."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from bot_factory.db import repo
from bot_factory.db.session import init_db, make_engine_and_sessionmaker


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine, sessionmaker = make_engine_and_sessionmaker(
        "sqlite+aiosqlite:///:memory:"
    )
    await init_db(engine)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


async def _make_owner_and_tenant(
    session: AsyncSession,
) -> tuple[int, int]:
    owner = await repo.get_or_create_owner(
        session, telegram_user_id=42, full_name="Joe", username="joe"
    )
    tenant = await repo.create_tenant(
        session,
        owner_id=owner.telegram_user_id,
        bot_token="123:abc",
        bot_username="joe_pizza_bot",
        business_type="restaurant",
        name="Joe's Pizza",
        address="Pizza Street 1",
        phone="+7 999 000-00-00",
        working_hours="Mon-Sun 12:00-23:00",
    )
    return owner.telegram_user_id, tenant.id


async def test_get_or_create_owner_is_idempotent(session: AsyncSession) -> None:
    o1 = await repo.get_or_create_owner(
        session, telegram_user_id=1, full_name="A", username=None
    )
    o2 = await repo.get_or_create_owner(
        session, telegram_user_id=1, full_name="A", username=None
    )
    assert o1.telegram_user_id == o2.telegram_user_id


async def test_create_tenant_and_list(session: AsyncSession) -> None:
    owner_id, tenant_id = await _make_owner_and_tenant(session)

    tenants = await repo.get_tenants_by_owner(session, owner_id)
    assert len(tenants) == 1
    assert tenants[0].id == tenant_id

    fetched = await repo.get_tenant_by_token(session, "123:abc")
    assert fetched is not None
    assert fetched.id == tenant_id


async def test_active_tenants_filter(session: AsyncSession) -> None:
    _, tenant_id = await _make_owner_and_tenant(session)

    active_before = await repo.list_active_tenants(session)
    assert any(t.id == tenant_id for t in active_before)

    await repo.set_tenant_active(session, tenant_id, is_active=False)

    active_after = await repo.list_active_tenants(session)
    assert all(t.id != tenant_id for t in active_after)


async def test_update_tenant_field(session: AsyncSession) -> None:
    _, tenant_id = await _make_owner_and_tenant(session)
    updated = await repo.update_tenant_field(
        session, tenant_id, "name", "Joe's New Pizza"
    )
    assert updated is not None
    assert updated.name == "Joe's New Pizza"


async def test_update_tenant_field_unknown(session: AsyncSession) -> None:
    _, tenant_id = await _make_owner_and_tenant(session)
    with pytest.raises(ValueError):
        await repo.update_tenant_field(session, tenant_id, "nonsense", "x")


async def test_menu_items_lifecycle(session: AsyncSession) -> None:
    _, tenant_id = await _make_owner_and_tenant(session)

    item = await repo.add_menu_item(
        session,
        tenant_id=tenant_id,
        title="Margherita",
        price_minor=45000,
        description="Classic",
    )
    items = await repo.get_menu_items(session, tenant_id)
    assert len(items) == 1
    assert items[0].id == item.id
    assert items[0].position == 1

    second = await repo.add_menu_item(
        session, tenant_id=tenant_id, title="Coke", price_minor=15000
    )
    assert second.position == 2

    deleted = await repo.delete_menu_item(session, item.id)
    assert deleted
    assert len(await repo.get_menu_items(session, tenant_id)) == 1


async def test_reservations_lifecycle(session: AsyncSession) -> None:
    _, tenant_id = await _make_owner_and_tenant(session)

    await repo.create_reservation(
        session,
        tenant_id=tenant_id,
        customer_name="Alice",
        customer_phone="+7 999 000",
        date_iso="2030-01-01",
        time_iso="19:00",
        party_size=4,
        comment="Birthday",
    )
    res = await repo.get_recent_reservations(session, tenant_id)
    assert len(res) == 1
    assert res[0].customer_name == "Alice"
    assert res[0].comment == "Birthday"


async def test_delete_tenant_cascades(session: AsyncSession) -> None:
    _, tenant_id = await _make_owner_and_tenant(session)
    await repo.add_menu_item(
        session, tenant_id=tenant_id, title="x", price_minor=100
    )
    await repo.create_reservation(
        session,
        tenant_id=tenant_id,
        customer_name="A",
        customer_phone="123",
        date_iso="2030-01-01",
        time_iso="19:00",
        party_size=2,
    )
    assert await repo.delete_tenant(session, tenant_id)

    assert await repo.get_tenant(session, tenant_id) is None
    assert (await repo.get_menu_items(session, tenant_id)) == []
    assert (await repo.get_recent_reservations(session, tenant_id)) == []
