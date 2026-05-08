"""SQLAlchemy ORM models for the bot factory."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    """Timezone-aware UTC "now" used as the default for ``created_at`` columns."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class Owner(Base):
    """A venue owner — the user that talks to the constructor bot."""

    __tablename__ = "owners"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tenants: Mapped[list[Tenant]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Tenant(Base):
    """A single venue and its child bot."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("owners.telegram_user_id", ondelete="CASCADE")
    )
    bot_token: Mapped[str] = mapped_column(String(128), unique=True)
    bot_username: Mapped[str] = mapped_column(String(64))
    business_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    working_hours: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    owner: Mapped[Owner] = relationship(back_populates="tenants")
    menu_items: Mapped[list[MenuItem]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
        order_by="MenuItem.position",
    )
    reservations: Mapped[list[Reservation]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
        order_by="Reservation.created_at.desc()",
    )


class MenuItem(Base):
    """A single dish / drink / banquet package."""

    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE")
    )
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Stored in minor units (e.g. kopecks) to avoid floating-point arithmetic.
    price_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    photo_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    tenant: Mapped[Tenant] = relationship(back_populates="menu_items")


class Reservation(Base):
    """A booking request submitted via a child bot."""

    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE")
    )
    customer_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    customer_name: Mapped[str] = mapped_column(String(255))
    customer_phone: Mapped[str] = mapped_column(String(64))
    date_iso: Mapped[str] = mapped_column(String(16))  # YYYY-MM-DD
    time_iso: Mapped[str] = mapped_column(String(8))  # HH:MM
    party_size: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tenant: Mapped[Tenant] = relationship(back_populates="reservations")
