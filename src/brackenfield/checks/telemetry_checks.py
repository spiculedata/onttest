"""Checks on FieldTrax devices and readings, plus vocabulary inferences."""

from __future__ import annotations

import polars as pl

from brackenfield.checks.registry import Tables, check, no_violations, violations
from brackenfield.timewindow import idle_window

FIELDTRAX = "FieldTrax"


def _device_ref(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns(pl.lit(FIELDTRAX).alias("source_tab"), pl.lit(None, dtype=pl.Int32).alias("source_row"))


@check(
    "DV001", "FieldTrax data was refreshed this run", "device", "warning",
    "If the API could not be reached, devices and readings come from the last successful snapshot.",
    audience="internal",
)
def fieldtrax_refreshed(t: Tables) -> pl.DataFrame:
    if t.fieldtrax_refreshed:
        return no_violations()
    frame = _device_ref(pl.DataFrame({"k": ["fieldtrax"]}))
    note = "No FieldTrax snapshot at all" if t.devices.is_empty() else "Using the previous FieldTrax snapshot"
    return violations(frame, key="k", field=None, raw=None, message=note)


@check(
    "DV002", "Every device is linked to a register machine", "device", "warning",
    "Linked by VIN, then rego, then business + fleet number in the device name.",
)
def device_unlinked(t: Tables) -> pl.DataFrame:
    found = _device_ref(t.devices.filter(pl.col("machine_id").is_null()))
    return violations(found, key="device_id", field=None, raw="name", message="Device matches no machine on the register")


@check(
    "DV003", "Device VIN and rego agree with the register", "device", "error",
    "A device linked by rego whose VIN differs (or the reverse) points at the wrong machine or a typo.",
    audience="internal",
)
def device_identity_disagrees(t: Tables) -> pl.DataFrame:
    reg = t.machines.select("machine_id", pl.col("vin").alias("m_vin"), pl.col("rego").alias("m_rego"))
    linked = t.devices.join(reg, on="machine_id", how="inner")
    found = _device_ref(linked.filter(
        (pl.col("vin").is_not_null() & pl.col("m_vin").is_not_null() & (pl.col("vin") != pl.col("m_vin")))
        | (pl.col("rego").is_not_null() & (pl.col("rego") != pl.col("m_rego")))
    ))
    return violations(found, key="device_id", field="vin/rego", raw=pl.concat_str("vin_raw", "rego_raw", separator=" / ", ignore_nulls=True),
                      message=pl.format("Register has {} / {}", pl.col("m_vin"), pl.col("m_rego")))


@check(
    "DV004", "Device name agrees with the linked machine", "device", "warning",
    "The name carries business and fleet number ('BE EX-01 Komatsu'); after a transfer it may be stale.",
    audience="internal",
)
def device_name_disagrees(t: Tables) -> pl.DataFrame:
    reg = t.machines.select("machine_id", "business_code", "fleet_no")
    linked = t.devices.join(reg, on="machine_id", how="inner")
    found = _device_ref(linked.filter(
        (pl.col("name_business_code") != pl.col("business_code")) | (pl.col("name_fleet_no") != pl.col("fleet_no"))
        | pl.col("name_suffix").str.contains(r"(?i)reassigned").fill_null(False)
    ))
    return violations(found, key="device_id", field="name", raw="name",
                      message=pl.format("Linked to {} {} on the register", pl.col("business_code"), pl.col("fleet_no")))


@check(
    "DV005", "A machine has at most one active tracker", "device", "warning",
    "Replaced trackers should carry a retired_at date.",
    audience="internal",
)
def multiple_active(t: Tables) -> pl.DataFrame:
    active = t.devices.filter(pl.col("machine_id").is_not_null(), pl.col("retired_on").is_null())
    found = _device_ref(active.filter(pl.len().over("machine_id") > 1))
    return violations(found, key="device_id", field=None, raw="name",
                      message=pl.format("More than one active device on {}", pl.col("machine_id")))


@check(
    "DV006", "Replaced trackers are recorded as retired", "device", "info",
    "Old units with retired_at are kept; their readings stay linked to the machine.",
    audience="internal",
)
def retired_devices(t: Tables) -> pl.DataFrame:
    found = _device_ref(t.devices.filter(pl.col("retired_on").is_not_null()))
    return violations(found, key="device_id", field="retired_at", raw="retired_at", message="Retired tracker kept")


@check(
    "DV007", "Devices reporting in seconds are converted to hours", "device", "info",
    "Some trackers report engine time in seconds (unit 's'); divided by 3600.",
    audience="internal",
)
def seconds_unit(t: Tables) -> pl.DataFrame:
    found = _device_ref(t.devices.filter(pl.col("unit") == "s"))
    return violations(found, key="device_id", field="unit", raw="unit", message="Readings converted from seconds")


@check(
    "DV008", "Devices are still listed by FieldTrax", "device", "warning",
    "A device seen in an earlier snapshot but missing from the latest is kept and flagged.",
    audience="internal",
)
def device_gone(t: Tables) -> pl.DataFrame:
    found = _device_ref(t.devices.filter(~pl.col("is_listed")))
    return violations(found, key="device_id", field=None, raw="name", message=pl.format(
        "Not in the FieldTrax device list since {} UTC; kept with its readings",
        pl.col("last_changed_at").dt.convert_time_zone("UTC").dt.strftime("%Y-%m-%d %H:%M")))


def _sync_errors(t: Tables, scopes: tuple[str, ...]) -> pl.DataFrame:
    return _device_ref(t.fieldtrax_errors.filter(pl.col("scope").is_in(scopes)))


@check(
    "DV009", "Every device item from FieldTrax could be stored", "device", "error",
    "A device item with no id (or a repeated id, or not an object) cannot be keyed. Its JSON is kept in "
    "meta.fieldtrax_sync_errors.",
    audience="internal",
)
def device_items_rejected(t: Tables) -> pl.DataFrame:
    found = _sync_errors(t, ("device",))
    return violations(found, key=pl.coalesce("device_id", pl.lit("(no id)")), field=None, raw="payload", message=pl.col("error"))


@check(
    "DV010", "Every device's readings were fetched", "device", "warning",
    "If a device's readings still fail after retries, the other devices carry on and this device keeps its "
    "earlier readings. Malformed reading items are kept in meta.fieldtrax_sync_errors.",
    audience="internal",
)
def readings_fetch_failed(t: Tables) -> pl.DataFrame:
    found = _sync_errors(t, ("readings", "reading"))
    return violations(found, key="device_id", field=None, raw="payload", message=pl.col("error"))


@check(
    "DV011", "FieldTrax knows the readings endpoint for every device", "device", "info",
    "A 404 on a device's readings means FieldTrax has no readings for it.",
    audience="internal",
)
def readings_not_found(t: Tables) -> pl.DataFrame:
    found = _sync_errors(t, ("readings_not_found",))
    return violations(found, key="device_id", field=None, raw=None, message="No readings resource (HTTP 404)")


@check(
    "RD007", "Each reading has a readable time, a numeric value and a known unit", "reading", "error",
    "API values are stored as received and parsed like workbook cells; unreadable ones load as null.",
    audience="internal",
)
def unreadable_readings(t: Tables) -> pl.DataFrame:
    reason = (
        pl.when(pl.col("time_utc").is_null()).then(pl.format("time {} is not ISO-8601 with an offset", pl.col("time_raw")))
        .when(pl.col("value").is_null()).then(pl.format("value {} is not a number", pl.col("value_raw")))
        .when(pl.col("engine_hours").is_null()).then(pl.format("unit {} is not h or s", pl.col("unit_raw")))
        .when(pl.col("metric").ne_missing("engine_hours")).then(pl.format("unknown metric {}", pl.col("metric").fill_null("(none)")))
    )
    found = _device_ref(t.readings.filter(reason.is_not_null()).with_columns(reason.alias("reason")))
    return violations(found, key="device_id", field="reading", raw="payload", message=pl.col("reason"))


@check(
    "RD001", "Repeated readings at the same instant are kept once", "reading", "info",
    "The same instant can arrive twice (e.g. 'Z' and '+10:00' forms). Kept once; count in source_line_count.",
    audience="internal",
)
def duplicate_instants(t: Tables) -> pl.DataFrame:
    found = _device_ref(t.readings.filter(pl.col("source_line_count") > 1, pl.col("distinct_values_at_instant") == 1))
    return violations(found, key="device_id", field="time", raw="time_raw", message=pl.format("{} copies at {} UTC", pl.col("source_line_count"), pl.col("time_utc").dt.strftime("%Y-%m-%d %H:%M")))


@check(
    "RD002", "Readings at the same instant agree", "reading", "error",
    "Two different values for one device at one instant cannot both be right.",
    audience="internal",
)
def conflicting_instants(t: Tables) -> pl.DataFrame:
    found = _device_ref(t.readings.filter(pl.col("distinct_values_at_instant") > 1))
    return violations(found, key="device_id", field="value", raw="time_raw", message=pl.format("Conflicting values at {} UTC", pl.col("time_utc").dt.strftime("%Y-%m-%d %H:%M")))


@check(
    "RD003", "Engine hours never go backwards", "reading", "error",
    "Engine hours are a cumulative meter.",
    audience="internal",
)
def hours_decrease(t: Tables) -> pl.DataFrame:
    by_device = ["device_id", "metric"]
    with_next = t.readings.with_columns(
        pl.col("engine_hours").shift(1).over(by_device).alias("before"),
        pl.col("engine_hours").shift(-1).over(by_device).alias("after"),
    )
    found = _device_ref(with_next.filter(pl.col("hours_delta") < -0.001))
    kind = (
        pl.when(pl.col("after").is_null()).then(pl.lit("last reading so far; cannot tell reset from glitch"))
        .when(pl.col("after") >= pl.col("before")).then(pl.lit("one-off bad reading; the next one is back on the old count"))
        .otherwise(pl.lit("meter reset or tracker swap; later readings continue from the new value"))
    )
    return violations(found, key="device_id", field="engine_hours", raw="value_raw", message=pl.format(
        "{} h -> {} h at {} UTC: {}", pl.col("before").round(1), pl.col("engine_hours").round(1),
        pl.col("time_utc").dt.strftime("%Y-%m-%d %H:%M"), kind))


@check(
    "RD004", "Engine hours do not grow faster than the clock", "reading", "error",
    "An increase larger than the elapsed time between readings is physically impossible.",
    audience="internal",
)
def hours_faster_than_clock(t: Tables) -> pl.DataFrame:
    with_prev = t.readings.with_columns(
        (pl.col("first_seen_run").shift(1).over("device_id", "metric") > pl.col("first_seen_run")).fill_null(False).alias("prev_late")
    )
    found = _device_ref(with_prev.filter(pl.col("hours_delta") > pl.col("elapsed_hours") + 0.01))
    late = pl.when(pl.col("prev_late")).then(pl.lit(" (the reading before it arrived late, in a later FieldTrax pull)")).otherwise(pl.lit(""))
    return violations(found, key="device_id", field="engine_hours", raw="value_raw", message=pl.format(
        "+{} h in {} h elapsed at {} UTC{}", pl.col("hours_delta").round(2), pl.col("elapsed_hours").round(2),
        pl.col("time_utc").dt.strftime("%Y-%m-%d %H:%M"), late))


@check(
    "RD005", "No readings after a tracker was retired", "reading", "warning",
    "A retired tracker should stop reporting.",
    audience="internal",
)
def after_retirement(t: Tables) -> pl.DataFrame:
    found = _device_ref(t.readings.filter(pl.col("is_after_retirement")))
    return violations(found, key="device_id", field="time", raw="time_raw", message="Reading after retired_at")


@check(
    "RD006", "Reading timestamps with an offset are normalised to UTC", "reading", "info",
    "FieldTrax mixes 'Z' and '+10:00' offsets. One summary line per device.",
    audience="internal",
)
def offsets_normalised(t: Tables) -> pl.DataFrame:
    summary = t.readings.filter(pl.col("time_offset") != "Z").group_by("device_id").agg(pl.len().alias("n"), pl.col("time_offset").unique().sort().str.join(",").alias("offsets"))
    return violations(_device_ref(summary), key="device_id", field="time", raw="offsets", message=pl.format("{} readings converted to UTC", pl.col("n")))


@check(
    "VC001", "Term mappings that are judgement calls or typo matches are confirmed", "vocabulary", "warning",
    "From mdm.term_usage: words mapped by an 'inferred' alias (e.g. 'On job', 'Repairs', 'Hire Well') or by a "
    "typo match ('fuzzy'). The value is applied; Priya confirms or corrects it in mdm/aliases.csv. Listed once per term.",
)
def inferred_vocab(t: Tables) -> pl.DataFrame:
    found = t.mdm_usage.filter(pl.col("canonical").is_not_null(), pl.col("needs_confirmation")).with_columns(
        pl.col("source_refs").str.split(", ").list.first().alias("first_ref"))
    found = found.with_columns(
        pl.col("first_ref").str.split("!").list.first().alias("source_tab"),
        pl.col("first_ref").str.split("!").list.last().cast(pl.Int32, strict=False).alias("source_row"),
    )
    how = pl.when(pl.col("basis") == "fuzzy").then(pl.format("typo match ({}) on '{}'", pl.col("score"), pl.col("matched_on"))).otherwise(pl.lit("inferred alias"))
    return violations(found, key="raw_value", field="domain", raw="raw_value", message=pl.format(
        "'{}' read as {} '{}' by {} on {} line(s). Please confirm.", pl.col("raw_value"), pl.col("domain"),
        pl.col("canonical"), how, pl.col("line_count")))


@check(
    "VC002", "Every coded value maps to a master value", "vocabulary", "error",
    "A word that matches no canonical value or alias, even allowing for typos, is left blank rather than guessed. "
    "Add it to mdm/aliases.csv.",
)
def unmapped_terms(t: Tables) -> pl.DataFrame:
    found = t.mdm_usage.filter(pl.col("canonical").is_null()).with_columns(
        pl.col("source_refs").str.split(", ").list.first().alias("first_ref"))
    found = found.with_columns(
        pl.col("first_ref").str.split("!").list.first().alias("source_tab"),
        pl.col("first_ref").str.split("!").list.last().cast(pl.Int32, strict=False).alias("source_row"),
    )
    return violations(found, key="raw_value", field="domain", raw="raw_value", message=pl.format(
        "'{}' is not a known {} on {} line(s). Nearest: {}", pl.col("raw_value"), pl.col("domain"),
        pl.col("line_count"), pl.col("suggestions").fill_null("none")))


@check(
    "DV012", "A tracker that matches no machine is not running", "device", "warning",
    "A tracker that logs engine hours is fitted to something working. If it is on an untracked machine marked "
    "Available, that machine is not idle.",
)
def unmatched_tracker_running(t: Tables) -> pl.DataFrame:
    start, end = idle_window(t.as_of)
    unmatched = t.devices.filter(pl.col("machine_id").is_null()).select("device_id", "name")
    window = t.readings.join(unmatched, on="device_id", how="inner").filter(
        pl.col("time_utc") >= start, pl.col("time_utc") <= end, pl.col("engine_hours").is_not_null())
    running = window.sort("device_id", "time_utc").with_columns(pl.col("engine_hours").diff().over("device_id").alias("step")).group_by(
        "device_id", "name").agg(pl.col("step").filter(pl.col("step") > 0).sum().alias("hours"), pl.col("time_utc").min().alias("first"))
    found = _device_ref(running.filter(pl.col("hours") >= 1.0))
    return violations(found, key="device_id", field="engine_hours", raw="name", message=pl.format(
        "{} ran {} h between 18 and 31 Oct (reporting since {}). It is fitted to a machine that is working.",
        pl.col("name"), pl.col("hours").round(1), pl.col("first").dt.convert_time_zone("Australia/Brisbane").dt.strftime("%-d %b")))
