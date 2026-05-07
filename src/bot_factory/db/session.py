"""Async SQLAlchemy engine + sessionmaker setup."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base


def _ensure_sqlite_dir(url: str) -> None:
    """If `url` points at an on-disk SQLite file, make sure its parent dir exists."""
    if not url.startswith("sqlite"):
        return
    # SQLAlchemy URL like "sqlite+aiosqlite:///./data/factory.db".
    # Special case: ":memory:" does not need a directory.
    if ":memory:" in url:
        return
    parsed = urlparse(url)
    # ``parsed.path`` is the part after the scheme — e.g. "/./data/factory.db".
    path = parsed.path.lstrip("/")
    if not path:
        return
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def make_engine_and_sessionmaker(
    url: str,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create the async engine + sessionmaker pair used everywhere else."""
    _ensure_sqlite_dir(url)
    engine = create_async_engine(url, future=True, echo=False)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    return engine, sessionmaker


async def init_db(engine: AsyncEngine) -> None:
    """Create all tables. Idempotent."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
