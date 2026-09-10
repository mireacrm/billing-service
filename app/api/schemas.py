"""Представления домена в HTTP-ответах."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import InvoiceStatus


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    appointment_id: uuid.UUID
    branch_id: uuid.UUID
    client_id: uuid.UUID
    employee_id: uuid.UUID
    total_kopecks: int
    commission_kopecks: int
    status: InvoiceStatus
    created_at: datetime
    paid_at: datetime | None


class CommissionOut(BaseModel):
    employee_id: uuid.UUID
    since: datetime
    until: datetime
    invoices: int
    commission_kopecks: int
