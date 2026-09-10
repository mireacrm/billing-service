"""Бизнес-операции. Используются и REST-слоем, и обработчиком событий."""

import uuid
from datetime import UTC, datetime

from mirea.common.v1 import common_pb2
from mirea.events.v1 import events_pb2
from mireacrm_common.errors import ConflictError, NotFoundError
from mireacrm_common.events import EventPublisher
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import commands, models

# Доля специалиста от оплаченного счёта.
COMMISSION_RATE = 0.4


def commission_for(total_kopecks: int) -> int:
    return int(total_kopecks * COMMISSION_RATE)


async def mark_processed(
    session: AsyncSession, event_id: uuid.UUID, routing_key: str
) -> bool:
    """Возвращает False, если событие уже обрабатывалось.

    Коммита здесь нет намеренно: отметка должна попасть в ту же транзакцию,
    что и эффект, иначе упавшая обработка оставит событие помеченным.
    """
    statement = (
        insert(models.ProcessedEvent)
        .values(event_id=event_id, routing_key=routing_key)
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(models.ProcessedEvent.event_id)
    )
    return await session.scalar(statement) is not None


async def issue_invoice(
    session: AsyncSession,
    event_id: uuid.UUID,
    data: commands.InvoiceIssue,
    publisher: EventPublisher,
) -> models.Invoice | None:
    """Выставляет счёт по завершённой записи. None — событие уже обработано."""
    if not await mark_processed(session, event_id, "appointment.completed"):
        return None

    invoice = models.Invoice(
        appointment_id=data.appointment_id,
        branch_id=data.branch_id,
        client_id=data.client_id,
        employee_id=data.employee_id,
        total_kopecks=data.total_kopecks,
        commission_kopecks=commission_for(data.total_kopecks),
    )
    session.add(invoice)
    await session.commit()
    await session.refresh(invoice)

    await publisher.publish(
        "invoice.issued",
        invoice_issued=events_pb2.InvoiceIssued(
            invoice_id=str(invoice.id),
            appointment_id=str(invoice.appointment_id),
            branch_id=str(invoice.branch_id),
            client_id=str(invoice.client_id),
            total=_money(invoice.total_kopecks),
        ),
    )
    return invoice


async def get_invoice(session: AsyncSession, invoice_id: uuid.UUID) -> models.Invoice:
    invoice = await session.get(models.Invoice, invoice_id)
    if invoice is None:
        raise NotFoundError("invoice", invoice_id)
    return invoice


async def pay_invoice(session: AsyncSession, invoice_id: uuid.UUID) -> models.Invoice:
    """Отмечает счёт оплаченным. Повторная оплата — конфликт, а не успех.

    Смена статуса выполняется одним условным UPDATE: прочитать, проверить и
    записать по отдельности означало бы, что два одновременных запроса на
    оплату оба увидят `issued` и оба её проведут. Условие в WHERE решает это
    в базе, как и захват слота в booking, и не держит блокировку на время
    начисления баллов, которое идёт следом по gRPC.
    """
    statement = (
        update(models.Invoice)
        .where(
            models.Invoice.id == invoice_id,
            models.Invoice.status == models.InvoiceStatus.ISSUED,
        )
        .values(status=models.InvoiceStatus.PAID, paid_at=datetime.now(UTC))
        .returning(models.Invoice)
        # populate_existing обязателен: счёт уже может лежать в identity map
        # сессии со старым статусом, и без этого вернётся он, а не строка,
        # которую база отдала из RETURNING.
        .execution_options(synchronize_session=False, populate_existing=True)
    )
    invoice = await session.scalar(statement)
    if invoice is None:
        # Ноль строк — либо счёта нет вовсе, либо он уже не `issued`.
        # Разделить эти случаи можно только отдельным чтением; менять оно
        # ничего не меняет, поэтому идёт в той же транзакции.
        existing = await get_invoice(session, invoice_id)
        raise ConflictError(
            f"счёт в статусе {existing.status.value!r}, "
            f"оплатить можно только {models.InvoiceStatus.ISSUED.value!r}"
        )

    await session.commit()
    return invoice


async def announce_paid(invoice: models.Invoice, publisher: EventPublisher) -> None:
    await publisher.publish(
        "invoice.paid",
        invoice_paid=events_pb2.InvoicePaid(
            invoice_id=str(invoice.id),
            branch_id=str(invoice.branch_id),
            client_id=str(invoice.client_id),
            employee_id=str(invoice.employee_id),
            total=_money(invoice.total_kopecks),
            employee_commission=_money(invoice.commission_kopecks),
        ),
    )


async def list_branch_invoices(
    session: AsyncSession,
    branch_id: uuid.UUID,
    status: models.InvoiceStatus | None = None,
    limit: int = 50,
) -> list[models.Invoice]:
    query = select(models.Invoice).where(models.Invoice.branch_id == branch_id)
    if status is not None:
        query = query.where(models.Invoice.status == status)

    result = await session.scalars(query.order_by(models.Invoice.created_at.desc()).limit(limit))
    return list(result)


async def employee_commission(
    session: AsyncSession, employee_id: uuid.UUID, since: datetime, until: datetime
) -> tuple[int, int]:
    """Комиссия специалиста за период: сумма и количество оплаченных счетов.

    Считается только по оплаченным: выставленный, но не оплаченный счёт
    комиссию не порождает.
    """
    query = select(
        func.coalesce(func.sum(models.Invoice.commission_kopecks), 0), func.count()
    ).where(
        models.Invoice.employee_id == employee_id,
        models.Invoice.status == models.InvoiceStatus.PAID,
        models.Invoice.paid_at >= since,
        models.Invoice.paid_at < until,
    )

    total, count = (await session.execute(query)).one()
    return int(total), int(count)


def _money(kopecks: int) -> common_pb2.Money:
    return common_pb2.Money(amount_kopecks=kopecks, currency_code="RUB")
