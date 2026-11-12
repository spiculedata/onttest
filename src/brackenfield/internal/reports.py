"""Markdown reports for the data team: DQ scorecard and MDM review."""

from __future__ import annotations

import json

import polars as pl


def _cell(v: object) -> str:
    return "" if v is None else str(v).replace("|", "\\|").replace("\n", " ")


def _table(frame: pl.DataFrame, columns: list[str], headers: list[str] | None = None, limit: int | None = None) -> list[str]:
    if frame.is_empty():
        return ["_None._", ""]
    rows = frame.head(limit) if limit else frame
    lines = ["| " + " | ".join(headers or columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(_cell(r[c]) for c in columns) + " |" for r in rows.iter_rows(named=True)]
    if limit and frame.height > limit:
        lines.append(f"\n_{frame.height - limit} more not shown; see the console or dq.issues._")
    return lines + [""]


def _latest(data: dict) -> dict:
    runs: pl.DataFrame = data["runs"]
    return runs.row(-1, named=True) if runs.height else {}


def dq_report(data: dict) -> str:
    run = _latest(data)
    issues: pl.DataFrame = data["issues"]
    checks: pl.DataFrame = data["checks"]
    sev = {s: issues.filter(pl.col("severity") == s).height for s in ("error", "warning", "info")}
    failing = checks.filter(pl.col("violations") > 0)
    moved = checks.filter(pl.col("previous_violations").is_not_null() & (pl.col("violations") != pl.col("previous_violations")))
    lines = [
        "# Data quality report (internal)", "",
        f"Run `{run.get('run_id')}` · status **{run.get('status')}** · FieldTrax refreshed: {run.get('fieldtrax_refreshed')} · "
        f"workbook sha256 `{str(run.get('workbook_sha256'))[:12]}…`", "",
        f"**{sev['error']} errors, {sev['warning']} warnings, {sev['info']} info** from {checks.height} checks "
        f"({checks.filter(pl.col('kind') == 'rule').height} rule, {checks.filter(pl.col('kind') == 'contract').height} contract). "
        f"{failing.height} checks have hits.", "",
        "## Scorecard", "",
        *_table(data["scorecard"], ["table", "records", "with_error", "with_error_or_warning", "clean_pct"],
                ["Table", "Records", "With an error", "With an error or warning", "Clean %"]),
        "## Checks with hits", "",
        *_table(failing.sort(pl.col("severity").replace_strict({"error": 0, "warning": 1, "info": 2}, default=3), "check_id"), ["check_id", "severity", "entity", "violations", "previous_violations", "title"],
                ["Check", "Severity", "Entity", "Hits", "Previous run", "Rule"]),
        "## Checks whose hit count moved since the previous run", "",
        *_table(moved, ["check_id", "previous_violations", "violations", "title"], ["Check", "Before", "Now", "Rule"]),
        "## New issues since the previous run", "",
        *_table(data["new_issues"], ["severity", "check_id", "entity_key", "source_tab", "source_row", "message"],
                ["Severity", "Check", "Record", "Tab", "Row", "Message"], limit=60),
        "## Resolved since the previous run", "",
        *_table(data["resolved_issues"], ["severity", "check_id", "entity_key", "source_tab", "source_row", "message"],
                ["Severity", "Check", "Record", "Tab", "Row", "Message"], limit=60),
        "## Row accounting (nothing dropped)", "",
        *_table(data["accounting"], ["sheet_name", "sheet_state", "hidden_cols", "disposition", "n"],
                ["Tab", "State", "Hidden columns", "Disposition", "Rows"]),
        "## FieldTrax syncs", "",
        *_table(_sync_rows(data["syncs"]), ["run_id", "devices_listed", "readings_received", "new_readings", "new_device_versions",
                                            "errors", "requests", "rate_limited", "unavailable", "reauths"]),
    ]
    return "\n".join(lines)


def _sync_rows(syncs: pl.DataFrame) -> pl.DataFrame:
    if syncs.is_empty():
        return syncs
    stats = [json.loads(s) if isinstance(s, str) else (s or {}) for s in syncs["stats"].to_list()]
    return syncs.drop("stats").with_columns(
        *[pl.Series(k, [st.get(k) for st in stats]) for k in ("requests", "rate_limited", "unavailable", "reauths")])


def mdm_report(data: dict) -> str:
    usage: pl.DataFrame = data["mdm_usage"]
    aliases: pl.DataFrame = data["mdm_aliases"]
    coverage: pl.DataFrame = data["mdm_coverage"]
    review = usage.filter(pl.col("needs_confirmation"))
    by_domain = coverage.group_by("domain").agg(pl.col("lines").sum().alias("lines"), pl.col("terms").sum().alias("terms"))
    auto = coverage.filter(~pl.col("basis").is_in(["inferred", "fuzzy", "unmapped"])).group_by("domain").agg(pl.col("lines").sum().alias("auto"))
    summary = by_domain.join(auto, on="domain", how="left").with_columns(
        pl.col("auto").fill_null(0), (100 * pl.col("auto").fill_null(0) / pl.col("lines")).round(1).alias("auto_pct")).sort("domain")
    unused = aliases.filter(~pl.col("seen"), pl.col("basis") != "canonical")
    lines = [
        "# Master data report (internal)", "",
        f"{usage.height} distinct written forms across {summary.height} domains. "
        f"{review.height} need a decision; {unused.height} aliases in mdm/aliases.csv were not seen in this workbook.", "",
        "## Coverage by domain", "",
        *_table(summary, ["domain", "terms", "lines", "auto", "auto_pct"],
                ["Domain", "Written forms", "Lines", "Lines mapped without review", "% without review"]),
        "## Needs a decision (inferred, typo match or unmapped)", "",
        *_table(review, ["domain", "raw_value", "canonical", "basis", "score", "suggestions", "line_count", "source_refs"],
                ["Domain", "Written as", "Mapped to", "Basis", "Score", "Nearest", "Lines", "Where"]),
        "## Everything seen", "",
        *_table(usage, ["domain", "raw_value", "canonical", "basis", "matched_on", "line_count"],
                ["Domain", "Written as", "Canonical", "Basis", "Matched alias", "Lines"]),
        "## Aliases defined but not seen in this workbook", "",
        "Kept on purpose for future spellings (regional words, typos seen elsewhere). Review if the list grows stale.", "",
        *_table(unused, ["domain", "written", "canonical", "basis"], ["Domain", "Alias", "Canonical", "Basis"]),
    ]
    return "\n".join(lines)
