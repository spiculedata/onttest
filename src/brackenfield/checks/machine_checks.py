"""Checks on the plant sheets (BE Plant, NH Fleet) and the de-duplicated machines."""

from __future__ import annotations

import polars as pl

from brackenfield.checks.registry import Tables, check, no_violations, violations

ACTIVE_STATUSES = ("available", "on_project", "workshop")


def _current_lines(t: Tables) -> pl.DataFrame:
    return t.machine_lines.filter(pl.col("status").ne_missing("transferred"))


def _transfer_lines(t: Tables) -> pl.DataFrame:
    return t.machine_lines.filter(pl.col("status") == "transferred")


@check(
    "MC001", "Fleet number is in the sheet's XX-NN format", "machine", "error",
    "Both plant sheets number live machines as two letters, a dash and two digits.",
)
def fleet_no_format(t: Tables) -> pl.DataFrame:
    found = _current_lines(t).filter(~pl.col("fleet_no").str.contains(r"^[A-Z]{2}-\d{2}$").fill_null(False))
    return violations(found, key="fleet_no", field="fleet_no", raw="fleet_no", message="Fleet number not in XX-NN format")


@check(
    "MC002", "Fleet number is unique within its business", "machine", "error",
    "READ ME: fleet numbers repeat across businesses (EX-01 at BE is not EX-01 at NH) but not within one.",
)
def fleet_no_unique(t: Tables) -> pl.DataFrame:
    found = _current_lines(t).filter(pl.len().over("business_code", "fleet_no") > 1)
    return violations(found, key="fleet_no", field="fleet_no", raw="fleet_no",
                      message=pl.format("{} {} appears more than once", pl.col("business_code"), pl.col("fleet_no")))


@check(
    "MC003", "Every machine has a VIN", "machine", "warning",
    "VIN is the strongest identity key (READ ME). A blank VIN on an old transfer line is fine when the "
    "receiving line has one. Where FieldTrax knows the VIN, it is suggested.",
)
def vin_missing(t: Tables) -> pl.DataFrame:
    no_vin = t.machines.filter(pl.col("vin").is_null()).select("machine_id")
    missing = t.machine_lines.filter(pl.col("vin").is_null()).join(no_vin, on="machine_id", how="semi")
    if t.devices.is_empty():
        suggested = missing.with_columns(pl.lit(None, dtype=pl.String).alias("ftx_vin"))
    else:
        ftx = t.devices.filter(pl.col("vin").is_not_null(), pl.col("retired_on").is_null()).group_by("machine_id").agg(
            pl.col("vin").unique().sort().str.join(" / ").alias("ftx_vin"))
        suggested = missing.join(ftx, on="machine_id", how="left")
    message = pl.when(pl.col("ftx_vin").is_not_null()).then(
        pl.format("VIN blank; FieldTrax tracker on rego {} reports VIN {}", pl.col("rego"), pl.col("ftx_vin"))
    ).otherwise(pl.lit("VIN blank and no other source for it"))
    return violations(suggested, key="fleet_no", field="vin", raw="vin_raw", message=message)


@check(
    "MC004", "VINs typed in lower case or with spaces are normalised", "machine", "info",
    "Upper-cased and whitespace removed before matching; the raw text is kept in vin_raw.",
)
def vin_normalised(t: Tables) -> pl.DataFrame:
    found = t.machine_lines.filter(pl.col("vin_was_normalised"))
    return violations(found, key="fleet_no", field="vin", raw="vin_raw", message=pl.format("Read as {}", pl.col("vin")))


@check(
    "MC005", "A VIN or rego belongs to one current machine line only", "machine", "error",
    "Two live lines sharing a VIN/rego (not via a 'Transferred to' line) means a duplicate or a typo. "
    "They are kept as separate machines until Priya says which is right.",
)
def identity_collision(t: Tables) -> pl.DataFrame:
    live = _current_lines(t)
    shared_vin = pl.col("vin").is_not_null() & (pl.len().over("vin") > 1)
    shared_rego = pl.col("rego").is_not_null() & (pl.len().over("rego") > 1)
    found = live.filter(shared_vin | shared_rego)
    return violations(found, key="fleet_no", field="vin/rego", raw=pl.concat_str("vin", "rego", separator=" / ", ignore_nulls=True),
                      message="Another live line has the same VIN or rego")


@check(
    "MC006", "Lines of the same machine agree on VIN and rego", "machine", "error",
    "Lines are linked by VIN or rego; if one matches and the other differs, one of them is wrong.",
)
def identity_disagreement(t: Tables) -> pl.DataFrame:
    found = t.machine_lines.filter(
        (pl.col("vin").drop_nulls().n_unique().over("machine_id") > 1) | (pl.col("rego").n_unique().over("machine_id") > 1)
    )
    return violations(found, key="fleet_no", field="vin/rego", raw=pl.concat_str("vin", "rego", separator=" / ", ignore_nulls=True),
                      message=pl.format("Linked to {} but VIN or rego differs between its lines", pl.col("machine_id")))


@check(
    "MC007", "A 'Transferred to' line matches a line on the receiving sheet", "machine", "error",
    "READ ME: moved machines keep a line on the old sheet; the receiving sheet holds the current record.",
)
def transfer_has_receiver(t: Tables) -> pl.DataFrame:
    receivers = _current_lines(t).select("machine_id", pl.col("business_code").alias("receiver_business"))
    found = _transfer_lines(t).join(receivers, on="machine_id", how="left").filter(
        pl.col("receiver_business").is_null() | (pl.col("receiver_business") != pl.col("transferred_to"))
    )
    return violations(found, key="fleet_no", field="status", raw="status_raw",
                      message=pl.format("No matching line found on the {} sheet", pl.col("transferred_to")))


