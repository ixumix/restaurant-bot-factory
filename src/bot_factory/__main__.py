"""Entry point: wire everything together and run forever."""

from __future__ import annotations

import asyncio
import logging
import signal

from .child.handlers import make_child_dispatcher_factory
from .claude import ClaudeClient
from .config import load_settings
from .db import repo
from .db.models import Tenant
from .db.session import init_db, make_engine_and_sessionmaker
from .devin_chat import DevinChatClient
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
    telegram_proxy_url = settings.telegram_proxy_url_value

    factory_bot = make_factory_bot(settings.factory_bot_token, telegram_proxy_url)
    notifier = Notifier(factory_bot)

    backend = settings.resolved_support_backend
    claude_client: ClaudeClient | None = None
    devin_client: DevinChatClient | None = None

    if backend == "claude":
        claude_keys = settings.claude_api_key_list
        claude_client = ClaudeClient(
            api_keys=claude_keys,
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            base_url=settings.claude_base_url,
            anthropic_version=settings.claude_anthropic_version,
            timeout_seconds=settings.claude_timeout_seconds,
        )
        logger.info(
            "Support chat backend=claude with %d API key(s), model=%s",
            len(claude_keys),
            settings.claude_model,
        )
    elif backend == "devin":
        devin_keys = settings.devin_api_key_list
        devin_client = DevinChatClient(
            api_keys=devin_keys,
            base_url=settings.devin_base_url,
            poll_interval_seconds=settings.devin_poll_interval_seconds,
            response_timeout_seconds=settings.devin_response_timeout_seconds,
            max_acu_limit=settings.devin_max_acu_limit_value,
        )
        logger.info(
            "Support chat backend=devin with %d API key(s), base_url=%s",
            len(devin_keys),
            settings.devin_base_url,
        )
    else:
        logger.info(
            "Support chat disabled (no CLAUDE_API_KEYS or DEVIN_API_KEYS set)"
        )

    child_dp_factory = make_child_dispatcher_factory(
        sessionmaker=sessionmaker,
        notifier=notifier,
        claude_client=claude_client,
        claude_history_limit=settings.claude_history_limit,
        claude_system_prompt_override=settings.claude_system_prompt_value,
        devin_client=devin_client,
    )

    manager_holder: dict[str, BotManager] = {}

    def manager_provider() -> BotManager:
        return manager_holder["manager"]

    factory_dp = make_factory_dispatcher(
        sessionmaker=sessionmaker,
        allowed_owner_ids=settings.allowed_owner_id_set,
        manager_provider=manager_provider,
        telegram_proxy_url=telegram_proxy_url,
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
        telegram_proxy_url=telegram_proxy_url,
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
        if claude_client is not None:
            await claude_client.aclose()
        if devin_client is not None:
            await devin_client.aclose()
        await engine.dispose()


def main() -> None:
    """Console-script entry point."""
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
