from datetime import datetime

import pytest

from paperoni.model import BaseWithQuality, DatePrecision


def test_date_precision_format():
    d = datetime.fromisoformat("2006-03-19 00:00")
    assert DatePrecision.format(d, DatePrecision.day) == "2006-03-19"
    assert DatePrecision.format(d, DatePrecision.month) == "2006-03"
    assert DatePrecision.format(d, DatePrecision.year) == "2006"
    assert DatePrecision.format(d, DatePrecision.unknown) == "2006"
    with pytest.raises(ValueError):
        DatePrecision.format(d, 4)


def test_date_precision_format_timestamp():
    d = 1234567890
    assert DatePrecision.format(d, DatePrecision.day) == "2009-02-13"


def test_date_precision_format_timestamp_float():
    d = 1234567890.3
    assert DatePrecision.format(d, DatePrecision.day) == "2009-02-13"


def test_date_precision_assimilate_date():
    d = 1987
    assert DatePrecision.assimilate_date(d) == {
        "date": "1987-01-01 00:00",
        "date_precision": DatePrecision.year,
    }

    d = "2006-03-19"
    assert DatePrecision.assimilate_date(d) == {
        "date": "2006-03-19 00:00",
        "date_precision": DatePrecision.day,
    }

    d = "2006-03-19 10:10"
    assert DatePrecision.assimilate_date(d) == {
        "date": "2006-03-19 00:00",
        "date_precision": DatePrecision.day,
    }

    d = "2006-01-01"
    assert DatePrecision.assimilate_date(d) == {
        "date": "2006-01-01 00:00",
        "date_precision": DatePrecision.year,
    }

    d = "2006-07-01"
    assert DatePrecision.assimilate_date(d) == {
        "date": "2006-07-01 00:00",
        "date_precision": DatePrecision.day,
    }

    d = None
    assert DatePrecision.assimilate_date(d) == {
        "date": "2000-01-01 00:00",
        "date_precision": DatePrecision.unknown,
    }

    with pytest.raises(AssertionError):
        d = "whatever"
        assert not DatePrecision.assimilate_date(d)


def test_quality_calculation():
    X = BaseWithQuality

    x = X(quality=4)
    assert x.quality_int() == 4

    x1 = X(quality=(1.0, 0.0, 0.0))
    x2 = X(quality=(1.0, 0.0))
    x3 = X(quality=(1.0,))
    assert (
        x1.quality_int()
        == x2.quality_int()
        == x3.quality_int()
        == 0xFF_00_00_00
    )

    x = X(quality=(0.5, 1.0, 0.25, 0.125))
    assert x.quality_int() == 0x7F_FF_3F_1F
