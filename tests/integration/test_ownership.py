"""Комиссия видна только своя: проверка на границе HTTP, база настоящая."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from mireacrm_common import identity

from app import commands, domain

DAY = datetime(2026, 9, 10, tzinfo=UTC)
SUBJECT = "8f1c0e4e-0000-4000-8000-000000000001"
OWN = uuid.uuid4()
OTHER = uuid.uuid4()
WINDOW = {"from": DAY.isoformat(), "to": (DAY + timedelta(days=1)).isoformat()}


def headers(role: str, employee_id: uuid.UUID | str = "") -> dict[str, str]:
    return {
        identity.HEADER_SUBJECT: SUBJECT,
        identity.HEADER_ROLES: role,
        identity.HEADER_EMPLOYEE: str(employee_id),
    }


@pytest.fixture
async def invoices(session, publisher) -> None:
    for employee in (OWN, OTHER):
        await domain.issue_invoice(
            session,
            uuid.uuid4(),
            commands.InvoiceIssue(
                appointment_id=uuid.uuid4(),
                branch_id=uuid.uuid4(),
                client_id=uuid.uuid4(),
                employee_id=employee,
                total_kopecks=520000,
            ),
            publisher,
        )


class TestCommission:
    async def test_specialist_sees_own(self, api, invoices) -> None:
        response = await api.get(
            f"/employees/{OWN}/commission", params=WINDOW, headers=headers("specialist", OWN)
        )
        assert response.status_code == 200
        assert response.json()["employee_id"] == str(OWN)

    async def test_specialist_denied_foreign(self, api, invoices) -> None:
        """Чужой заработок — не то, что специалисту положено видеть."""
        response = await api.get(
            f"/employees/{OTHER}/commission", params=WINDOW, headers=headers("specialist", OWN)
        )
        assert response.status_code == 403

    @pytest.mark.parametrize("role", ["admin", "manager"])
    async def test_privileged_sees_any(self, api, invoices, role) -> None:
        response = await api.get(
            f"/employees/{OTHER}/commission", params=WINDOW, headers=headers(role)
        )
        assert response.status_code == 200

    async def test_account_without_employee_denied(self, api, invoices) -> None:
        response = await api.get(
            f"/employees/{OTHER}/commission", params=WINDOW, headers=headers("specialist")
        )
        assert response.status_code == 403

    async def test_branch_invoices_untouched_by_the_check(self, api, invoices) -> None:
        """Счета филиала специалисту недоступны по роли — проверять владение нечем."""
        response = await api.get(f"/branches/{uuid.uuid4()}/invoices", headers=headers("manager"))
        assert response.status_code == 200
