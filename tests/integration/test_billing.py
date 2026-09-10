"""Домен против настоящего Postgres."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from mireacrm_common.errors import ConflictError, NotFoundError

from app import commands, domain, models

BRANCH = uuid.uuid4()
EMPLOYEE = uuid.uuid4()


def issue_data(total: int = 520000, **kwargs) -> commands.InvoiceIssue:
    payload = {
        "appointment_id": uuid.uuid4(),
        "branch_id": BRANCH,
        "client_id": uuid.uuid4(),
        "employee_id": EMPLOYEE,
        "total_kopecks": total,
    }
    payload.update(kwargs)
    return commands.InvoiceIssue(**payload)


class TestIssue:
    async def test_invoice_created_with_commission(self, session, publisher):
        invoice = await domain.issue_invoice(session, uuid.uuid4(), issue_data(), publisher)

        assert invoice is not None
        assert invoice.total_kopecks == 520000
        assert invoice.commission_kopecks == 208000
        assert invoice.status is models.InvoiceStatus.ISSUED
        assert publisher.routing_keys() == ["invoice.issued"]

    async def test_duplicate_event_ignored(self, session, publisher):
        """Повторная доставка не должна выставить второй счёт."""
        event_id = uuid.uuid4()
        data = issue_data()

        first = await domain.issue_invoice(session, event_id, data, publisher)
        second = await domain.issue_invoice(session, event_id, data, publisher)

        assert first is not None
        assert second is None
        assert publisher.routing_keys() == ["invoice.issued"]

    async def test_processed_mark_shares_transaction(self, session, publisher):
        """Отметка и счёт живут в одной транзакции: откат снимает обе."""
        event_id = uuid.uuid4()

        assert await domain.mark_processed(session, event_id, "appointment.completed")
        await session.rollback()

        # После отката событие снова считается необработанным.
        assert await domain.mark_processed(session, event_id, "appointment.completed")


class TestPayment:
    async def test_paid_and_announced(self, session, publisher):
        invoice = await domain.issue_invoice(session, uuid.uuid4(), issue_data(), publisher)

        paid = await domain.pay_invoice(session, invoice.id)
        await domain.announce_paid(paid, publisher)

        assert paid.status is models.InvoiceStatus.PAID
        assert paid.paid_at is not None
        assert publisher.routing_keys() == ["invoice.issued", "invoice.paid"]

    async def test_double_payment_rejected(self, session, publisher):
        invoice = await domain.issue_invoice(session, uuid.uuid4(), issue_data(), publisher)
        await domain.pay_invoice(session, invoice.id)

        with pytest.raises(ConflictError):
            await domain.pay_invoice(session, invoice.id)

    async def test_concurrent_payment_pays_once(self, context, session, publisher):
        """Две одновременные оплаты одного счёта: пройти должна ровно одна.

        Проверка «прочитать, сравнить, записать» здесь не годится — оба
        запроса увидели бы `issued`. Решает условие в WHERE, как и захват
        слота в booking.
        """
        invoice = await domain.issue_invoice(session, uuid.uuid4(), issue_data(), publisher)

        async def pay():
            async with context.session() as db:
                return await domain.pay_invoice(db, invoice.id)

        results = await asyncio.gather(pay(), pay(), return_exceptions=True)

        paid = [item for item in results if isinstance(item, models.Invoice)]
        conflicts = [item for item in results if isinstance(item, ConflictError)]
        assert len(paid) == 1, results
        assert len(conflicts) == 1, results

    async def test_unknown_invoice(self, session, publisher):
        with pytest.raises(NotFoundError):
            await domain.pay_invoice(session, uuid.uuid4())


class TestReports:
    async def test_branch_invoices_filtered_by_status(self, session, publisher):
        first = await domain.issue_invoice(session, uuid.uuid4(), issue_data(), publisher)
        await domain.issue_invoice(session, uuid.uuid4(), issue_data(), publisher)
        await domain.pay_invoice(session, first.id)

        paid = await domain.list_branch_invoices(session, BRANCH, models.InvoiceStatus.PAID)
        issued = await domain.list_branch_invoices(session, BRANCH, models.InvoiceStatus.ISSUED)

        assert [i.id for i in paid] == [first.id]
        assert len(issued) == 1

    async def test_commission_counts_only_paid(self, session, publisher):
        paid = await domain.issue_invoice(session, uuid.uuid4(), issue_data(), publisher)
        await domain.issue_invoice(session, uuid.uuid4(), issue_data(), publisher)
        await domain.pay_invoice(session, paid.id)

        now = datetime.now(UTC)
        total, count = await domain.employee_commission(
            session, EMPLOYEE, now - timedelta(hours=1), now + timedelta(hours=1)
        )

        assert count == 1
        assert total == 208000

    async def test_commission_respects_period(self, session, publisher):
        invoice = await domain.issue_invoice(session, uuid.uuid4(), issue_data(), publisher)
        await domain.pay_invoice(session, invoice.id)

        past = datetime.now(UTC) - timedelta(days=30)
        total, count = await domain.employee_commission(
            session, EMPLOYEE, past, past + timedelta(days=1)
        )

        assert (total, count) == (0, 0)
