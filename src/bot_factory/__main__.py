"""Entry point: wire everything together and run forever."""

from __future__ import annotations

import asyncio
import logging
import signal

from .child.handlers import make_child_dispatcher_factory
from .config import load_settings
from .db import repo
from .db.models import Tenant
from .db.session import init_db, make_engine_and_sessionmaker
from .factory.bot import make_factory_bot, make_factory_dispatcher
from .logging_setup import setup_logging
from .manager import BotManager
from .notifications import Notifier

logger = logging.getLogger(__name__)


async def amain() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    engine, sessionmaker = make_engine_and_sessionmaker(settings.database_url)
    await init_db(engine)

    factory_bot = make_factory_bot(settings.factory_bot_token)
    notifier = Notifier(factory_bot)
    child_dp_factory = make_child_dispatcher_factory(
        sessionmaker=sessionmaker, notifier=notifier
    )

    manager_holder: dict[str, BotManager] = {}

    def manager_provider() -> BotManager:
        return manager_holder["manager"]

    factory_dp = make_factory_dispatcher(
        sessionmaker=sessionmaker,
        allowed_owner_ids=settings.allowed_owner_id_set,
        manager_provider=manager_provider,
    )

    async def load_active() -> list[Tenant]:
        async with sessionmaker() as db_session:
            return list(await repo.list_active_tenants(db_session))

    manager = BotManager(
        factory_bot=factory_bot,
        factory_dispatcher=factory_dp,
        sessionmaker=sessionmaker,
        notifier=notifier,
        child_dispatcher_factory=child_dp_factory,
        active_tenants_loader=load_active,
    )
    manager_holder["manager"] = manager

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_stop() -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:  # pragma: no cover - Windows
            pass

    polling_task = asyncio.create_task(manager.start(), name="factory-polling")
    stop_task = asyncio.create_task(stop_event.wait(), name="stop-signal")

    logger.info("Bot factory started")
    try:
        done, _pending = await asyncio.wait(
            {polling_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        # If polling exited on its own, surface the exception (if any).
        if polling_task in done:
            polling_task.result()
    finally:
        logger.info("Shutting down...")
        await manager.shutdown()
        if not polling_task.done():
            polling_task.cancel()
            try:
                await polling_task
            except (asyncio.CancelledError, Exception):
                pass
        await engine.dispose()


def main() -> None:
    """Console-script entry point."""
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
