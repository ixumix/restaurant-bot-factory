"""Runtime manager for child bots.

Each venue gets its own :class:`Bot` and :class:`Dispatcher`. The manager runs
all of them — plus the constructor bot — concurrently in a single event loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher

from .telegram import make_telegram_bot

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from .db.models import Tenant
    from .notifications import Notifier

logger = logging.getLogger(__name__)


# Type of the function that builds a fresh Dispatcher for a single tenant.
ChildDispatcherFactory = Callable[[int], Dispatcher]
# Type of the function that returns the list of currently active tenants.
ActiveTenantsLoader = Callable[[], Awaitable[list["Tenant"]]]


class BotManager:
    """Owns the constructor bot, all child bots and their lifecycles."""

    def __init__(
        self,
        *,
        factory_bot: Bot,
        factory_dispatcher: Dispatcher,
        sessionmaker: async_sessionmaker[AsyncSession],
        notifier: Notifier,
        child_dispatcher_factory: ChildDispatcherFactory,
        active_tenants_loader: ActiveTenantsLoader,
        telegram_proxy_url: str | None = None,
    ) -> None:
        self._factory_bot = factory_bot
        self._factory_dp = factory_dispatcher
        self._sessionmaker = sessionmaker
        self._notifier = notifier
        self._make_child_dp = child_dispatcher_factory
        self._load_active = active_tenants_loader
        self._telegram_proxy_url = telegram_proxy_url

        # tenant_id → (Bot, asyncio.Task running its polling loop)
        self._children: dict[int, tuple[Bot, asyncio.Task[None]]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ public

    async def start(self) -> None:
        """Spawn pollers for the constructor bot and every active tenant."""
        for tenant in await self._load_active():
            await self.spawn_child(tenant)

        logger.info(
            "BotManager: starting factory bot polling (%d child bots already running)",
            len(self._children),
        )
        # The factory dispatcher's polling loop "owns" the main task; child loops
        # run alongside as background tasks.
        await self._factory_dp.start_polling(self._factory_bot)

    async def shutdown(self) -> None:
        """Cancel every child poller and close every Bot session."""
        async with self._lock:
            for tenant_id in list(self._children):
                await self._stop_child_locked(tenant_id)
        await self._factory_bot.session.close()

    async def spawn_child(self, tenant: Tenant) -> None:
        """Start a long-polling task for a single tenant."""
        async with self._lock:
            if tenant.id in self._children:
                logger.debug("Child bot for tenant %s already running", tenant.id)
                return
            await self._start_child_locked(tenant)

    async def stop_child(self, tenant_id: int) -> None:
        """Cancel a tenant's polling task. No-op if it's not running."""
        async with self._lock:
            await self._stop_child_locked(tenant_id)

    async def restart_child(self, tenant: Tenant) -> None:
        """Stop and start a tenant's child bot — useful after edits."""
        async with self._lock:
            await self._stop_child_locked(tenant.id)
            await self._start_child_locked(tenant)

    def is_running(self, tenant_id: int) -> bool:
        return tenant_id in self._children

    # --------------------------------------------------------------- internals

    async def _start_child_locked(self, tenant: Tenant) -> None:
        bot = make_telegram_bot(tenant.bot_token, self._telegram_proxy_url)
        dp = self._make_child_dp(tenant.id)

        async def runner(child_bot: Bot, child_dp: Dispatcher, tid: int) -> None:
            try:
                await child_dp.start_polling(child_bot)
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - logging only
                logger.exception("Child bot polling crashed for tenant %s", tid)
            finally:
                await child_bot.session.close()

        task = asyncio.create_task(
            runner(bot, dp, tenant.id), name=f"child-bot-{tenant.id}"
        )
        self._children[tenant.id] = (bot, task)
        logger.info("Started child bot for tenant %s (@%s)", tenant.id, tenant.bot_username)

    async def _stop_child_locked(self, tenant_id: int) -> None:
        entry = self._children.pop(tenant_id, None)
        if entry is None:
            return
        bot, task = entry
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # ``runner`` already closes the session on normal exit. ``close()`` is
        # idempotent on aiogram's BaseSession so calling it again is safe.
        await bot.session.close()
        logger.info("Stopped child bot for tenant %s", tenant_id)
