"""Hires: one row per line on "Hires 25-26", cancelled and duplicate lines included.

Rules from READ ME applied here:
  - Rates are per day unless Basis says wk or mth (week = 5 days, month = 22).
  - GST column decides inc/ex; when blank, BE is inc GST and NH is ex GST.
  - Struck-through lines were cancelled before they started.
  - Off-hire blank, "ongoing" or "TBA" means still on hire; Start "TBA" means not started.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from brackenfield import mdm, vocab
from brackenfield.transform.parsing import (
    clean_text,
    date_style,
    ex_gst,
    is_ambiguous_dmy,
    money_embedded_basis,
    parse_date,
    parse_money,
    to_day_rate,
)

OPEN_MARKERS = ("ongoing", "tba")
NOT_STARTED_MARKERS = ("tba",)
DEFAULT_GST_BY_BUSINESS = {"BE": "inc", "NH": "ex"}
# Every cell on the line, as written. A line equal to an earlier one on all of these is a duplicate.
DUPLICATE_COLUMNS = (
    "hire_no", "supplier_raw", "category_raw", "project_raw", "business_code_raw", "start_raw",
    "off_hire_raw", "rate_raw", "basis_raw", "gst_raw", "notes",
)


def _resolve_project(projects: pl.DataFrame) -> pl.Expr:
    """Project cell -> project code. Accepts "P-2055", "2055" or the project name."""
    by_name = {name.lower(): code for code, name in projects.select("project_code", "name").iter_rows()}
    codes = projects["project_code"].to_list()
    text = clean_text("project_raw")
    as_code = text.str.to_uppercase().str.replace(r"^(?:P-?)?(\d{4})$", "P-$1")
    return (
        pl.when(as_code.is_in(codes))
        .then(as_code)
        .otherwise(text.str.to_lowercase().replace_strict(by_name, default=None, return_dtype=pl.String))
    )


def _project_match(projects: pl.DataFrame) -> pl.Expr:
    codes = projects["project_code"].to_list()
    text = clean_text("project_raw").str.to_uppercase()
    return (
        pl.when(text.is_in(codes)).then(pl.lit("code"))
        .when(text.str.contains(r"^\d{4}$")).then(pl.lit("bare_number"))
        .when(pl.col("project_code").is_not_null()).then(pl.lit("name"))
        .otherwise(None)
    )


def _status(as_of: date) -> pl.Expr:
    return (
        pl.when(pl.col("is_cancelled")).then(pl.lit("cancelled"))
        .when(pl.col("start_marker") == "tba").then(pl.lit("not_started"))
        .when(pl.col("start_date") > as_of).then(pl.lit("not_started"))
        .when(pl.col("off_hire_date") <= as_of).then(pl.lit("off_hired"))
        .when(pl.col("start_date").is_not_null()).then(pl.lit("on_hire"))
        .otherwise(None)
    )


def build_hires(hire_rows: pl.DataFrame, projects: pl.DataFrame, as_of: date) -> pl.DataFrame:
    raw = hire_rows.rename(
        {
            "supplier": "supplier_raw",
            "category": "category_raw",
            "project": "project_raw",
            "business_code": "business_code_raw",
            "start": "start_raw",
            "off_hire": "off_hire_raw",
            "rate": "rate_raw",
            "basis": "basis_raw",
            "gst": "gst_raw",
        }
    )
    marker = lambda col: clean_text(col).str.to_lowercase()  # noqa: E731 - tiny local helper
    hires = (
        raw.with_columns(
            clean_text("hire_no").str.to_uppercase().alias("hire_no"),
            mdm.resolve_expr("supplier_raw", "supplier").alias("supplier_name"),
            mdm.resolve_expr("supplier_raw", "supplier", "basis").alias("supplier_basis"),
            mdm.resolve_expr("category_raw", "category").alias("category"),
            mdm.resolve_expr("category_raw", "category", "basis").alias("category_basis"),
            mdm.resolve_expr("business_code_raw", "business").alias("business_code"),
            parse_date("start_raw").alias("start_date"),
            date_style("start_raw").alias("start_style"),
            is_ambiguous_dmy("start_raw").fill_null(False).alias("start_ambiguous"),
            pl.when(marker("start_raw").is_in(NOT_STARTED_MARKERS)).then(marker("start_raw")).alias("start_marker"),
            parse_date("off_hire_raw").alias("off_hire_date"),
            date_style("off_hire_raw").alias("off_hire_style"),
            is_ambiguous_dmy("off_hire_raw").fill_null(False).alias("off_hire_ambiguous"),
            pl.when(pl.col("off_hire_raw").is_null()).then(pl.lit("blank"))
            .when(marker("off_hire_raw").is_in(OPEN_MARKERS)).then(marker("off_hire_raw"))
            .alias("off_hire_marker"),
            parse_money("rate_raw").alias("rate_amount"),
            money_embedded_basis("rate_raw").alias("rate_text_basis_raw"),
            mdm.resolve_expr("basis_raw", "rate_basis").alias("rate_basis"),
            mdm.resolve_expr("gst_raw", "gst").alias("gst_column"),
            clean_text("gst_raw").alias("gst_written"),
            (pl.col("strike") == "all").alias("is_cancelled"),
            clean_text("notes").alias("notes"),
        )
        .with_columns(
            _resolve_project(projects).alias("project_code"),
            pl.col("supplier_name").map_elements(vocab.org_id_for_supplier, return_dtype=pl.String).alias("supplier_org_id"),
            pl.col("business_code").str.to_lowercase().map_elements(lambda c: f"org_{c}", return_dtype=pl.String).alias("business_org_id"),
            pl.coalesce(
                pl.when(pl.col("gst_column").is_in(["inc", "ex"])).then(pl.col("gst_column")),
                pl.when(pl.col("gst_written").is_null()).then(
                    pl.col("business_code").replace_strict(DEFAULT_GST_BY_BUSINESS, default=None)
                ),
            ).alias("gst_treatment"),
            pl.when(pl.col("gst_column").is_in(["inc", "ex"])).then(pl.lit("gst_column"))
            .when(pl.col("gst_written").is_null()).then(pl.lit("readme_default_for_business"))
            .alias("gst_basis"),
            mdm.resolve_expr("rate_text_basis_raw", "rate_basis").alias("rate_text_basis"),
        )
        .with_columns(_project_match(projects).alias("project_match"))
        .with_columns(
            ex_gst(pl.col("rate_amount"), pl.col("gst_treatment")).round(2).alias("rate_ex_gst"),
        )
        .with_columns(
            (pl.col("rate_ex_gst") * 1.1).round(2).alias("rate_inc_gst"),
            to_day_rate(pl.col("rate_ex_gst"), pl.col("rate_basis")).round(2).alias("day_rate_ex_gst"),
            _status(as_of).alias("status"),
        )
    )
    return _mark_duplicates(hires).select(
        "hire_no", "status", "is_cancelled", "is_duplicate_line", "duplicate_of_row", "supplier_org_id",
        "supplier_name", "supplier_raw", "supplier_basis", "category", "category_raw", "category_basis",
        "project_code", "project_raw", "project_match", "business_code", "business_org_id", "business_code_raw",
        "start_date", "start_raw", "start_style", "start_ambiguous", "start_marker", "off_hire_date",
        "off_hire_raw", "off_hire_style", "off_hire_ambiguous", "off_hire_marker", "rate_amount", "rate_raw",
        "rate_text_basis", "rate_basis", "basis_raw", "gst_column", "gst_raw", "gst_treatment", "gst_basis",
        "rate_ex_gst", "rate_inc_gst", "day_rate_ex_gst", "notes", "comments", "strike", "source_tab", "source_row",
    )


def _mark_duplicates(hires: pl.DataFrame) -> pl.DataFrame:
    """A line identical in every cell to an earlier line is flagged, not dropped."""
    first_row = pl.col("source_row").min().over(DUPLICATE_COLUMNS)
    return hires.sort("source_row").with_columns(
        (pl.col("source_row") != first_row).alias("is_duplicate_line"),
        pl.when(pl.col("source_row") != first_row).then(first_row).alias("duplicate_of_row"),
    )
