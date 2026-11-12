"""Internal DQ & MDM console and reports, built from the warehouse. Not for Priya.

Outputs (under out/internal/):
  dq_console.html  one self-contained file: overview, checks, issues, row accounting,
                   master data, FieldTrax syncs, run history
  dq_report.md     scorecard, check results, new and resolved issues since the last run
  mdm_report.md    domain coverage, judgement calls, unmapped words, unused aliases
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import polars as pl

from brackenfield.config import Settings
from brackenfield.internal import reports

TEMPLATE = Path(__file__).with_name("template.html")
ENTITY_TABLES = {"machine": "machine_lines", "hire": "hires", "project": "projects", "rate_card": "rate_card"}
ISSUE_KEY = ["check_id", "entity_key", "source_tab", "source_row", "field", "message"]


def _q(con: duckdb.DuckDBPyConnection, sql: str) -> pl.DataFrame:
    return con.sql(sql).pl()


def _runs(con) -> pl.DataFrame:
    return _q(con, """SELECT run_id, started_at, finished_at, status, fieldtrax_refreshed, fieldtrax_requests,
                             row_counts, issue_counts, change_counts, workbook_sha256
                      FROM meta.runs ORDER BY run_id""")


def _issue_trend(con) -> pl.DataFrame:
    return _q(con, """SELECT run_id, severity, count(*) AS n FROM dq.issue_history GROUP BY ALL ORDER BY run_id, severity""")


def _issue_delta(con, runs: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(new, resolved) issues between the last two runs."""
    ids = runs["run_id"].to_list()
    if len(ids) < 2:
        empty = _q(con, "SELECT * FROM dq.issue_history LIMIT 0")
        return empty, empty
    cur = _q(con, f"SELECT * FROM dq.issue_history WHERE run_id = '{ids[-1]}'")
    prev = _q(con, f"SELECT * FROM dq.issue_history WHERE run_id = '{ids[-2]}'")
    new = cur.join(prev, on=ISSUE_KEY, how="anti", nulls_equal=True)
    resolved = prev.join(cur, on=ISSUE_KEY, how="anti", nulls_equal=True)
    return new, resolved


def _checks(con, runs: pl.DataFrame) -> pl.DataFrame:
    ids = runs["run_id"].to_list()
    last = ids[-1] if ids else ""
    prev = ids[-2] if len(ids) > 1 else ""
    return _q(con, f"""
        SELECT c.check_id, c.kind, c.entity, c.severity, c.for_priya, c.title, c.rationale,
               coalesce(r.violations, 0) AS violations, p.violations AS previous_violations
        FROM dq.check_catalogue c
        LEFT JOIN dq.check_results r ON r.check_id = c.check_id AND r.run_id = '{last}'
        LEFT JOIN dq.check_results p ON p.check_id = c.check_id AND p.run_id = '{prev}'
        ORDER BY c.kind DESC, c.check_id""")


def _scorecard(con, issues: pl.DataFrame) -> pl.DataFrame:
    """Per record table: how many records carry at least one error or warning."""
    flagged = issues.filter(pl.col("severity").is_in(["error", "warning"]), pl.col("source_row").is_not_null())
    rows = []
    for entity, table in ENTITY_TABLES.items():
        records = _q(con, f"SELECT source_tab, source_row FROM clean.{table}")
        hit = records.join(flagged.select("source_tab", "source_row").unique(), on=["source_tab", "source_row"], how="semi")
        errors = records.join(flagged.filter(pl.col("severity") == "error").select("source_tab", "source_row").unique(),
                              on=["source_tab", "source_row"], how="semi")
        rows.append({"entity": entity, "table": f"clean.{table}", "records": records.height,
                     "with_error": errors.height, "with_error_or_warning": hit.height,
                     "clean_pct": round(100 * (1 - hit.height / records.height), 1) if records.height else None})
    for table, key in (("devices", "device_id"), ("readings", "device_id")):
        records = _q(con, f"SELECT {key} FROM clean.{table}")
        hits = issues.filter(pl.col("source_tab") == "FieldTrax", pl.col("severity").is_in(["error", "warning"]),
                             pl.col("entity").is_in(["device", "reading", table]))
        n = hits.height if table == "readings" else hits["entity_key"].n_unique()
        rows.append({"entity": table.rstrip("s"), "table": f"clean.{table}", "records": records.height,
                     "with_error": None, "with_error_or_warning": n,
                     "clean_pct": round(100 * (1 - n / records.height), 1) if records.height else None})
    return pl.DataFrame(rows)


