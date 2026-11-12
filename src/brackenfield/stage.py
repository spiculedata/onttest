"""Turn raw cells into one row per sheet row, and account for every row.

Each tab has a `SheetSpec` describing where its header is and what its columns
are called. Every row from 1 to the sheet's last row gets a disposition
(record, header, title, subtotal, total, documentation or blank), so a later
check can prove that nothing was dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

import polars as pl

from brackenfield.extract.workbook import WorkbookExtract

BE_PLANT = "BE Plant"
NH_FLEET = "NH Fleet"
PROJECTS = "Projects"
HIRES = "Hires 25-26"
OLD_RATES = "_old rates"
READ_ME = "READ ME"


def _plant_row_kind(first_cell: str | None) -> str:
    text = (first_cell or "").strip()
    if re.match(r"^subtotal\b", text, re.IGNORECASE):
        return "subtotal"
    if text.upper() == "TOTAL":
        return "total"
    return "record"


@dataclass(frozen=True)
class SheetSpec:
    name: str
    header_row: int | None
    columns: dict[str, str]  # header text as written -> field name
    entity: str
    classify: Callable[[str | None], str] = lambda _first: "record"

    @property
    def expected_headers(self) -> list[str]:
        return list(self.columns)


SHEET_SPECS: dict[str, SheetSpec] = {
    spec.name: spec
    for spec in (
        SheetSpec(READ_ME, None, {}, "documentation", lambda _first: "documentation"),
        SheetSpec(
            BE_PLANT,
            4,
            {
                "Fleet No": "fleet_no",
                "Description": "description",
                "Make": "make",
                "Model": "model",
                "Rego": "rego",
                "VIN": "vin",
                "Year": "year",
                "Status": "status",
                "Depot": "depot",
                "Capital cost": "capital_cost",
                "Operator mobile": "operator_mobile",
            },
            "machine",
            _plant_row_kind,
        ),
        SheetSpec(
            NH_FLEET,
            1,
            {
                "Unit": "fleet_no",
                "Type": "description",
                "Reg": "rego",
                "Chassis/VIN": "vin",
                "Yr": "year",
                "Status": "status",
                "Location": "depot",
                "Purchase $": "capital_cost",
            },
            "machine",
            _plant_row_kind,
        ),
        SheetSpec(
            PROJECTS,
            1,
            {"Code": "project_code", "Name": "name", "State": "state", "Business": "business_code"},
            "project",
        ),
        SheetSpec(
            HIRES,
            1,
            {
                "Hire No": "hire_no",
                "Supplier": "supplier",
                "Category": "category",
                "Project": "project",
                "BU": "business_code",
                "Start": "start",
                "Off-hire": "off_hire",
                "Rate": "rate",
                "Basis": "basis",
                "GST": "gst",
                "Notes": "notes",
            },
            "hire",
        ),
        SheetSpec(
            OLD_RATES,
            1,
            {"Category": "category", "Old day rate (superseded Jan-25)": "day_rate"},
            "rate_card",
        ),
    )
}


class UnknownSheetError(RuntimeError):
    pass


class HeaderMismatchError(RuntimeError):
    pass


def header_row_values(cells: pl.DataFrame, spec: SheetSpec) -> list[str]:
    header = cells.filter(pl.col("sheet_name") == spec.name, pl.col("row_num") == spec.header_row)
    return header.sort("col_num")["value_text"].to_list()


def verify_layout(extract: WorkbookExtract) -> None:
    """Fail fast if a tab appears or a header changes: the mapping would be wrong."""
    unknown = set(extract.sheets["sheet_name"]) - set(SHEET_SPECS)
    if unknown:
        raise UnknownSheetError(f"Workbook has tabs with no SheetSpec: {sorted(unknown)}")
    for spec in SHEET_SPECS.values():
        if spec.header_row is None:
            continue
        found = header_row_values(extract.cells, spec)
        if found != spec.expected_headers:
            raise HeaderMismatchError(f"{spec.name!r} header row {spec.header_row}: expected {spec.expected_headers}, found {found}")


def _row_summary(cells: pl.DataFrame) -> pl.DataFrame:
    """One row per (sheet, row) with strike/comment/hidden flags rolled up."""
    valued = pl.col("value_text").is_not_null()
    return cells.group_by("sheet_name", "row_num").agg(
        pl.col("value_text").filter(pl.col("col_num") == pl.col("col_num").min()).first().alias("first_cell"),
        valued.sum().alias("value_count"),
        (pl.col("is_strike") & valued).sum().alias("struck_count"),
        pl.col("is_hidden_row").any().alias("is_hidden_row"),
        pl.concat_str(pl.col("col_letter"), pl.lit(": "), pl.col("comment_text"))
        .filter(pl.col("comment_text").is_not_null())
        .str.join("; ")
        .alias("comments"),
    )


def build_dispositions(extract: WorkbookExtract) -> pl.DataFrame:
    """Every row of every sheet, 1..max_row, with what we did with it."""
    summary = _row_summary(extract.cells)
    frames = []
    for sheet in extract.sheets.iter_rows(named=True):
        spec = SHEET_SPECS[sheet["sheet_name"]]
        rows = pl.DataFrame({"sheet_name": sheet["sheet_name"], "row_num": range(1, sheet["max_row"] + 1)})
        rows = rows.with_columns(pl.col("row_num").cast(pl.Int32)).join(summary, on=["sheet_name", "row_num"], how="left")
        kinds = [
            _disposition(spec, r["row_num"], r["value_count"], r["first_cell"]) for r in rows.iter_rows(named=True)
        ]
        frames.append(
            rows.with_columns(
                pl.Series("disposition", kinds, dtype=pl.String),
                pl.lit(sheet["sheet_state"]).alias("sheet_state"),
                pl.lit(spec.entity).alias("entity"),
            )
        )
    return pl.concat(frames).with_columns(
        pl.col("value_count").fill_null(0),
        pl.col("struck_count").fill_null(0),
        pl.col("is_hidden_row").fill_null(False),
    )


def _disposition(spec: SheetSpec, row_num: int, value_count: int | None, first_cell: str | None) -> str:
    if not value_count:
        return "blank"
    if spec.header_row is None:
        return spec.classify(first_cell)
    if row_num < spec.header_row:
        return "title"
    if row_num == spec.header_row:
        return "header"
    return spec.classify(first_cell)


def sheet_rows(extract: WorkbookExtract, dispositions: pl.DataFrame, sheet_name: str, kind: str = "record") -> pl.DataFrame:
    """Wide frame for one sheet: one column per header (as text) plus provenance.

    Columns: source_tab, source_row, <field names...>, strike ("none"/"partial"/"all"),
    comments. Rows are those whose disposition equals `kind`.
    """
    spec = SHEET_SPECS[sheet_name]
    wanted = dispositions.filter(pl.col("sheet_name") == sheet_name, pl.col("disposition") == kind)
    header_cols = (
        extract.cells.filter(pl.col("sheet_name") == sheet_name, pl.col("row_num") == spec.header_row)
        .select("col_num", pl.col("value_text").replace_strict(spec.columns).alias("field"))
    )
    body = (
        extract.cells.filter(pl.col("sheet_name") == sheet_name)
        .join(wanted.select("row_num"), on="row_num", how="semi")
        .join(header_cols, on="col_num", how="left")
        .with_columns(pl.col("field").fill_null(pl.concat_str(pl.lit("col_"), pl.col("col_letter"))))
    )
    wide = body.pivot(on="field", index="row_num", values="value_text", aggregate_function="first")
    for field in spec.columns.values():
        if field not in wide.columns:
            wide = wide.with_columns(pl.lit(None, dtype=pl.String).alias(field))
    strike = pl.when(pl.col("struck_count") == 0).then(pl.lit("none"))
    strike = strike.when(pl.col("struck_count") == pl.col("value_count")).then(pl.lit("all")).otherwise(pl.lit("partial"))
    return (
        wanted.select("row_num", strike.alias("strike"), "comments")
        .join(wide, on="row_num", how="left")
        .with_columns(pl.lit(sheet_name).alias("source_tab"), pl.col("row_num").alias("source_row"))
        .select("source_tab", "source_row", *spec.columns.values(), "strike", "comments")
        .sort("source_row")
    )
