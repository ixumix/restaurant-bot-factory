"""Thin repository layer over the SQLAlchemy models.

Functions here take an :class:`AsyncSession` and never hold references to the
session past their own scope.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import MenuItem, Owner, Reservation, Tenant

RESERVATION_STATUS_VALUES = frozenset({"new", "confirmed", "declined", "cancelled", "done"})

# ---------------------------------------------------------------------------
# Owners


async def get_or_create_owner(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    full_name: str,
    username: str | None,
) -> Owner:
    """Idempotently fetch the :class:`Owner` for ``telegram_user_id``."""
    owner = await session.get(Owner, telegram_user_id)
    if owner is None:
        owner = Owner(
            telegram_user_id=telegram_user_id,
            full_name=full_name,
            username=username,
        )
        session.add(owner)
        await session.commit()
    return owner


# ---------------------------------------------------------------------------
# Tenants


async def get_tenant_by_token(session: AsyncSession, token: str) -> Tenant | None:
    """Return the tenant that uses ``token`` for its child bot, if any."""
    stmt = select(Tenant).where(Tenant.bot_token == token)
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_tenant(
    session: AsyncSession,
    *,
    owner_id: int,
    bot_token: str,
    bot_username: str,
    business_type: str,
    name: str,
    description: str | None = None,
    address: str | None = None,
    phone: str | None = None,
    working_hours: str | None = None,
) -> Tenant:
    """Persist a new tenant. Caller is responsible for token uniqueness."""
    tenant = Tenant(
        owner_id=owner_id,
        bot_token=bot_token,
        bot_username=bot_username,
        business_type=business_type,
        name=name,
        description=description,
        address=address,
        phone=phone,
        working_hours=working_hours,
        is_active=True,
    )
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def get_tenants_by_owner(
    session: AsyncSession, owner_id: int
) -> Sequence[Tenant]:
    stmt = (
        select(Tenant)
        .where(Tenant.owner_id == owner_id)
        .order_by(Tenant.created_at.desc())
    )
    return (await session.execute(stmt)).scalars().all()


async def get_tenant(session: AsyncSession, tenant_id: int) -> Tenant | None:
    return await session.get(Tenant, tenant_id)


async def list_active_tenants(session: AsyncSession) -> Sequence[Tenant]:
    stmt = select(Tenant).where(Tenant.is_active.is_(True))
    return (await session.execute(stmt)).scalars().all()


async def update_tenant_field(
    session: AsyncSession, tenant_id: int, field: str, value: object
) -> Tenant | None:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        return None
    if not hasattr(tenant, field):
        msg = f"Unknown tenant field: {field!r}"
        raise ValueError(msg)
    setattr(tenant, field, value)
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def set_tenant_active(
    session: AsyncSession, tenant_id: int, *, is_active: bool
) -> Tenant | None:
    return await update_tenant_field(session, tenant_id, "is_active", is_active)


async def delete_tenant(session: AsyncSession, tenant_id: int) -> bool:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        return False
    await session.delete(tenant)
    await session.commit()
    return True


# ---------------------------------------------------------------------------
# Menu items


async def add_menu_item(
    session: AsyncSession,
    *,
    tenant_id: int,
    title: str,
    price_minor: int,
    description: str | None = None,
    category: str | None = None,
    currency: str = "RUB",
    photo_file_id: str | None = None,
) -> MenuItem:
    # Position = max(existing position) + 1 so items render in insertion order.
    stmt = (
        select(MenuItem.position)
        .where(MenuItem.tenant_id == tenant_id)
        .order_by(MenuItem.position.desc())
        .limit(1)
    )
    last = (await session.execute(stmt)).scalar_one_or_none()
    position = (last or 0) + 1
    item = MenuItem(
        tenant_id=tenant_id,
        title=title,
        description=description,
        price_minor=price_minor,
        currency=currency,
        category=category,
        photo_file_id=photo_file_id,
        position=position,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def get_menu_items(
    session: AsyncSession, tenant_id: int, *, only_available: bool = False
) -> Sequence[MenuItem]:
    stmt = (
        select(MenuItem)
        .where(MenuItem.tenant_id == tenant_id)
        .order_by(MenuItem.position)
    )
    if only_available:
        stmt = stmt.where(MenuItem.is_available.is_(True))
    return (await session.execute(stmt)).scalars().all()


async def delete_menu_item(session: AsyncSession, item_id: int) -> bool:
    item = await session.get(MenuItem, item_id)
    if item is None:
        return False
    await session.delete(item)
    await session.commit()
    return True


# Fields the owner can edit on an existing :class:`MenuItem` from the UI.
_EDITABLE_MENU_ITEM_FIELDS: frozenset[str] = frozenset(
    {"title", "description", "price_minor", "category", "is_available"}
)


async def get_menu_item(session: AsyncSession, item_id: int) -> MenuItem | None:
    return await session.get(MenuItem, item_id)


async def update_menu_item_field(
    session: AsyncSession, item_id: int, field: str, value: object
) -> MenuItem | None:
    if field not in _EDITABLE_MENU_ITEM_FIELDS:
        msg = f"Unknown menu item field: {field!r}"
        raise ValueError(msg)
    item = await session.get(MenuItem, item_id)
    if item is None:
        return None
    setattr(item, field, value)
    await session.commit()
    await session.refresh(item)
    return item


async def toggle_menu_item_availability(
    session: AsyncSession, item_id: int
) -> MenuItem | None:
    item = await session.get(MenuItem, item_id)
    if item is None:
        return None
    item.is_available = not item.is_available
    await session.commit()
    await session.refresh(item)
    return item


# ---------------------------------------------------------------------------
# Reservations


async def create_reservation(
    session: AsyncSession,
    *,
    tenant_id: int,
    customer_name: str,
    customer_phone: str,
    date_iso: str,
    time_iso: str,
    party_size: int,
    customer_telegram_id: int | None = None,
    comment: str | None = None,
) -> Reservation:
    reservation = Reservation(
        tenant_id=tenant_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        date_iso=date_iso,
        time_iso=time_iso,
        party_size=party_size,
        customer_telegram_id=customer_telegram_id,
        comment=comment,
    )
    session.add(reservation)
    await session.commit()
    await session.refresh(reservation)
    return reservation


async def get_reservation(session: AsyncSession, reservation_id: int) -> Reservation | None:
    return await session.get(Reservation, reservation_id)


async def update_reservation_status(
    session: AsyncSession, reservation_id: int, status: str
) -> Reservation | None:
    if status not in RESERVATION_STATUS_VALUES:
        msg = f"Unknown reservation status: {status!r}"
        raise ValueError(msg)
    reservation = await session.get(Reservation, reservation_id)
    if reservation is None:
        return None
    reservation.status = status
    await session.commit()
    await session.refresh(reservation)
    return reservation


async def get_recent_reservations(
    session: AsyncSession, tenant_id: int, *, limit: int = 10
) -> Sequence[Reservation]:
    stmt = (
        select(Reservation)
        .where(Reservation.tenant_id == tenant_id)
        .order_by(Reservation.created_at.desc())
        .limit(limit)
    )
    return (await session.execute(stmt)).scalars().all()
