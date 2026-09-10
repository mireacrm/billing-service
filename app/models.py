import enum
import uuid
from datetime import datetime
from typing import Annotated

from sqlalchemy import BigInteger, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


UuidPk = Annotated[
    uuid.UUID, mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
]
CreatedAt = Annotated[
    datetime, mapped_column(DateTime(timezone=True), server_default=func.now())
]


class InvoiceStatus(enum.StrEnum):
    ISSUED = "issued"
    PAID = "paid"
    CANCELLED = "cancelled"


class Invoice(Base):
    """Счёт за завершённую запись.

    appointment_id уникален: одна запись — один счёт, сколько бы раз событие
    ни доставили.
    """

    __tablename__ = "invoices"

    id: Mapped[UuidPk]
    appointment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    total_kopecks: Mapped[int] = mapped_column(BigInteger)
    commission_kopecks: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status"), default=InvoiceStatus.ISSUED
    )
    created_at: Mapped[CreatedAt]
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProcessedEvent(Base):
    """Inbox: RabbitMQ доставляет at-least-once.

    Отметка пишется той же транзакцией, что и эффект — иначе упавшая обработка
    оставит событие помеченным, и повторная доставка молча пропустит его.
    """

    __tablename__ = "processed_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    routing_key: Mapped[str] = mapped_column(String(64))
    processed_at: Mapped[CreatedAt]
