"""Show and process recent reservations for a tenant."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...db import repo
from ...db.models import Reservation, Tenant
from .. import keyboards, texts

router = Router(name="factory.reservations")
logger = logging.getLogger(__name__)

_OWNER_ACTION_STATUSES = {"confirmed", "declined"}


def _parse_status_payload(data: str) -> tuple[int, str] | None:
    parts = data.split(":")
    if len(parts) != 3:
        return None
    _, reservation_id_raw, status = parts
    if status not in _OWNER_ACTION_STATUSES:
        return None
    try:
        reservation_id = int(reservation_id_raw)
    except ValueError:
        return None
    return reservation_id, status


def _format_reservation(reservation: Reservation) -> str:
    return texts.reservation_line(
        reservation.date_iso,
        reservation.time_iso,
        reservation.party_size,
        reservation.customer_name,
        reservation.customer_phone,
        reservation.status,
        reservation_id=reservation.id,
    )


async def _notify_customer_about_status(
    tenant: Tenant,
    reservation: Reservation,
) -> bool:
    if reservation.customer_telegram_id is None:
        return False

    bot = Bot(
        token=tenant.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await bot.send_message(
            reservation.customer_telegram_id,
            texts.customer_reservation_status_notification(
                venue_name=tenant.name,
                date_iso=reservation.date_iso,
                time_iso=reservation.time_iso,
                party_size=reservation.party_size,
                status=reservation.status,
            ),
        )
    except TelegramAPIError as exc:
        logger.warning(
            "Failed to notify customer %s about reservation %s: %s",
            reservation.customer_telegram_id,
            reservation.id,
            exc,
        )
        return False
    finally:
        await bot.session.close()
    return True


@router.callback_query(F.data.startswith("res:"))
async def show_reservations(
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
        reservations = list(
            await repo.get_recent_reservations(session, tenant_id, limit=10)
        )

    if not reservations:
        await call.message.answer(
            texts.NO_RESERVATIONS,
            reply_markup=keyboards.back_to_tenant_kb(tenant_id),
        )
        await call.answer()
        return

    lines = ["<b>Последние бронирования:</b>"]
    for reservation in reservations:
        lines.append(_format_reservation(reservation))
        if reservation.comment:
            lines.append(f"   💬 {reservation.comment}")
    await call.message.answer(
        "\n".join(lines),
        reply_markup=keyboards.reservations_kb(tenant_id, reservations),
    )
    await call.answer()


@router.callback_query(F.data.startswith("resstatus:"))
async def update_reservation_status(
    call: CallbackQuery,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    if call.data is None or call.from_user is None:
        return
    parsed = _parse_status_payload(call.data)
    if parsed is None:
        await call.answer("Bad payload")
        return
    reservation_id, status = parsed

    async with sessionmaker() as session:
        reservation = await repo.get_reservation(session, reservation_id)
        if reservation is None:
            await call.answer(texts.RESERVATION_NOT_FOUND)
            return
        tenant = await repo.get_tenant(session, reservation.tenant_id)
        if tenant is None or tenant.owner_id != call.from_user.id:
            await call.answer("Не найдено")
            return
        if reservation.status != "new":
            await call.answer(texts.RESERVATION_ALREADY_PROCESSED)
            return
        updated = await repo.update_reservation_status(session, reservation_id, status)
        if updated is None:
            await call.answer(texts.RESERVATION_NOT_FOUND)
            return

    customer_notified = await _notify_customer_about_status(tenant, updated)

    await call.answer(texts.RESERVATION_STATUS_UPDATED)
    if call.message is not None:
        await call.message.answer(
            texts.reservation_status_owner_line(
                tenant.name,
                updated.date_iso,
                updated.time_iso,
                updated.status,
                customer_notified=customer_notified,
            ),
            reply_markup=keyboards.reservation_actions_kb(updated),
        )
