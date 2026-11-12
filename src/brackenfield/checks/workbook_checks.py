"""Checks on the workbook as a whole: nothing dropped, nothing hidden unnoticed, totals."""

from __future__ import annotations

import polars as pl

from brackenfield.checks.registry import Tables, check, no_violations, violations
from brackenfield.stage import BE_PLANT, HIRES, SHEET_SPECS
from brackenfield.transform.parsing import parse_money

RECORD_TABLES = {"machine": "machine_lines", "hire": "hires", "project": "projects", "rate_card": "rate_card"}


def _cell_ref(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.rename({"sheet_name": "source_tab", "row_num": "source_row"})


@check(
    "WB001", "Every record row on every tab reached a clean table", "workbook", "error",
    "Nothing is dropped silently: each row classed as a record must appear in its target table.",
)
def every_record_row_landed(t: Tables) -> pl.DataFrame:
    landed = pl.concat(
        [getattr(t, table).select("source_tab", "source_row") for table in RECORD_TABLES.values()]
    ).unique()
    expected = _cell_ref(t.dispositions.filter(pl.col("disposition") == "record").select("sheet_name", "row_num"))
    missing = expected.join(landed, on=["source_tab", "source_row"], how="anti")
    return violations(missing, key=pl.lit(None), field=None, raw=None, message="Record row did not reach any clean table")


@check(
    "WB002", "Tab names and header rows match the expected layout", "workbook", "error",
    "Enforced before anything is written: an unknown tab or a changed header aborts the run, "
    "because columns would otherwise be mapped to the wrong fields.",
)
def layout_precondition(_t: Tables) -> pl.DataFrame:
    return no_violations()


@check(
    "WB003", "No values sit outside the header columns", "workbook", "error",
    "A value typed beyond the last named column would not map to any field.",
)
def values_outside_headers(t: Tables) -> pl.DataFrame:
    frames = []
    for spec in SHEET_SPECS.values():
        if spec.header_row is None:
            continue
        stray = t.cells.filter(
            pl.col("sheet_name") == spec.name,
            pl.col("row_num") > spec.header_row,
            pl.col("col_num") > len(spec.columns),
            pl.col("value_text").is_not_null(),
        )
        frames.append(violations(_cell_ref(stray), key="coordinate", field="col_letter", raw="value_text",
                                 message=pl.format("Value in unnamed column {}", pl.col("col_letter"))))
    return pl.concat(frames)


@check(
    "WB004", "Hidden tabs, columns and rows are read, not skipped", "workbook", "info",
    "Hidden content is part of the register; this lists what was hidden and was ingested anyway.",
)
def hidden_content(t: Tables) -> pl.DataFrame:
    sheets = t.sheets.filter(pl.col("sheet_state") != "visible").select(
        pl.col("sheet_name").alias("source_tab"), pl.lit(None, dtype=pl.Int32).alias("source_row"),
        pl.format("Tab is {}", pl.col("sheet_state")).alias("message"), pl.col("sheet_name").alias("key"),
    )
    cols = t.sheets.filter(pl.col("hidden_cols").is_not_null()).select(
        pl.col("sheet_name").alias("source_tab"), pl.lit(None, dtype=pl.Int32).alias("source_row"),
        pl.format("Hidden column(s) {} read", pl.col("hidden_cols")).alias("message"), pl.col("sheet_name").alias("key"),
    )
    rows = t.dispositions.filter(pl.col("is_hidden_row")).select(
        pl.col("sheet_name").alias("source_tab"), pl.col("row_num").alias("source_row"),
        pl.lit("Hidden row read").alias("message"), pl.col("sheet_name").alias("key"),
    )
    found = pl.concat([sheets, cols, rows])
    return violations(found, key="key", field=None, raw=None, message=pl.col("message"))


@check(
    "WB005", "Cell comments are captured as data", "workbook", "info",
    "Comments are stored verbatim (raw.workbook_cells, and the row's `comments` column). "
    "They are recorded, never acted on.",
)
def cell_comments(t: Tables) -> pl.DataFrame:
    found = _cell_ref(t.cells.filter(pl.col("comment_text").is_not_null()))
    return violations(found, key="coordinate", field="comment", raw="comment_text",
                      message=pl.format("Comment by {} recorded", pl.col("comment_author")))


@check(
    "WB006", "Strike-through covers the whole line or none of it", "workbook", "warning",
    "READ ME: struck-through hire lines are cancelled. A partly struck line is ambiguous.",
)
def partial_strike(t: Tables) -> pl.DataFrame:
    found = _cell_ref(t.dispositions.filter(pl.col("struck_count") > 0, pl.col("struck_count") < pl.col("value_count")))
    return violations(found, key=pl.lit(None), field=None, raw=None,
                      message=pl.format("{} of {} cells struck through", pl.col("struck_count"), pl.col("value_count")))


@check(
    "WB007", "Strike-through only appears on the hire sheet", "workbook", "warning",
    "Strike-through means 'cancelled' only on Hires 25-26; elsewhere its meaning is unknown.",
)
def strike_elsewhere(t: Tables) -> pl.DataFrame:
    found = _cell_ref(t.dispositions.filter(pl.col("struck_count") > 0, pl.col("sheet_name") != HIRES))
    return violations(found, key=pl.lit(None), field=None, raw=None, message="Struck-through cells outside the hire sheet")


def _plant_blocks(t: Tables) -> pl.DataFrame:
    """BE Plant record rows tagged with the subtotal row that closes their block."""
    rows = t.dispositions.filter(pl.col("sheet_name") == BE_PLANT, pl.col("disposition").is_in(["record", "subtotal"]))
    rows = rows.sort("row_num").with_columns(
        pl.when(pl.col("disposition") == "subtotal").then(pl.col("row_num")).backward_fill().alias("block_row")
    )
    costs = t.machine_lines.filter(pl.col("source_tab") == BE_PLANT).select(
        pl.col("source_row").alias("row_num"), "capital_cost_aud", "capital_cost_raw"
    )
    return rows.filter(pl.col("disposition") == "record").join(costs, on="row_num", how="left")


def _typed_totals(t: Tables, kind: str) -> pl.DataFrame:
    return (
        t.cells.filter(pl.col("sheet_name") == BE_PLANT, pl.col("col_letter") == "J")
        .join(t.dispositions.filter(pl.col("sheet_name") == BE_PLANT, pl.col("disposition") == kind),
              on=["sheet_name", "row_num"], how="semi")
        .select("row_num", "value_text", parse_money("value_text").alias("typed"))
    )


@check(
    "WB008", "Typed subtotals equal the sum of the lines above them", "workbook", "warning",
    "READ ME: \"Don't trust the totals. Somebody types them.\" Totals are never loaded as data; "
    "this compares them with the computed sums.",
)
def subtotals_reconcile(t: Tables) -> pl.DataFrame:
    computed = _plant_blocks(t).group_by("block_row").agg(
        pl.col("capital_cost_aud").sum().alias("computed"),
        pl.col("capital_cost_aud").is_null().sum().alias("unpriced"),
    )
    typed = _typed_totals(t, "subtotal").rename({"row_num": "block_row"})
    found = typed.join(computed, on="block_row", how="left").filter(
        (pl.col("typed") - pl.col("computed")).abs() > 0.5
    ).with_columns(pl.lit(BE_PLANT).alias("source_tab"), pl.col("block_row").alias("source_row"))
    return violations(found, key=pl.lit("capital cost subtotal"), field="Capital cost", raw="value_text", message=pl.format(
        "Typed {} but lines sum to {} ({} line(s) without a number)", pl.col("typed"), pl.col("computed"), pl.col("unpriced")))


@check(
    "WB009", "Typed grand total equals the sum of all lines", "workbook", "warning",
    "Same as WB008 for the TOTAL row.",
)
def total_reconciles(t: Tables) -> pl.DataFrame:
    computed = _plant_blocks(t)["capital_cost_aud"].sum()
    subtotal_sum = _typed_totals(t, "subtotal")["typed"].sum()
    found = _typed_totals(t, "total").filter((pl.col("typed") - computed).abs() > 0.5).with_columns(
        pl.lit(BE_PLANT).alias("source_tab"), pl.col("row_num").alias("source_row")
    )
    return violations(found, key=pl.lit("capital cost total"), field="Capital cost", raw="value_text", message=pl.format(
        "Typed {} but lines sum to {}; typed subtotals sum to {}", pl.col("typed"), pl.lit(computed), pl.lit(subtotal_sum)))