@check(
    "MC008", "Transferred machines carry the same year, cost and type on both sheets", "machine", "warning",
    "The two lines of a moved machine should describe the same asset.",
)
def transfer_attributes_agree(t: Tables) -> pl.DataFrame:
    current = _current_lines(t).select("machine_id", pl.col("year").alias("c_year"), pl.col("capital_cost_aud").alias("c_cost"),
                                       pl.col("category").alias("c_cat"), pl.col("fleet_no").alias("c_fleet"))
    pairs = _transfer_lines(t).join(current, on="machine_id", how="inner")
    found = pairs.filter((pl.col("year") != pl.col("c_year")) | (pl.col("capital_cost_aud") != pl.col("c_cost")) | (pl.col("category") != pl.col("c_cat")))
    return violations(found, key="fleet_no", field="year/cost/category", raw=None, message=pl.format(
        "Old line says {}/{}/{}; current line {} says {}/{}/{}", pl.col("year"), pl.col("capital_cost_aud"), pl.col("category"),
        pl.col("c_fleet"), pl.col("c_year"), pl.col("c_cost"), pl.col("c_cat")))


@check(
    "MC009", "Capital cost is a number", "machine", "warning",
    "Costs like 'TBC' are kept as raw text and loaded as null.",
)
def capital_cost_unreadable(t: Tables) -> pl.DataFrame:
    found = t.machine_lines.filter(pl.col("capital_cost_raw").is_not_null(), pl.col("capital_cost_aud").is_null())
    return violations(found, key="fleet_no", field="capital_cost", raw="capital_cost_raw", message="Capital cost is not a number")


@check(
    "MC010", "Capital cost typed as text is read as a number", "machine", "info",
    "Values like '$326,000' are stored as text in Excel; parsed to 326000.",
)
def capital_cost_as_text(t: Tables) -> pl.DataFrame:
    found = t.machine_lines.filter(pl.col("capital_cost_raw").str.contains(r"[$,]"), pl.col("capital_cost_aud").is_not_null())
    return violations(found, key="fleet_no", field="capital_cost", raw="capital_cost_raw",
                      message=pl.format("Read as {}", pl.col("capital_cost_aud")))


@check(
    "MC011", "Description agrees with the fleet number prefix", "machine", "warning",
    "EX = Excavator 20t, MX = 5t, SK = Skid steer, WC = Water cart, TP = Tipper, RL = Roller, LV = Light vehicle, GN = Generator.",
)
def category_matches_prefix(t: Tables) -> pl.DataFrame:
    found = t.machine_lines.filter(pl.col("fleet_prefix_category").is_not_null(), pl.col("category") != pl.col("fleet_prefix_category"))
    return violations(found, key="fleet_no", field="description", raw="description_raw",
                      message=pl.format("Prefix implies {}", pl.col("fleet_prefix_category")))


@check(
    "MC012", "A disposed machine was not built in the register's own year", "machine", "warning",
    "A machine with Year = 2026 that is already disposed/sold suggests the year or the status is wrong.",
)
def disposed_same_year(t: Tables) -> pl.DataFrame:
    found = t.machine_lines.filter(pl.col("status") == "disposed", pl.col("year") >= t.as_of.year)
    return violations(found, key="fleet_no", field="year/status", raw=pl.concat_str("year_raw", "status_raw", separator=" / "),
                      message="Disposed in the same year as its Year column")


@check(
    "MC013", "Make and model are known", "machine", "info",
    "NH Fleet has no Make/Model columns; those machines load with null make/model.",
)
def make_model_missing(t: Tables) -> pl.DataFrame:
    found = t.machine_lines.filter(pl.col("make").is_null() | pl.col("model").is_null())
    return violations(found, key="fleet_no", field="make/model", raw=None, message="No make/model on this sheet")


@check(
    "MC014", "Every working machine has a FieldTrax tracker", "machine", "warning",
    "Machines that are available, on project or in the workshop should report engine hours.",
)
def machine_without_tracker(t: Tables) -> pl.DataFrame:
    if t.devices.is_empty():
        return no_violations()
    tracked = t.devices.filter(pl.col("machine_id").is_not_null()).select("machine_id").unique()
    found = t.machines.filter(pl.col("status").is_in(ACTIVE_STATUSES)).join(tracked, on="machine_id", how="anti")
    return violations(found, key="machine_id", field=None, raw=pl.concat_str("business_code", "fleet_no", separator=" "),
                      message=pl.format("{} {} ({}) has no FieldTrax device", pl.col("business_code"), pl.col("fleet_no"), pl.col("status")))


@check(
    "MC015", "An operator mobile belongs to one machine", "machine", "warning",
    "From the hidden Operator mobile column. One number on two machines may be an operator with a machine and a ute, "
    "or a copy-paste error.",
)
def shared_operator_mobile(t: Tables) -> pl.DataFrame:
    lines = _current_lines(t).filter(pl.col("operator_mobile").is_not_null())
    shared = lines.with_columns(
        pl.len().over("operator_mobile").alias("n"),
        pl.concat_str(pl.col("business_code"), pl.lit(" "), pl.col("fleet_no")).alias("label"),
    ).filter(pl.col("n") > 1)
    others = shared.group_by("operator_mobile").agg(pl.col("label").sort().str.join(" and ").alias("all"))
    found = shared.join(others, on="operator_mobile")
    return violations(found, key="fleet_no", field="operator_mobile", raw="operator_mobile",
                      message=pl.format("{} share this operator mobile", pl.col("all")))
