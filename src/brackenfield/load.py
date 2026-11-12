"""DuckDB storage.

Schemas:
  raw    the workbook cell by cell, and every FieldTrax snapshot (append-only)
  clean  the records: organizations, sites, projects, machines, hires, devices, readings...
  dq     check catalogue, issues for this run, issue history, Priya's list (view)
  meta   one row per pipeline run

`clean` and `dq.issues` are rebuilt on each run inside one transaction, so a
failed run leaves the previous good state in place. Re-running on an unchanged
workbook gives the same rows.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb
import polars as pl

SCHEMAS = ("raw", "mdm", "clean", "dq", "meta")

DDL = """
CREATE TABLE IF NOT EXISTS raw.fieldtrax_device_versions (
    device_id VARCHAR, name VARCHAR, vin VARCHAR, rego VARCHAR, retired_at VARCHAR, unit VARCHAR,
    payload VARCHAR, is_listed BOOLEAN, valid_from TIMESTAMPTZ, sync_run VARCHAR
);
CREATE TABLE IF NOT EXISTS raw.fieldtrax_reading_lines (
    device_id VARCHAR, time VARCHAR, metric VARCHAR, value VARCHAR, unit VARCHAR, payload VARCHAR,
    first_seen_run VARCHAR, first_seen_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS meta.fieldtrax_syncs (
    run_id VARCHAR, fetched_at TIMESTAMPTZ, devices_listed INTEGER, readings_received INTEGER,
    new_readings INTEGER, new_device_versions INTEGER, errors INTEGER, stats JSON
);
CREATE TABLE IF NOT EXISTS meta.fieldtrax_sync_errors (
    run_id VARCHAR, scope VARCHAR, device_id VARCHAR, error VARCHAR, payload VARCHAR
);
CREATE TABLE IF NOT EXISTS meta.run_labels (
    label VARCHAR PRIMARY KEY, run_id VARCHAR, labelled_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS meta.record_changes (
    run_id VARCHAR, table_name VARCHAR, change_type VARCHAR, record_key VARCHAR,
    field VARCHAR, old_value VARCHAR, new_value VARCHAR
);
CREATE TABLE IF NOT EXISTS meta.runs (
    run_id VARCHAR PRIMARY KEY, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
    workbook_path VARCHAR, workbook_sha256 VARCHAR, fieldtrax_refreshed BOOLEAN,
    fieldtrax_requests INTEGER, row_counts JSON, issue_counts JSON, change_counts JSON, status VARCHAR
);
CREATE TABLE IF NOT EXISTS dq.issue_history (
    run_id VARCHAR, check_id VARCHAR, check_title VARCHAR, entity VARCHAR, severity VARCHAR,
    for_priya BOOLEAN, entity_key VARCHAR, source_tab VARCHAR, source_row INTEGER,
    field VARCHAR, raw_value VARCHAR, message VARCHAR
);
CREATE TABLE IF NOT EXISTS dq.check_results (run_id VARCHAR, check_id VARCHAR, violations BIGINT);
"""

PRIYA_VIEW = """
CREATE OR REPLACE VIEW dq.priya_list AS
SELECT
    row_number() OVER (ORDER BY CASE severity WHEN 'error' THEN 0 ELSE 1 END, check_id, source_tab, source_row, entity_key) AS item,
    severity, check_id, check_title, entity, entity_key, source_tab, source_row, field, raw_value, message
FROM dq.issues
WHERE for_priya
"""


@contextmanager
def connect(path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        con.execute("SET TimeZone = 'UTC'")
        for schema in SCHEMAS:
            con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        con.execute(DDL)
        yield con
    finally:
        con.close()


def _replace(con: duckdb.DuckDBPyConnection, table: str, frame: pl.DataFrame) -> None:
    con.register("_frame", frame.to_arrow())
    try:
        con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _frame")
    finally:
        con.unregister("_frame")


def _append(con: duckdb.DuckDBPyConnection, table: str, frame: pl.DataFrame) -> None:
    if frame.is_empty():
        return
    con.register("_frame", frame.to_arrow())
    try:
        con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM _frame")
    finally:
        con.unregister("_frame")


DEVICE_VERSION_COLUMNS = ["device_id", "name", "vin", "rego", "retired_at", "unit", "payload", "is_listed"]


def _current_device_versions(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    return con.sql(
        "SELECT * EXCLUDE (rn) FROM (SELECT *, row_number() OVER (PARTITION BY device_id ORDER BY valid_from DESC) rn "
        "FROM raw.fieldtrax_device_versions) WHERE rn = 1"
    ).pl()


def changed_device_versions(current: pl.DataFrame, listed: pl.DataFrame) -> pl.DataFrame:
    """Rows to append: devices that are new or differ, plus devices that stopped being listed.

    Compared on the device's full JSON payload and whether it is listed, so an
    unchanged device list produces no rows.
    """
    listed = listed.with_columns(pl.lit(True).alias("is_listed")).select(DEVICE_VERSION_COLUMNS)
    if current.is_empty():
        return listed
    current = current.select(DEVICE_VERSION_COLUMNS)
    gone = current.filter(pl.col("is_listed")).join(listed, on="device_id", how="anti").with_columns(pl.lit(False).alias("is_listed"))
    candidates = pl.concat([listed, gone])
    return candidates.join(current, on=["device_id", "payload", "is_listed"], how="anti", nulls_equal=True)


def append_fieldtrax_snapshot(con: duckdb.DuckDBPyConnection, run_id: str, snapshot) -> dict[str, int]:
    """Land a snapshot without duplicating anything already stored. Returns what was new."""
    versions = changed_device_versions(_current_device_versions(con), snapshot.devices)
    _append(con, "raw.fieldtrax_device_versions", versions.with_columns(
        pl.lit(snapshot.fetched_at).alias("valid_from"), pl.lit(run_id).alias("sync_run")))
    known = con.sql("SELECT device_id, payload FROM raw.fieldtrax_reading_lines").pl()
    fresh = snapshot.readings.unique(subset=["device_id", "payload"], keep="first", maintain_order=True)
    fresh = fresh.join(known, on=["device_id", "payload"], how="anti") if known.height else fresh
    _append(con, "raw.fieldtrax_reading_lines", fresh.with_columns(
        pl.lit(run_id).alias("first_seen_run"), pl.lit(snapshot.fetched_at).alias("first_seen_at")))
    _append(con, "meta.fieldtrax_sync_errors", snapshot.errors.with_columns(pl.lit(run_id).alias("run_id")))
    counts = {
        "devices_listed": snapshot.devices.height, "readings_received": snapshot.readings.height,
        "new_readings": fresh.height, "new_device_versions": versions.height, "errors": snapshot.errors.height,
    }
    _append(con, "meta.fieldtrax_syncs", pl.DataFrame([{
        "run_id": run_id, "fetched_at": snapshot.fetched_at, **counts, "stats": json.dumps(snapshot.stats.as_dict())}]))
    return counts


def read_fieldtrax_raw(con: duckdb.DuckDBPyConnection) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """All device versions, all reading lines, and the errors from the most recent sync."""
    versions = con.sql("SELECT * FROM raw.fieldtrax_device_versions").pl()
    readings = con.sql("SELECT * FROM raw.fieldtrax_reading_lines").pl()
    errors = con.sql(
        "SELECT * FROM meta.fieldtrax_sync_errors WHERE run_id = (SELECT max(run_id) FROM meta.fieldtrax_syncs)"
    ).pl()
    return versions, readings, errors


class LabelError(ValueError):
    pass


def label_run(con: duckdb.DuckDBPyConnection, label: str, run_id: str) -> None:
    """Pin a name (e.g. "before_advance") to a FieldTrax sync, so views can rebuild FieldTrax as it was then."""
    if not con.execute("SELECT 1 FROM meta.fieldtrax_syncs WHERE run_id = ?", [run_id]).fetchall():
        raise LabelError(f"{run_id} is not a run that synced FieldTrax; label a run that refreshed it")
    con.execute("DELETE FROM meta.run_labels WHERE label = ?", [label])
    con.execute("INSERT INTO meta.run_labels VALUES (?, ?, now())", [label, run_id])


def read_clean_tables(con: duckdb.DuckDBPyConnection, names: list[str]) -> dict[str, pl.DataFrame | None]:
    """The clean tables as they stand before this run (None when absent), for the change report."""
    existing = {r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'clean'").fetchall()}
    return {name: con.sql(f"SELECT * FROM clean.{name}").pl() if name in existing else None for name in names}


@contextmanager
def transaction(con: duckdb.DuckDBPyConnection) -> Iterator[None]:
    """One run = one transaction: the FieldTrax append and the clean rebuild land together or not at all."""
    con.execute("BEGIN TRANSACTION")
    try:
        yield
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise


def write_run(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    raw_tables: dict[str, pl.DataFrame],
    clean_tables: dict[str, pl.DataFrame],
    issues: pl.DataFrame,
    check_results: pl.DataFrame,
    catalogue: pl.DataFrame,
    changes: pl.DataFrame,
    run_row: dict,
    mdm_tables: dict[str, pl.DataFrame] | None = None,
) -> None:
    for name, frame in raw_tables.items():
        _replace(con, f"raw.{name}", frame)
    for name, frame in (mdm_tables or {}).items():
        _replace(con, f"mdm.{name}", frame)
    for name, frame in clean_tables.items():
        _replace(con, f"clean.{name}", frame)
    _replace(con, "dq.issues", issues)
    _replace(con, "dq.check_catalogue", catalogue)
    con.execute(PRIYA_VIEW)
    _append(con, "dq.issue_history", issues.with_columns(pl.lit(run_id).alias("run_id")))
    _append(con, "dq.check_results", check_results.with_columns(pl.lit(run_id).alias("run_id")))
    _append(con, "meta.record_changes", changes.with_columns(pl.lit(run_id).alias("run_id")))
    _append(con, "meta.runs", pl.DataFrame([run_row]))
