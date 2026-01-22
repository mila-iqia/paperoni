from datetime import date

import pytest
from serieux import serialize

from paperoni.model.classes import DatePrecision, Institution
from paperoni.refinement.formats import extract_date, institution_from_ror

rors = {
    "mila": "05c22rx21",
    "udem": "0161xgx34",
    "mcgill": "01pxwe438",
}


@pytest.mark.parametrize("name,ror_id", rors.items())
async def test_ror(name, ror_id, data_regression):
    inst = await institution_from_ror(ror_id)
    data = serialize(Institution, inst)
    data_regression.check(data)


def test_extract_date_integer_input_year():
    """Test that integer year inputs work correctly."""
    result = extract_date(2020)
    assert result["date"] == date(2020, 1, 1)
    assert result["date_precision"] == DatePrecision.year


@pytest.mark.parametrize(
    ["month", "abbreviation", "number"],
    [
        ("January", "Jan", 1),
        ("February", "Feb", 2),
        ("March", "Mar", 3),
        ("April", "Apr", 4),
        ("May", "May", 5),
        ("June", "Jun", 6),
        ("July", "Jul", 7),
        ("August", "Aug", 8),
        ("September", "Sep", 9),
        ("October", "Oct", 10),
        ("November", "Nov", 11),
        ("December", "Dec", 12),
    ],
)
def test_extract_date_abbreviated_months(month, abbreviation, number):
    result = extract_date(f"{month} 2020")
    abbr_result = extract_date(f"{abbreviation} 2020")
    assert result == abbr_result

    if month != abbreviation:
        abbr_result = extract_date(f"{abbreviation}. 2020")
        assert result == abbr_result

    assert result["date"] == date(2020, number, 1)
    assert result["date_precision"] == DatePrecision.month


@pytest.mark.parametrize(
    ["input_str", "expected_date", "expected_precision"],
    [
        ("Jan 3 - Jan 7 2020", date(2020, 1, 3), DatePrecision.day),
        ("Jan 3 - 7 2020", date(2020, 1, 3), DatePrecision.day),
        ("Jan 3 2020", date(2020, 1, 3), DatePrecision.day),
        ("3 - 7 Jan 2020", date(2020, 1, 3), DatePrecision.day),
        ("3 Jan 2020", date(2020, 1, 3), DatePrecision.day),
        ("Jan 2020", date(2020, 1, 1), DatePrecision.month),
        ("2020 Jan 3", date(2020, 1, 3), DatePrecision.day),
        ("2020 Jan", date(2020, 1, 1), DatePrecision.month),
        ("2020", date(2020, 1, 1), DatePrecision.year),
    ],
)
def test_extract_date_full_month_day_year_format(
    input_str, expected_date, expected_precision
):
    """Test formats like 'Jan 3 2020' and 'January 15, 2021'."""
    result = extract_date(input_str)
    assert result["date"] == expected_date
    assert result["date_precision"] == expected_precision


@pytest.mark.parametrize(
    "invalid_input",
    [
        None,
        "",
        "random text",
        [],
        {},
        12.5,
    ],
)
def test_extract_date_invalid_inputs(invalid_input):
    """Test that invalid inputs return None."""
    result = extract_date(invalid_input)
    assert result is None