def _accounting(con) -> tuple[pl.DataFrame, pl.DataFrame]:
    summary = _q(con, """SELECT r.sheet_name, s.sheet_state, s.hidden_cols, r.disposition, count(*) AS n
                         FROM raw.workbook_rows r JOIN raw.workbook_sheets s USING (sheet_name)
                         GROUP BY ALL ORDER BY r.sheet_name, r.disposition""")
    non_records = _q(con, """SELECT sheet_name, row_num, disposition, first_cell, value_count, struck_count, comments
                             FROM raw.workbook_rows WHERE disposition <> 'record' ORDER BY sheet_name, row_num""")
    return summary, non_records


def _mdm(con) -> dict[str, pl.DataFrame]:
    usage = _q(con, "SELECT * FROM mdm.term_usage")
    aliases = _q(con, "SELECT * FROM mdm.aliases")
    canonical = _q(con, "SELECT * FROM mdm.canonical")
    seen = usage.select("domain", pl.col("matched_on").alias("written")).drop_nulls().unique()
    aliases = aliases.join(seen.with_columns(pl.lit(True).alias("seen")), on=["domain", "written"], how="left").with_columns(
        pl.col("seen").fill_null(False))
    coverage = usage.with_columns(pl.col("basis").fill_null("unmapped")).group_by("domain", "basis").agg(
        pl.col("line_count").sum().alias("lines"), pl.len().alias("terms")).sort("domain", "basis")
    return {"usage": usage, "aliases": aliases, "canonical": canonical, "coverage": coverage}


def _fieldtrax(con) -> tuple[pl.DataFrame, pl.DataFrame]:
    syncs = _q(con, "SELECT * FROM meta.fieldtrax_syncs ORDER BY run_id")
    errors = _q(con, "SELECT * FROM meta.fieldtrax_sync_errors ORDER BY run_id, scope, device_id")
    return syncs, errors


def _changes(con) -> pl.DataFrame:
    return _q(con, """SELECT run_id, table_name, change_type, count(DISTINCT record_key) AS records
                      FROM meta.record_changes GROUP BY ALL ORDER BY run_id, table_name, change_type""")


def collect(db_path: Path) -> dict[str, pl.DataFrame | dict]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        con.execute("SET TimeZone = 'UTC'")
        runs = _runs(con)
        issues = _q(con, "SELECT * FROM dq.issues")
        new, resolved = _issue_delta(con, runs)
        summary, non_records = _accounting(con)
        syncs, sync_errors = _fieldtrax(con)
        counts = {t: con.execute(f"SELECT count(*) FROM clean.{t}").fetchall()[0][0] for t in
                  ("organizations", "sites", "projects", "machines", "machine_lines", "hires", "rate_card", "devices", "readings")}
        return {
            "runs": runs, "trend": _issue_trend(con), "issues": issues, "new_issues": new, "resolved_issues": resolved,
            "checks": _checks(con, runs), "scorecard": _scorecard(con, issues), "accounting": summary,
            "non_records": non_records, "syncs": syncs, "sync_errors": sync_errors, "changes": _changes(con),
            "table_counts": counts, **{f"mdm_{k}": v for k, v in _mdm(con).items()},
        }
    finally:
        con.close()


def _records(frame: pl.DataFrame) -> list[dict]:
    return json.loads(frame.write_json()) if frame.height else []


def payload(data: dict) -> dict:
    out = {k: (_records(v) if isinstance(v, pl.DataFrame) else v) for k, v in data.items()}
    out["built_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    return out


def render(data: dict) -> str:
    blob = json.dumps(payload(data), default=str).replace("</", "<\\/")
    return TEMPLATE.read_text().replace("/*__DATA__*/null", blob)


def build_internal(settings: Settings, out_dir: Path) -> list[Path]:
    data = collect(settings.database_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "dq_console.html": render(data),
        "dq_report.md": reports.dq_report(data),
        "mdm_report.md": reports.mdm_report(data),
    }
    for name, text in files.items():
        (out_dir / name).write_text(text)
    return [out_dir / n for n in files]
