"""Polars expressions for the messy field types in the register.

Each parser returns null when it cannot read a value; it never guesses. The
checks compare raw vs parsed columns to report anything that came out null.
"""

from __future__ import annotations

import polars as pl

from brackenfield.config import GST_RATE, WORKING_DAYS_PER_MONTH, WORKING_DAYS_PER_WEEK

ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"
DMY_LONG = r"^\d{1,2}/\d{1,2}/\d{4}$"
DMY_SHORT = r"^\d{1,2}/\d{1,2}/\d{2}$"

# "$1,710", "1450", "5435/wk", "650/day", "1200 / week", "TBC". The unit after "/" is
# resolved through the MDM rate_basis domain, so "/wk", "/week" and "pw" all mean the same.
MONEY = r"^\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:(?:/|per)\s*([a-z][a-z .]*))?$"

DAYS_PER_BASIS = {"day": 1, "wk": WORKING_DAYS_PER_WEEK, "mth": WORKING_DAYS_PER_MONTH}

VIN_PATTERN = r"^[A-HJ-NPR-Z0-9]{17}$"  # 17 chars, no I, O or Q
REGO_PATTERN = r"^[A-Z]{2}\d{3}[A-Z]$"


def clean_text(column: str) -> pl.Expr:
    """Trim, collapse internal whitespace, and turn empty strings into null."""
    text = pl.col(column).str.strip_chars().str.replace_all(r"\s+", " ")
    return pl.when(text == "").then(None).otherwise(text)


def parse_date(column: str) -> pl.Expr:
    """ISO dates and Australian day-first dates (dd/mm/yy and dd/mm/yyyy).

    Each format is gated by a regex, because strptime alone reads "02/04/26"
    as the year 0026 under %Y.
    """
    text = pl.col(column).str.strip_chars()
    return (
        pl.when(text.str.contains(ISO_DATE))
        .then(text.str.strptime(pl.Date, "%Y-%m-%d", strict=False))
        .when(text.str.contains(DMY_LONG))
        .then(text.str.strptime(pl.Date, "%d/%m/%Y", strict=False))
        .when(text.str.contains(DMY_SHORT))
        .then(text.str.strptime(pl.Date, "%d/%m/%y", strict=False))
        .otherwise(None)
    )


def date_style(column: str) -> pl.Expr:
    """How the date was written: "iso", "dmy" or null when not a date."""
    text = pl.col(column).str.strip_chars()
    return (
        pl.when(text.str.contains(ISO_DATE))
        .then(pl.lit("iso"))
        .when(text.str.contains(DMY_LONG) | text.str.contains(DMY_SHORT))
        .then(pl.lit("dmy"))
        .otherwise(None)
    )


def is_ambiguous_dmy(column: str) -> pl.Expr:
    """True for d/m dates where both parts are <= 12, so m/d would also be valid."""
    parts = pl.col(column).str.strip_chars().str.extract_groups(r"^(\d{1,2})/(\d{1,2})/\d{2,4}$")
    first = parts.struct.field("1").cast(pl.Int32, strict=False)
    second = parts.struct.field("2").cast(pl.Int32, strict=False)
    return (first <= 12) & (second <= 12) & (first != second)


def parse_money(column: str) -> pl.Expr:
    text = pl.col(column).str.strip_chars().str.to_lowercase()
    return text.str.extract(MONEY, 1).str.replace_all(",", "").cast(pl.Float64, strict=False)


def money_embedded_basis(column: str) -> pl.Expr:
    """The "/wk" in "5435/wk", if the rate text carries its own basis."""
    return pl.col(column).str.strip_chars().str.to_lowercase().str.extract(MONEY, 2)


def parse_int(column: str) -> pl.Expr:
    return pl.col(column).str.strip_chars().cast(pl.Float64, strict=False).cast(pl.Int32, strict=False)


def normalise_vin(column: str) -> pl.Expr:
    """Upper-case and strip all whitespace; "w4ys...rf6 " and "LF8BAH48Z 2X3..." happen."""
    vin = pl.col(column).str.to_uppercase().str.replace_all(r"\s+", "")
    return pl.when(vin == "").then(None).otherwise(vin)


def normalise_rego(column: str) -> pl.Expr:
    rego = pl.col(column).str.to_uppercase().str.replace_all(r"\s+", "")
    return pl.when(rego == "").then(None).otherwise(rego)


def ex_gst(amount: pl.Expr, treatment: pl.Expr) -> pl.Expr:
    """Unknown treatment gives null, so a rate is never silently 10% out."""
    return pl.when(treatment == "inc").then(amount / (1 + GST_RATE)).when(treatment == "ex").then(amount).otherwise(None)


def to_day_rate(amount: pl.Expr, basis: pl.Expr) -> pl.Expr:
    days = basis.replace_strict(DAYS_PER_BASIS, default=None, return_dtype=pl.Float64)
    return amount / days
