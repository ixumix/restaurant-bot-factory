"""Lightweight logging setup."""

from __future__ import annotations

import logging


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging with a sensible format."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # aiogram is chatty at DEBUG; keep it at INFO unless the user really asks for more.
    if level.upper() != "DEBUG":
        logging.getLogger("aiogram").setLevel(logging.WARNING)
