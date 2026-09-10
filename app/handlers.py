"""Обработчики доменных событий.

Разбор payload — работа транспорта: домен получает уже готовые команды.
"""

import logging
import uuid

from mirea.events.v1 import events_pb2
from mireacrm_common.lifespan import AppContext

from app import commands, domain
from app.clients import Neighbours

log = logging.getLogger(__name__)


def on_appointment_completed(context: AppContext):
    neighbours: Neighbours = context.clients

    async def handler(envelope: events_pb2.EventEnvelope) -> None:
        payload = envelope.appointment_completed
        appointment_id = uuid.UUID(payload.appointment_id)

        # Событие несёт только идентификаторы — цену спрашиваем у booking.
        details = await neighbours.appointment(appointment_id)

        async with context.session() as session:
            invoice = await domain.issue_invoice(
                session,
                uuid.UUID(envelope.event_id),
                commands.InvoiceIssue(
                    appointment_id=appointment_id,
                    branch_id=details.branch_id,
                    client_id=details.client_id,
                    employee_id=details.employee_id,
                    total_kopecks=details.price_kopecks,
                ),
                context.publisher,
            )

        if invoice is None:
            log.info("событие уже обработано, счёт не выставлен: %s", envelope.event_id)
            return

        log.info("выставлен счёт %s на %s коп.", invoice.id, invoice.total_kopecks)

    return handler
