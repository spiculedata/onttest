"""Devices (FieldTrax trackers) and their engine-hour readings.

Built from the device version history and every reading line ever landed in
`raw`, so a device that disappears from the API is kept (is_listed = false) and
readings accumulate across syncs. Values arrive as text and are parsed here, the
same way as workbook cells: anything unreadable becomes null and is reported.

No column depends on *when* the pipeline ran, so an unchanged API gives
identical records.
"""

from __future__ import annotations

import polars as pl

from brackenfield.config import SECONDS_PER_HOUR
from brackenfield.transform.parsing import normalise_rego, normalise_vin

DEVICE_NAME = r"^(?<business>BE|NH) (?<fleet_no>[A-Z]{2}-\d{2})\b\s*(?<suffix>.*)$"
UNIT_TO_HOURS = {"h": 1.0, "s": 1.0 / SECONDS_PER_HOUR}

DEVICE_COLUMNS = [
    "device_id", "name", "machine_id", "link_method", "vin", "vin_raw", "rego", "rego_raw", "unit", "retired_at",
    "retired_on", "name_business_code", "name_fleet_no", "name_suffix", "is_listed", "first_seen_at",
    "last_changed_at", "version_count",
]


def build_devices(versions: pl.DataFrame, machines: pl.DataFrame, register_lines: pl.DataFrame) -> pl.DataFrame:
    """Current version of each device, linked to a machine."""
    history = versions.group_by("device_id").agg(
        pl.col("valid_from").min().alias("first_seen_at"),
        pl.col("valid_from").max().alias("last_changed_at"),
        pl.len().cast(pl.Int32).alias("version_count"),
    )
    name_parts = pl.col("name").str.extract_groups(DEVICE_NAME)
    current = (
        versions.sort("valid_from")
        .group_by("device_id")
        .last()
        .join(history, on="device_id")
        .with_columns(
            pl.col("vin").alias("vin_raw"),
            pl.col("rego").alias("rego_raw"),
            normalise_vin("vin").alias("vin"),
            normalise_rego("rego").alias("rego"),
            pl.col("retired_at").str.to_date(strict=False).alias("retired_on"),
            name_parts.struct.field("business").alias("name_business_code"),
            name_parts.struct.field("fleet_no").alias("name_fleet_no"),
            pl.when(name_parts.struct.field("suffix") != "").then(name_parts.struct.field("suffix")).alias("name_suffix"),
        )
    )
    return _link_devices(current, machines, register_lines).select(DEVICE_COLUMNS).sort("device_id")


def _link_devices(devices: pl.DataFrame, machines: pl.DataFrame, register_lines: pl.DataFrame) -> pl.DataFrame:
    """Link by VIN, then rego, then business + fleet number on the device name."""
    by_vin = register_lines.filter(pl.col("vin").is_not_null()).group_by("vin").agg(pl.col("machine_id").first().alias("m_vin"))
    by_rego = register_lines.filter(pl.col("rego").is_not_null()).group_by("rego").agg(pl.col("machine_id").first().alias("m_rego"))
    by_name = machines.select(
        pl.col("business_code").alias("name_business_code"),
        pl.col("fleet_no").alias("name_fleet_no"),
        pl.col("machine_id").alias("m_name"),
    )
    linked = (
        devices.join(by_vin, on="vin", how="left")
        .join(by_rego, on="rego", how="left")
        .join(by_name, on=["name_business_code", "name_fleet_no"], how="left")
    )
    return linked.with_columns(
        pl.coalesce("m_vin", "m_rego", "m_name").alias("machine_id"),
        pl.when(pl.col("m_vin").is_not_null()).then(pl.lit("vin"))
        .when(pl.col("m_rego").is_not_null()).then(pl.lit("rego"))
        .when(pl.col("m_name").is_not_null()).then(pl.lit("name"))
        .alias("link_method"),
    ).drop("m_vin", "m_rego", "m_name")


