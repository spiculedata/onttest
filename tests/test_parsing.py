from datetime import date

import polars as pl

from brackenfield.transform.parsing import (
    date_style,
    ex_gst,
    is_ambiguous_dmy,
    money_embedded_basis,
    normalise_vin,
    parse_date,
    parse_money,
    to_day_rate,
)


def _apply(expr: pl.Expr, values: list) -> list:
    return pl.DataFrame({"v": values}, schema={"v": pl.String}).select(expr.alias("out"))["out"].to_list()


def test_parse_date_reads_iso_and_australian_day_first_formats():
    values = ["2026-06-02", "02/04/26", "18/08/2026", "TBA", None, "31/02/26"]

    parsed = _apply(parse_date("v"), values)

    assert parsed == [date(2026, 6, 2), date(2026, 4, 2), date(2026, 8, 18), None, None, None]


def test_parse_date_does_not_read_two_digit_year_as_year_0026():
    assert _apply(parse_date("v"), ["02/04/26"]) == [date(2026, 4, 2)]


def test_date_style_and_ambiguity_flags():
    values = ["2026-06-02", "02/04/26", "18/08/26", "05/05/26"]

    assert _apply(date_style("v"), values) == ["iso", "dmy", "dmy", "dmy"]
    assert _apply(is_ambiguous_dmy("v"), values) == [None, True, False, False]


def test_parse_money_strips_currency_commas_and_unit_suffix():
    values = ["$1,710", "1450", "5435/wk", "650/day", "TBC", " $326,000 "]

    assert _apply(parse_money("v"), values) == [1710.0, 1450.0, 5435.0, 650.0, None, 326000.0]
    assert _apply(money_embedded_basis("v"), values) == [None, None, "wk", "day", None, None]


def test_normalise_vin_uppercases_and_removes_whitespace():
    values = ["lf8bah48z 2X3SJZCR", "w4ysxn2w8nymturf6 ", "", None]

    assert _apply(normalise_vin("v"), values) == ["LF8BAH48Z2X3SJZCR", "W4YSXN2W8NYMTURF6", None, None]


def test_to_day_rate_uses_five_day_week_and_22_day_month():
    frame = pl.DataFrame({"amount": [500.0, 2200.0, 100.0], "basis": ["wk", "mth", "day"]})

    out = frame.select(to_day_rate(pl.col("amount"), pl.col("basis")))["amount"].to_list()

    assert out == [100.0, 100.0, 100.0]


def test_unknown_gst_treatment_gives_no_ex_gst_rate():
    frame = pl.DataFrame({"amount": [110.0, 100.0, 100.0], "gst": ["inc", "ex", None]})

    out = frame.select(ex_gst(pl.col("amount"), pl.col("gst")).round(2))["amount"].to_list()

    assert out == [100.0, 100.0, None]
