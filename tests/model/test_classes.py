from datetime import date, datetime

import pytest

from paperoni.model.classes import DatePrecision


@pytest.mark.parametrize(
    ["date", "expected"],
    [
        (
            None,
            {
                "date": datetime(2000, 1, 1).date(),
                "date_precision": DatePrecision.unknown,
            },
        ),
        (
            "",
            {
                "date": datetime(2000, 1, 1).date(),
                "date_precision": DatePrecision.unknown,
            },
        ),
        (2023, {"date": date(2023, 1, 1), "date_precision": DatePrecision.year}),
        (23, {"date": date(2023, 1, 1), "date_precision": DatePrecision.year}),
        ("2023", {"date": date(2023, 1, 1), "date_precision": DatePrecision.year}),
        ("23", False),
        ("2023-05", {"date": date(2023, 5, 1), "date_precision": DatePrecision.month}),
        (
            "2023-05-15",
            {"date": date(2023, 5, 15), "date_precision": DatePrecision.day},
        ),
        (
            "2023-05-01",
            {"date": date(2023, 5, 1), "date_precision": DatePrecision.month},
        ),
        (
            "2023-01-01",
            {"date": date(2023, 1, 1), "date_precision": DatePrecision.year},
        ),
    ],
)
def test_assimilate_date(date, expected):
    """Test integer year input."""
    if not expected:
        with pytest.raises(AssertionError):
            DatePrecision.assimilate_date(date)
    else:
        assert DatePrecision.assimilate_date(date) == expected
