"""gRPC-клиенты к соседям."""

import uuid
from dataclasses import dataclass

from mirea.booking.v1 import booking_pb2, booking_pb2_grpc
from mirea.client.v1 import client_pb2, client_pb2_grpc
from mirea.common.v1 import common_pb2
from mireacrm_common import grpc_client


@dataclass(frozen=True, slots=True)
class AppointmentDetails:
    branch_id: uuid.UUID
    client_id: uuid.UUID
    employee_id: uuid.UUID
    price_kopecks: int


class Neighbours:
    """Booking отдаёт детали визита, client принимает начисление баллов."""

    def __init__(self, booking_addr: str, client_addr: str) -> None:
        self._booking_channel = grpc_client.channel(booking_addr)
        self._client_channel = grpc_client.channel(client_addr)
        self._booking = booking_pb2_grpc.BookingServiceStub(self._booking_channel)
        self._clients = client_pb2_grpc.ClientServiceStub(self._client_channel)

    async def close(self) -> None:
        await self._booking_channel.close()
        await self._client_channel.close()

    async def appointment(self, appointment_id: uuid.UUID) -> AppointmentDetails:
        request = booking_pb2.GetAppointmentRequest(appointment_id=str(appointment_id))

        async with grpc_client.call("booking", "appointment", appointment_id) as metadata:
            response = await self._booking.GetAppointment(request, metadata=metadata)

        item = response.appointment
        return AppointmentDetails(
            branch_id=uuid.UUID(item.branch_id),
            client_id=uuid.UUID(item.client_id),
            employee_id=uuid.UUID(item.employee_id),
            price_kopecks=item.price.amount_kopecks,
        )

    async def accrue_points(
        self, client_id: uuid.UUID, invoice_id: uuid.UUID, paid_kopecks: int
    ) -> int:
        request = client_pb2.AddLoyaltyPointsRequest(
            client_id=str(client_id),
            invoice_id=str(invoice_id),
            paid=common_pb2.Money(amount_kopecks=paid_kopecks, currency_code="RUB"),
        )

        async with grpc_client.call("client", "client", client_id) as metadata:
            response = await self._clients.AddLoyaltyPoints(request, metadata=metadata)

        return response.points_added
