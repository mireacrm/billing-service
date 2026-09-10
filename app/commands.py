"""Входные команды предметной области."""

import uuid

from pydantic import BaseModel, Field


class InvoiceIssue(BaseModel):
    """Данные для выставления счёта.

    Событие несёт только идентификаторы, детали визита биллинг запрашивает
    у booking сам — тонкие события не приходится версионировать при каждом
    изменении карточки.
    """

    appointment_id: uuid.UUID
    branch_id: uuid.UUID
    client_id: uuid.UUID
    employee_id: uuid.UUID
    total_kopecks: int = Field(ge=0)
