"""Show recent reservations for a tenant."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...db import repo
from .. import keyboards, texts

router = Router(name="factory.reservations")


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
    for r in reservations:
        lines.append(
            texts.reservation_line(
                r.date_iso, r.time_iso, r.party_size, r.customer_name, r.customer_phone
            )
        )
        if r.comment:
            lines.append(f"   💬 {r.comment}")
    await call.message.answer(
        "\n".join(lines),
        reply_markup=keyboards.reservations_kb(tenant_id, reservations),
    )
    await call.answer()
