"""Shared formatting helpers used by both factory and child handlers."""

from __future__ import annotations


def format_price(price_minor: int, currency: str) -> str:
    major = price_minor // 100
    minor = price_minor % 100
    body = f"{major}" if minor == 0 else f"{major}.{minor:02d}"
    suffix = "₽" if currency == "RUB" else currency
    return f"{body} {suffix}"
