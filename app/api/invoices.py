import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from mireacrm_common.deps import get_context, get_publisher, get_session
from mireacrm_common.events import EventPublisher
from mireacrm_common.lifespan import AppContext
from sqlalchemy.ext.asyncio import AsyncSession

from app import domain
from app.api import schemas
from app.infra import access
from app.models import InvoiceStatus

router = APIRouter(tags=["billing"])


@router.get("/invoices/{invoice_id}", response_model=schemas.InvoiceOut)
async def get_invoice(invoice_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    return await domain.get_invoice(session, invoice_id)


@router.post("/invoices/{invoice_id}/pay", response_model=schemas.InvoiceOut)
async def pay_invoice(
    invoice_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    publisher: EventPublisher = Depends(get_publisher),
    context: AppContext = Depends(get_context),
):
    """Отмечает оплату, начисляет клиенту баллы и публикует invoice.paid."""
    invoice = await domain.pay_invoice(session, invoice_id)

    await context.clients.accrue_points(
        invoice.client_id, invoice.id, invoice.total_kopecks
    )
    await domain.announce_paid(invoice, publisher)
    return invoice


@router.get("/branches/{branch_id}/invoices", response_model=list[schemas.InvoiceOut])
async def list_branch_invoices(
    branch_id: uuid.UUID,
    status: InvoiceStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    return await domain.list_branch_invoices(session, branch_id, status, limit)


@router.get("/employees/{employee_id}/commission", response_model=schemas.CommissionOut)
async def get_commission(
    employee_id: uuid.UUID,
    since: datetime = Query(alias="from"),
    until: datetime = Query(alias="to"),
    session: AsyncSession = Depends(get_session),
):
    access.ensure_owner(employee_id, "комиссия сотрудника")
    total, count = await domain.employee_commission(session, employee_id, since, until)
    return schemas.CommissionOut(
        employee_id=employee_id,
        since=since,
        until=until,
        invoices=count,
        commission_kopecks=total,
    )
