"""Расчёт комиссии специалиста."""

import pytest

from app.domain import commission_for


@pytest.mark.parametrize(
    ("total_kopecks", "expected"),
    [
        (0, 0),
        (520000, 208000),      # 5200 руб → 2080 руб (40%)
        (100000, 40000),       # 1000 руб → 400 руб
        (1, 0),                # округление вниз, копейки не делятся
        (7, 2),                # 2.8 → 2
    ],
)
def test_commission(total_kopecks: int, expected: int):
    assert commission_for(total_kopecks) == expected


def test_commission_never_exceeds_total():
    for total in (0, 1, 999, 520000, 10**9):
        assert 0 <= commission_for(total) <= total
