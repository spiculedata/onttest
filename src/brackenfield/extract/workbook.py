"""Read the workbook exactly as it is: every tab, every non-empty cell.

Nothing is interpreted here. Each cell becomes one row carrying its value as
text, its Excel type and everything about how it looks that could carry meaning
(strike-through, hidden row/column, hidden sheet, comments, fills, fonts).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import openpyxl
import polars as pl
from openpyxl.cell.cell import Cell
from openpyxl.worksheet.worksheet import Worksheet

CELL_SCHEMA = {
    "sheet_name": pl.String,
    "sheet_index": pl.Int32,
    "row_num": pl.Int32,
    "col_num": pl.Int32,
    "col_letter": pl.String,
    "coordinate": pl.String,
    "value_text": pl.String,
    "value_type": pl.String,
    "number_format": pl.String,
    "is_strike": pl.Boolean,
    "is_bold": pl.Boolean,
    "font_rgb": pl.String,
    "fill_rgb": pl.String,
    "is_hidden_row": pl.Boolean,
    "is_hidden_col": pl.Boolean,
    "is_merged": pl.Boolean,
    "comment_text": pl.String,
    "comment_author": pl.String,
}

SHEET_SCHEMA = {
    "sheet_name": pl.String,
    "sheet_index": pl.Int32,
    "sheet_state": pl.String,
    "max_row": pl.Int32,
    "max_col": pl.Int32,
    "hidden_rows": pl.String,
    "hidden_cols": pl.String,
    "merged_ranges": pl.String,
}


@dataclass(frozen=True)
class WorkbookExtract:
    path: Path
    sha256: str
    sheets: pl.DataFrame
    cells: pl.DataFrame


class WorkbookReadError(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cell_value_text(value: object) -> tuple[str | None, str]:
    """Render a cell value as text plus a type tag, without losing information."""
    if value is None:
        return None, "empty"
    if isinstance(value, bool):
        return str(value).upper(), "bool"
    if isinstance(value, datetime):
        if value.time() == datetime.min.time():
            return value.date().isoformat(), "date"
        return value.isoformat(), "datetime"
    if isinstance(value, date):
        return value.isoformat(), "date"
    if isinstance(value, float) and value.is_integer():
        return str(int(value)), "number"
    if isinstance(value, (int, float)):
        return str(value), "number"
    return str(value), "string"


def _rgb(color: object) -> str | None:
    rgb = getattr(color, "rgb", None)
    if getattr(color, "type", None) == "rgb" and isinstance(rgb, str):
        return rgb
    return None


def _cell_record(ws: Worksheet, sheet_index: int, cell: Cell, merged: set[str]) -> dict:
    value_text, value_type = cell_value_text(cell.value)
    fill_rgb = _rgb(cell.fill.fgColor) if cell.fill.fill_type else None
    return {
        "sheet_name": ws.title,
        "sheet_index": sheet_index,
        "row_num": cell.row,
        "col_num": cell.column,
        "col_letter": cell.column_letter,
        "coordinate": cell.coordinate,
        "value_text": value_text,
        "value_type": value_type,
        "number_format": cell.number_format,
        "is_strike": bool(cell.font.strike),
        "is_bold": bool(cell.font.b),
        "font_rgb": _rgb(cell.font.color),
        "fill_rgb": fill_rgb,
        "is_hidden_row": bool(ws.row_dimensions[cell.row].hidden),
        "is_hidden_col": bool(ws.column_dimensions[cell.column_letter].hidden),
        "is_merged": cell.coordinate in merged,
        "comment_text": cell.comment.text if cell.comment else None,
        "comment_author": cell.comment.author if cell.comment else None,
    }


def _merged_coordinates(ws: Worksheet) -> set[str]:
    coords: set[str] = set()
    for rng in ws.merged_cells.ranges:
        for row in ws.iter_rows(min_row=rng.min_row, max_row=rng.max_row, min_col=rng.min_col, max_col=rng.max_col):
            coords.update(c.coordinate for c in row)
    return coords


def _sheet_record(ws: Worksheet, sheet_index: int) -> dict:
    hidden_rows = sorted(r for r, d in ws.row_dimensions.items() if d.hidden)
    hidden_cols = sorted(c for c, d in ws.column_dimensions.items() if d.hidden)
    return {
        "sheet_name": ws.title,
        "sheet_index": sheet_index,
        "sheet_state": ws.sheet_state,
        "max_row": ws.max_row,
        "max_col": ws.max_column,
        "hidden_rows": ",".join(map(str, hidden_rows)) or None,
        "hidden_cols": ",".join(hidden_cols) or None,
        "merged_ranges": ",".join(str(r) for r in ws.merged_cells.ranges) or None,
    }


def _sheet_cells(ws: Worksheet, sheet_index: int) -> list[dict]:
    merged = _merged_coordinates(ws)
    return [
        _cell_record(ws, sheet_index, cell, merged)
        for row in ws.iter_rows()
        for cell in row
        if cell.value is not None or cell.comment is not None
    ]


def read_workbook(path: Path) -> WorkbookExtract:
    if not path.exists():
        raise WorkbookReadError(f"Workbook not found: {path}")
    try:
        # data_only=False keeps formulas as written; the register is typed values,
        # and a formula would show up as value_type "string" starting with "=".
        wb = openpyxl.load_workbook(path, data_only=False)
    except Exception as exc:  # openpyxl raises a zoo of exception types
        raise WorkbookReadError(f"Could not open {path.name}: {exc}") from exc

    sheets = [_sheet_record(ws, i) for i, ws in enumerate(wb.worksheets)]
    cells = [rec for i, ws in enumerate(wb.worksheets) for rec in _sheet_cells(ws, i)]
    return WorkbookExtract(
        path=path,
        sha256=file_sha256(path),
        sheets=pl.DataFrame(sheets, schema=SHEET_SCHEMA),
        cells=pl.DataFrame(cells, schema=CELL_SCHEMA),
    )