def parse_reading_time(column: str) -> pl.Expr:
    """ISO-8601 with "Z" or an explicit offset, normalised to UTC. Anything else is null."""
    text = pl.col(column).str.strip_chars().str.replace(r"Z$", "+00:00")
    return text.str.to_datetime("%Y-%m-%dT%H:%M:%S%z", time_zone="UTC", strict=False)


def _parse_lines(raw_readings: pl.DataFrame) -> pl.DataFrame:
    value = pl.col("value_raw").str.strip_chars().cast(pl.Float64, strict=False)
    unit = pl.col("unit_raw").str.strip_chars().str.to_lowercase()
    return raw_readings.rename({"time": "time_raw", "value": "value_raw", "unit": "unit_raw"}).with_columns(
        parse_reading_time("time_raw").alias("time_utc"),
        pl.when(pl.col("time_raw").str.ends_with("Z")).then(pl.lit("Z")).otherwise(pl.col("time_raw").str.slice(-6)).alias("time_offset"),
        value.alias("value"),
        (value * unit.replace_strict(UNIT_TO_HOURS, default=None, return_dtype=pl.Float64)).alias("engine_hours"),
    )


def build_readings(raw_readings: pl.DataFrame, devices: pl.DataFrame) -> pl.DataFrame:
    """One row per (device, metric, instant); unreadable lines kept with their raw text.

    Lines whose time cannot be read have no instant to de-duplicate on, so each
    stays as its own row (time_utc null) for the checks to report.
    """
    parsed = _parse_lines(raw_readings)
    instant = ["device_id", "metric", "time_utc"]
    timed = parsed.filter(pl.col("time_utc").is_not_null())
    deduped = (
        timed.sort("device_id", "time_utc", "first_seen_run", "payload")
        .group_by(instant, maintain_order=True)
        .agg(
            pl.all().exclude(instant).first(),
            pl.len().cast(pl.Int32).alias("source_line_count"),
            pl.col("engine_hours").round(3).n_unique().cast(pl.Int32).alias("distinct_values_at_instant"),
        )
    )
    untimed = parsed.filter(pl.col("time_utc").is_null()).with_columns(
        pl.lit(1, dtype=pl.Int32).alias("source_line_count"), pl.lit(1, dtype=pl.Int32).alias("distinct_values_at_instant"))
    rows = pl.concat([deduped, untimed.select(deduped.columns)]).join(
        devices.select("device_id", "machine_id", "retired_on"), on="device_id", how="left")
    return _with_deltas(rows).select(
        "device_id", "machine_id", "metric", "time_utc", "time_raw", "time_offset", "engine_hours", "value",
        "value_raw", "unit_raw", "hours_delta", "elapsed_hours", "is_after_retirement", "source_line_count",
        "distinct_values_at_instant", "first_seen_run", "payload",
    ).sort("device_id", "metric", "time_utc", "payload", nulls_last=True)


def _with_deltas(rows: pl.DataFrame) -> pl.DataFrame:
    """Change since the previous *readable* reading of the same device; unreadable rows get nulls."""
    by_device = ["device_id", "metric"]
    readable = (pl.col("time_utc").is_not_null() & pl.col("engine_hours").is_not_null())
    valid = rows.filter(readable).sort("device_id", "metric", "time_utc").with_columns(
        (pl.col("engine_hours") - pl.col("engine_hours").shift(1).over(by_device)).alias("hours_delta"),
        ((pl.col("time_utc") - pl.col("time_utc").shift(1).over(by_device)).dt.total_seconds() / SECONDS_PER_HOUR).alias("elapsed_hours"),
    )
    rest = rows.filter(~readable).with_columns(
        pl.lit(None, dtype=pl.Float64).alias("hours_delta"), pl.lit(None, dtype=pl.Float64).alias("elapsed_hours"))
    return pl.concat([valid, rest.select(valid.columns)]).with_columns(
        (pl.col("time_utc").dt.date() > pl.col("retired_on")).fill_null(False).alias("is_after_retirement"))
