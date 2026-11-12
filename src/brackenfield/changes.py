"""What a run changed: field-level diff of every clean table, before vs after.

This is how "the second run must change nothing" is proven rather than
asserted: an unchanged source gives an empty diff.
"""

from __future__ import annotations

import polars as pl

TABLE_KEYS: dict[str, list[str]] = {
    "organizations": ["org_id"],
    "org_aliases": ["alias"],
    "sites": ["site_id"],
    "projects": ["project_code"],
    "machines": ["machine_id"],
    "machine_lines": ["source_tab", "source_row"],
    "hires": ["source_tab", "source_row"],
    "rate_card": ["source_tab", "source_row"],
    "devices": ["device_id"],
    "readings": ["device_id", "metric", "time_utc", "payload"],
}

# Columns computed from other columns or from history. A change in them is reported as
# "recomputed" so the "changed" rows are only values that came from a source.
DERIVED_COLUMNS: dict[str, set[str]] = {
    "devices": {"name_suffix", "name_business_code", "name_fleet_no", "retired_on", "last_changed_at", "version_count",
                "vin", "rego", "link_method"},
    "readings": {"hours_delta", "elapsed_hours", "is_after_retirement"},
    "machines": {"register_line_count", "source_refs"},
    "machine_lines": {"identity_group"},
}

CHANGE_SCHEMA = {
    "table_name": pl.String,
    "change_type": pl.String,
    "record_key": pl.String,
    "field": pl.String,
    "old_value": pl.String,
    "new_value": pl.String,
}


def _as_text(frame: pl.DataFrame) -> pl.DataFrame:
    """Every column as comparable text; timestamps in UTC so a DuckDB round trip compares equal."""
    exprs = []
    for name, dtype in frame.schema.items():
        col = pl.col(name)
        if isinstance(dtype, pl.Datetime) and dtype.time_zone:
            col = col.dt.convert_time_zone("UTC")
        if dtype == pl.Float64 or dtype == pl.Float32:
            col = col.round(9)
        exprs.append(col.cast(pl.String).alias(name))
    return frame.select(exprs)


def _key_expr(keys: list[str]) -> pl.Expr:
    return pl.concat_str([pl.col(k).fill_null("∅") for k in keys], separator=" | ")


def _whole_rows(frame: pl.DataFrame, table: str, keys: list[str], change_type: str) -> pl.DataFrame:
    return frame.select(
        pl.lit(table).alias("table_name"),
        pl.lit(change_type).alias("change_type"),
        _key_expr(keys).alias("record_key"),
        pl.lit(None, dtype=pl.String).alias("field"),
        pl.lit(None, dtype=pl.String).alias("old_value"),
        pl.lit(None, dtype=pl.String).alias("new_value"),
    )


def diff_table(table: str, old: pl.DataFrame | None, new: pl.DataFrame) -> pl.DataFrame:
    keys = TABLE_KEYS[table]
    new_t = _as_text(new)
    if old is None:
        return _whole_rows(new_t, table, keys, "added")
    old_t = _as_text(old)
    common = [c for c in new_t.columns if c in old_t.columns and c not in keys]
    added = _whole_rows(new_t.join(old_t, on=keys, how="anti", nulls_equal=True), table, keys, "added")
    removed = _whole_rows(old_t.join(new_t, on=keys, how="anti", nulls_equal=True), table, keys, "removed")
    both = new_t.select(keys + common).join(old_t.select(keys + common), on=keys, how="inner", nulls_equal=True, suffix="__old")
    changed = [
        both.filter(pl.col(c).ne_missing(pl.col(f"{c}__old"))).select(
            pl.lit(table).alias("table_name"),
            pl.lit("recomputed" if c in DERIVED_COLUMNS.get(table, set()) else "changed").alias("change_type"),
            _key_expr(keys).alias("record_key"),
            pl.lit(c).alias("field"),
            pl.col(f"{c}__old").alias("old_value"),
            pl.col(c).alias("new_value"),
        )
        for c in common
    ]
    schema_changes = [
        pl.DataFrame([{"table_name": table, "change_type": kind, "record_key": None, "field": col,
                       "old_value": None, "new_value": None}], schema=CHANGE_SCHEMA)
        for kind, cols in (("column_added", set(new_t.columns) - set(old_t.columns)),
                           ("column_removed", set(old_t.columns) - set(new_t.columns)))
        for col in sorted(cols)
    ]
    return pl.concat([added, removed, *changed, *schema_changes], how="vertical").cast(CHANGE_SCHEMA)


def diff_tables(old: dict[str, pl.DataFrame | None], new: dict[str, pl.DataFrame]) -> pl.DataFrame:
    frames = [diff_table(name, old.get(name), frame) for name, frame in new.items() if name in TABLE_KEYS]
    return pl.concat(frames).sort("table_name", "change_type", "record_key", "field", nulls_last=True)


def summarise(changes: pl.DataFrame) -> dict[str, dict[str, int]]:
    """{table: {added: n, removed: n, changed: n records}}"""
    out: dict[str, dict[str, int]] = {}
    counts = changes.group_by("table_name", "change_type").agg(pl.col("record_key").n_unique().alias("n"))
    for table, kind, n in counts.sort("table_name", "change_type").iter_rows():
        out.setdefault(table, {})[kind] = n
    return out
