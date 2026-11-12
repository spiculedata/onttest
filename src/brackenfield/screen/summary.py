"""answers.json: the headline counts in the brief's skeleton, one flat object.

Everything telemetry-related is "before /__advance" (the before_advance sync) unless it sits under
`after_advance`. Money totals are summed from the full-precision day rates in clean.hires and
rounded once.
"""

from __future__ import annotations

import polars as pl

GONE_STATUSES = ("disposed",)  # "Sold" and "Disposed" both resolve to disposed
TRANSFER_STATUS = "transferred"


def _cents(x: float) -> str:
    return f"{x:.2f}"


def _whole(x: float) -> int | float:
    return int(round(x)) if abs(x - round(x)) < 0.005 else round(x, 2)


def _machines(machines: pl.DataFrame, lines: pl.DataFrame, be_typed_total: float | None) -> dict:
    disposed = machines.filter(pl.col("status").is_in(GONE_STATUSES)).height
    be_lines = lines.filter(pl.col("business_code") == "BE")["capital_cost_aud"].sum()
    return {
        "distinct_machines": machines.height,
        "owned_current": machines.height - disposed,
        "owned_disposed": disposed,
        "transfer_rows": lines.filter(pl.col("status") == TRANSFER_STATUS).height,
        "be_total_discrepancy": None if be_typed_total is None else _whole(be_lines - be_typed_total),
    }


def _hires(hires: pl.DataFrame) -> dict:
    distinct = hires.filter(~pl.col("is_duplicate_line"))
    open_ = distinct.filter(pl.col("status") == "on_hire")
    duplicates = hires.filter(pl.col("is_duplicate_line"))["hire_no"].unique().sort().to_list()
    return {
        "hire_rows_distinct": hires["hire_no"].n_unique(),
        "cancelled": distinct.filter(pl.col("is_cancelled")).height,
        "duplicate_hire": ", ".join(duplicates),
        "open_hires": open_.height,
        "open_hire_run_rate_ex_gst_per_day": _cents(open_.select(pl.col("day_rate_ex_gst").sum()).item()),
    }


def _telemetry(devices: pl.DataFrame, readings: pl.DataFrame, machines: pl.DataFrame) -> dict:
    tracked = devices["machine_id"].drop_nulls().unique()
    available = machines.filter(pl.col("status") == "available")
    return {
        "devices_total": devices.height,
        "devices_retired": devices.filter(pl.col("retired_at").is_not_null()).height,
        "devices_unmatched": devices.filter(pl.col("machine_id").is_null()).height,
        "readings_distinct": readings.select("device_id", "time_utc").n_unique(),
        "available_no_telemetry": available.filter(~pl.col("machine_id").is_in(tracked.implode())).height,
    }


def _answer(world: dict, hires: pl.DataFrame) -> dict:
    confirmed = [h["hire_no"] for h in world["hires"] if h["outcome"] == "end_confirmed"]
    saving = hires.filter(~pl.col("is_duplicate_line"), pl.col("hire_no").is_in(confirmed)).select(pl.col("day_rate_ex_gst").sum()).item()
    return {
        "idle_confirmed": sum(m["idle_status"] == "confirmed" for m in world["machines"]),
        "replaceable_hires": len(confirmed),
        "saving_ex_gst_per_day": _cents(saving or 0.0),
    }


def _after_advance(changes: list[dict], readings_before: pl.DataFrame, readings_after: pl.DataFrame) -> dict:
    count = lambda kind: sum(c["change"] == kind for c in changes)  # noqa: E731
    key = ["device_id", "time_utc"]
    return {
        "devices_added": count("added"),
        "devices_gone": count("gone"),
        "devices_renamed": count("renamed"),
        "readings_added": readings_after.select(key).unique().join(readings_before.select(key).unique(), on=key, how="anti").height,
    }


def skeleton(tables: dict[str, pl.DataFrame], be_typed_total: float | None, before, after, before_world: dict,
             device_changes: list[dict]) -> dict:
    """The brief's answers.json. `before`/`after` are analysis.Inputs at the two syncs."""
    return {
        **_machines(tables["machines"], tables["machine_lines"], be_typed_total),
        **_hires(tables["hires"]),
        **_telemetry(before.devices, before.readings, tables["machines"]),
        **_answer(before_world, tables["hires"]),
        "after_advance": _after_advance(device_changes, before.readings, after.readings),
    }
