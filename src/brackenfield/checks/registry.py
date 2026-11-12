"""Check registry: every rule a bad row can fail, with its id, severity and rationale.

Severity:
  error    the value is wrong or unusable as written. Goes to Priya.
  warning  the value is readable but suspicious. Goes to Priya.
  info     handled automatically by a documented rule. Logged, not for Priya.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

import polars as pl

SEVERITIES = ("error", "warning", "info")
AUDIENCES = ("priya", "internal")

VIOLATION_SCHEMA = {
    "entity_key": pl.String,
    "source_tab": pl.String,
    "source_row": pl.Int32,
    "field": pl.String,
    "raw_value": pl.String,
    "message": pl.String,
}

ISSUE_SCHEMA = {
    "check_id": pl.String,
    "check_title": pl.String,
    "entity": pl.String,
    "severity": pl.String,
    "for_priya": pl.Boolean,
    **VIOLATION_SCHEMA,
}


@dataclass(frozen=True)
class Tables:
    as_of: date
    sheets: pl.DataFrame
    cells: pl.DataFrame
    dispositions: pl.DataFrame
    organizations: pl.DataFrame
    org_aliases: pl.DataFrame
    sites: pl.DataFrame
    projects: pl.DataFrame
    machine_lines: pl.DataFrame
    machines: pl.DataFrame
    hires: pl.DataFrame
    rate_card: pl.DataFrame
    devices: pl.DataFrame
    readings: pl.DataFrame
    fieldtrax_errors: pl.DataFrame
    mdm_usage: pl.DataFrame
    fieldtrax_refreshed: bool


@dataclass(frozen=True)
class Check:
    check_id: str
    title: str
    entity: str
    severity: str
    rationale: str
    fn: Callable[[Tables], pl.DataFrame] = field(repr=False)
    audience: str = "priya"  # "priya" or "internal" (data team only, however severe)

    @property
    def for_priya(self) -> bool:
        return self.audience == "priya" and self.severity in ("error", "warning")


REGISTRY: dict[str, Check] = {}


def check(check_id: str, title: str, entity: str, severity: str, rationale: str, audience: str = "priya"):
    """Register a rule. The function returns violations shaped like VIOLATION_SCHEMA."""
    if severity not in SEVERITIES:
        raise ValueError(f"{check_id}: unknown severity {severity!r}")

    def register(fn: Callable[[Tables], pl.DataFrame]) -> Callable[[Tables], pl.DataFrame]:
        if check_id in REGISTRY:
            raise ValueError(f"Duplicate check id {check_id}")
        if audience not in AUDIENCES:
            raise ValueError(f"{check_id}: unknown audience {audience!r}")
        REGISTRY[check_id] = Check(check_id, title, entity, severity, rationale, fn, audience)
        return fn

    return register


def violations(
    frame: pl.DataFrame,
    *,
    key: str | pl.Expr,
    field: str | None,
    raw: str | pl.Expr | None,
    message: str | pl.Expr,
) -> pl.DataFrame:
    """Shape matching rows of a clean table into the standard violation frame."""
    as_expr = lambda v: pl.col(v) if isinstance(v, str) else v  # noqa: E731
    text = lambda v: pl.lit(None, dtype=pl.String) if v is None else as_expr(v).cast(pl.String)  # noqa: E731
    return frame.select(
        as_expr(key).cast(pl.String).alias("entity_key"),
        pl.col("source_tab").cast(pl.String),
        pl.col("source_row").cast(pl.Int32),
        pl.lit(field, dtype=pl.String).alias("field"),
        text(raw).alias("raw_value"),
        (pl.lit(message) if isinstance(message, str) else message).cast(pl.String).alias("message"),
    )


def no_violations() -> pl.DataFrame:
    return pl.DataFrame(schema=VIOLATION_SCHEMA)


def run_rule_checks(tables: Tables) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Run every registered rule. Returns (issues, per-check results)."""
    issue_frames, results = [], []
    for chk in REGISTRY.values():
        found = chk.fn(tables).cast(VIOLATION_SCHEMA)  # type: ignore[arg-type]
        results.append({"check_id": chk.check_id, "violations": found.height})
        issue_frames.append(
            found.with_columns(
                pl.lit(chk.check_id).alias("check_id"),
                pl.lit(chk.title).alias("check_title"),
                pl.lit(chk.entity).alias("entity"),
                pl.lit(chk.severity).alias("severity"),
                pl.lit(chk.for_priya).alias("for_priya"),
            ).select(list(ISSUE_SCHEMA))
        )
    issues = pl.concat(issue_frames) if issue_frames else pl.DataFrame(schema=ISSUE_SCHEMA)
    return issues, pl.DataFrame(results, schema={"check_id": pl.String, "violations": pl.Int64})


def catalogue() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "check_id": c.check_id,
                "kind": "rule",
                "entity": c.entity,
                "severity": c.severity,
                "for_priya": c.for_priya,
                "audience": c.audience,
                "title": c.title,
                "rationale": c.rationale,
            }
            for c in REGISTRY.values()
        ]
    )
