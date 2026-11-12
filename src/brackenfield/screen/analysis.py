"""Priya's question: which hires could I end right now because we own something idle that
would do the job, and what would that save me a day?

The rules for the numbers (as given):
  - As of 31 October 2026, end of day, AEST. The answer uses the FieldTrax data as it stood
    before /__advance; only the "after advance" view uses the data after it.
  - Open hire: READ ME rules (struck = cancelled, Start TBA = not started, Off-hire blank /
    ongoing / TBA = still on), with a start on or before 31 Oct and an off-hire after it, or none.
    Rates converted to dollars per day excluding GST.
  - Idle: the register reads Available or Yard, and FieldTrax confirms under 1.0 engine hour
    between 18 Oct 00:00 and 31 Oct 23:59 AEST. Hours run = the sum of positive increases between
    consecutive readings, across all of the machine's devices. No device = unconfirmed, never idle.
  - Replaceable: an idle machine can replace one open hire of the same category on a project in
    the same state as its depot. Pairs chosen to save the most.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import polars as pl

from brackenfield.config import GST_RATE
from brackenfield.timewindow import AEST, idle_window  # noqa: F401 - re-exported for the screen

IDLE_MAX_HOURS = 1.0  # strictly under
IDLE_STATUSES = ("Available", "Yard")  # READ ME: the same thing; shown as "Available" on the screen
STATUS_LABEL = "Available"


@dataclass(frozen=True)
class Inputs:
    as_of: date
    hires: pl.DataFrame
    projects: pl.DataFrame
    machines: pl.DataFrame
    sites: pl.DataFrame
    devices: pl.DataFrame
    readings: pl.DataFrame
    issues: pl.DataFrame
    organizations: pl.DataFrame


def machine_evidence(inp: Inputs, machine_lines: pl.DataFrame) -> pl.DataFrame:
    """Machines whose register line reads Available or Yard, with FieldTrax hours in the window."""
    start, end = idle_window(inp.as_of)
    # The machine's own current line (not an old "Transferred to" line) must read Available or Yard.
    current = machine_lines.select("source_tab", "source_row", "status_raw")
    machines = (
        inp.machines.join(current, on=["source_tab", "source_row"], how="left")
        .filter(pl.col("status_raw").is_in(IDLE_STATUSES))
        .join(inp.sites.select("site_id", pl.col("name").alias("depot"), "state"), on="site_id", how="left")
    )
    devices = inp.devices.filter(pl.col("machine_id").is_not_null()).group_by("machine_id").agg(
        pl.col("device_id").sort().str.join(", ").alias("device_ids"))
    in_window = inp.readings.filter(
        pl.col("machine_id").is_not_null(), pl.col("engine_hours").is_not_null(),
        pl.col("time_utc") >= start, pl.col("time_utc") <= end,
    ).sort("device_id", "time_utc")
    hours = in_window.with_columns(pl.col("engine_hours").diff().over("device_id").alias("step")).group_by("machine_id").agg(
        pl.col("step").filter(pl.col("step") > 0).sum().alias("hours_run"),
        pl.len().alias("readings_in_window"),
        pl.col("time_utc").min().alias("first_reading"),
        pl.col("time_utc").max().alias("last_reading"),
    )
    out = machines.join(devices, on="machine_id", how="left").join(hours, on="machine_id", how="left")
    return out.with_columns(_idle_status().alias("idle_status"), _idle_reason().alias("idle_reason"))


def _idle_status() -> pl.Expr:
    return (
        pl.when(pl.col("device_ids").is_null()).then(pl.lit("unconfirmed"))
        .when(pl.col("readings_in_window").fill_null(0) < 2).then(pl.lit("unconfirmed"))
        .when(pl.col("hours_run") < IDLE_MAX_HOURS).then(pl.lit("confirmed"))
        .otherwise(pl.lit("working"))
    )


def _idle_reason() -> pl.Expr:
    hours = pl.col("hours_run").fill_null(0).round(2).cast(pl.String)
    return (
        pl.when(pl.col("device_ids").is_null()).then(pl.lit("Available, but no FieldTrax device to confirm it is idle."))
        .when(pl.col("readings_in_window").fill_null(0) < 2).then(pl.lit("Available, but its device has no readings 18–31 Oct."))
        .when(pl.col("hours_run") < IDLE_MAX_HOURS).then(pl.format("Available; {} h run 18–31 Oct.", hours))
        .otherwise(pl.format("Available, but {} h run 18–31 Oct.", hours))
    )


def on_hire(inp: Inputs) -> pl.DataFrame:
    return (
        inp.hires.filter(pl.col("status") == "on_hire")
        .join(inp.projects.select("project_code", pl.col("name").alias("project_name"), pl.col("state").alias("project_state")),
              on="project_code", how="left")
        .sort("day_rate_ex_gst", "source_row", descending=[True, False])
    )


def match(hires: pl.DataFrame, machines: pl.DataFrame) -> dict[int, str]:
    """source_row -> machine_id, choosing the pairs that save the most.

    Within one (category, state) any idle machine can replace any open hire, so giving the
    k idle machines to the k dearest hires is the maximum saving. Confirmed-idle machines are
    placed first; unconfirmed ones then take the next-dearest hires, shown separately.
    """
    pool = machines.filter(pl.col("idle_status") != "working").sort(
        pl.col("idle_status") != "confirmed", "business_code", "fleet_no")
    used: set[str] = set()
    out: dict[int, str] = {}
    for hire in hires.filter(~pl.col("is_duplicate_line")).iter_rows(named=True):
        for m in pool.iter_rows(named=True):
            if m["machine_id"] in used or m["category"] != hire["category"] or m["state"] != hire["project_state"]:
                continue
            used.add(m["machine_id"])
            out[hire["source_row"]] = m["machine_id"]
            break
    return out


def working_days_until(start: date, end: date | None) -> int | None:
    """Weekdays after `start` up to and including `end` (READ ME: a week is 5 working days)."""
    if end is None or end <= start:
        return None
    days = (end - start).days
    return sum(1 for i in range(1, days + 1) if (start + timedelta(days=i)).weekday() < 5)


def issues_for(issues: pl.DataFrame, tab: str, row: int | None, keys: list[str]) -> list[dict]:
    hits = issues.filter(
        pl.col("for_priya")
        & (((pl.col("source_tab") == tab) & (pl.col("source_row") == row)) | pl.col("entity_key").is_in(keys))
    )
    return hits.select("check_id", "severity", "check_title", "message").unique().sort("check_id").to_dicts()


def ex_to_inc(amount: float | None) -> float | None:
    return None if amount is None else round(amount * (1 + GST_RATE), 2)
