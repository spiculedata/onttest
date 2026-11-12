"""Checks on Hires 25-26."""

from __future__ import annotations

from datetime import date

import polars as pl

from brackenfield.checks.registry import Tables, check, violations

DAY_RATE_BAND = (0.6, 1.6)  # x the category median; outside this is suspicious


def _live(t: Tables) -> pl.DataFrame:
    return t.hires.filter(~pl.col("is_cancelled"), ~pl.col("is_duplicate_line"))


@check(
    "HR001", "A hire line is not an exact copy of an earlier line", "hire", "warning",
    "Kept and flagged (is_duplicate_line). Could be a double entry or two identical machines on hire.",
)
def exact_duplicate(t: Tables) -> pl.DataFrame:
    found = t.hires.filter(pl.col("is_duplicate_line"))
    return violations(found, key="hire_no", field=None, raw=None,
                      message=pl.format("Identical to row {}; is this one hire or two?", pl.col("duplicate_of_row")))


@check(
    "HR002", "A hire number is used by one hire only", "hire", "error",
    "Two different lines sharing a hire number cannot both be right.",
)
def hire_no_reused(t: Tables) -> pl.DataFrame:
    distinct = t.hires.filter(~pl.col("is_duplicate_line"))
    found = distinct.filter(pl.len().over("hire_no") > 1)
    return violations(found, key="hire_no", field="hire_no", raw="hire_no", message="Hire number used by different lines")


@check(
    "HR003", "Hire numbers run without gaps", "hire", "info",
    "A gap may be a deleted line, which READ ME says never happens.",
)
def hire_no_gaps(t: Tables) -> pl.DataFrame:
    numbers = t.hires["hire_no"].str.extract(r"^H-(\d{4})$", 1).cast(pl.Int32, strict=False).drop_nulls()
    if numbers.is_empty():
        return violations(t.hires.head(0), key="hire_no", field=None, raw=None, message="")
    missing = sorted(set(range(numbers.min(), numbers.max() + 1)) - set(numbers.to_list()))
    frame = pl.DataFrame({"hire_no": [f"H-{n}" for n in missing], "source_tab": "Hires 25-26", "source_row": None},
                         schema={"hire_no": pl.String, "source_tab": pl.String, "source_row": pl.Int32})
    return violations(frame, key="hire_no", field="hire_no", raw=None, message="Hire number not present on the sheet")


@check(
    "HR004", "Start is a date or TBA", "hire", "error",
    "READ ME: a Start of TBA means the hire has not started. Anything else must be a date.",
)
def start_unreadable(t: Tables) -> pl.DataFrame:
    found = t.hires.filter(pl.col("start_date").is_null(), pl.col("start_marker").is_null())
    return violations(found, key="hire_no", field="start", raw="start_raw", message="Start is not a readable date")


@check(
    "HR005", "Start of TBA means not started", "hire", "info",
    "Loaded with status not_started and a null start_date.",
)
def start_tba(t: Tables) -> pl.DataFrame:
    found = t.hires.filter(pl.col("start_marker") == "tba")
    return violations(found, key="hire_no", field="start", raw="start_raw", message="Not started (Start = TBA)")


@check(
    "HR006", "Off-hire is a date, blank, 'ongoing' or 'TBA'", "hire", "error",
    "READ ME: blank, ongoing or TBA means still on hire.",
)
def off_hire_unreadable(t: Tables) -> pl.DataFrame:
    found = t.hires.filter(pl.col("off_hire_date").is_null(), pl.col("off_hire_marker").is_null())
    return violations(found, key="hire_no", field="off_hire", raw="off_hire_raw", message="Off-hire is not a readable date")


@check(
    "HR007", "Off-hire is not before start", "hire", "error",
    "A machine cannot come off hire before it went on.",
)
def off_hire_before_start(t: Tables) -> pl.DataFrame:
    found = t.hires.filter(pl.col("off_hire_date") < pl.col("start_date"))
    return violations(found, key="hire_no", field="off_hire", raw="off_hire_raw",
                      message=pl.format("Off-hire {} is before start {}", pl.col("off_hire_date"), pl.col("start_date")))


@check(
    "HR008", "Day/month order is read Australian-style", "hire", "info",
    "Text dates like 02/04/26 are read as dd/mm/yy (2 Apr 2026). Listed where the other order would also be a valid date.",
)
def ambiguous_dates(t: Tables) -> pl.DataFrame:
    start = t.hires.filter(pl.col("start_ambiguous")).with_columns(pl.lit("start").alias("f"), pl.col("start_raw").alias("r"), pl.col("start_date").alias("d"))
    off = t.hires.filter(pl.col("off_hire_ambiguous")).with_columns(pl.lit("off_hire").alias("f"), pl.col("off_hire_raw").alias("r"), pl.col("off_hire_date").alias("d"))
    found = pl.concat([start, off])
    return violations(found, key="hire_no", field=None, raw="r", message=pl.format("{} read as {}", pl.col("f"), pl.col("d")))


@check(
    "HR009", "A rate with its own '/wk' or '/day' agrees with the Basis column", "hire", "error",
    "'5435/wk' with Basis 'day' would be out by a factor of 5.",
)
def rate_basis_conflict(t: Tables) -> pl.DataFrame:
    found = t.hires.filter(pl.col("rate_text_basis").is_not_null(), pl.col("rate_text_basis") != pl.col("rate_basis"))
    return violations(found, key="hire_no", field="rate", raw="rate_raw",
                      message=pl.format("Rate text says {}, Basis says {}", pl.col("rate_text_basis"), pl.col("rate_basis")))


@check(
    "HR010", "Blank GST is defaulted by business", "hire", "info",
    "READ ME: if GST is blank, BE entries are inc GST and NH entries are ex GST.",
)
def gst_defaulted(t: Tables) -> pl.DataFrame:
    found = t.hires.filter(pl.col("gst_basis") == "readme_default_for_business")
    return violations(found, key="hire_no", field="gst", raw="gst_raw",
                      message=pl.format("GST blank; {} default '{}' applied", pl.col("business_code"), pl.col("gst_treatment")))


@check(
    "HR011", "The hire's BU matches the project's business", "hire", "error",
    "Each project belongs to one business (Projects tab).",
)
def bu_matches_project(t: Tables) -> pl.DataFrame:
    projects = t.projects.select("project_code", pl.col("business_code").alias("project_business"))
    found = t.hires.join(projects, on="project_code", how="inner").filter(pl.col("business_code") != pl.col("project_business"))
    return violations(found, key="hire_no", field="business_code", raw="business_code_raw",
                      message=pl.format("BU {} but project {} belongs to {}", pl.col("business_code"), pl.col("project_code"), pl.col("project_business")))


@check(
    "HR012", "Projects given by name or bare number are resolved to a code", "hire", "info",
    "'2055' -> P-2055; 'Darling Downs solar civil' -> P-2055.",
)
def project_resolved_loosely(t: Tables) -> pl.DataFrame:
    found = t.hires.filter(pl.col("project_match").is_in(["bare_number", "name"]))
    return violations(found, key="hire_no", field="project", raw="project_raw",
                      message=pl.format("Resolved by {} to {}", pl.col("project_match"), pl.col("project_code")))


@check(
    "HR013", "Day rate is in line with other hires of the same category", "hire", "warning",
    f"Ex-GST day rate outside {DAY_RATE_BAND[0]}x-{DAY_RATE_BAND[1]}x the category median usually means a wrong Basis or GST.",
)
def day_rate_outlier(t: Tables) -> pl.DataFrame:
    live = _live(t).with_columns(pl.col("day_rate_ex_gst").median().over("category").alias("median"))
    ratio = pl.col("day_rate_ex_gst") / pl.col("median")
    found = live.filter((ratio < DAY_RATE_BAND[0]) | (ratio > DAY_RATE_BAND[1]))
    return violations(found, key="hire_no", field="rate", raw=pl.concat_str("rate_raw", "basis_raw", "gst_raw", separator=" | ", ignore_nulls=True),
                      message=pl.format("{}/day ex GST vs {} median {}/day", pl.col("day_rate_ex_gst"), pl.col("category"), pl.col("median").round(2)))


@check(
    "HR014", "Day rate is above the superseded Jan-25 rate", "hire", "warning",
    "The hidden `_old rates` tab lists day rates superseded in Jan-25; a 2026 hire at or below one is suspicious.",
)
def below_old_rate(t: Tables) -> pl.DataFrame:
    old = t.rate_card.select("category", pl.col("day_rate").alias("old_rate"))
    found = _live(t).join(old, on="category", how="inner").filter(pl.col("day_rate_ex_gst") <= pl.col("old_rate"))
    return violations(found, key="hire_no", field="rate", raw="rate_raw",
                      message=pl.format("{}/day ex GST is not above the old {} rate {}", pl.col("day_rate_ex_gst"), pl.col("category"), pl.col("old_rate")))


@check(
    "HR015", "Struck-through lines are loaded as cancelled", "hire", "info",
    "READ ME: struck-through hire lines were cancelled before they started. Kept, status = cancelled.",
)
def cancelled_lines(t: Tables) -> pl.DataFrame:
    found = t.hires.filter(pl.col("is_cancelled"))
    return violations(found, key="hire_no", field=None, raw=None, message="Struck through: cancelled")


def _swapped(d: date | None) -> date | None:
    """The same digits read the other way round (d/m <-> m/d), if that is a different, valid date."""
    if d is None or d.day > 12 or d.day == d.month:
        return None
    try:
        return date(d.year, d.day, d.month)
    except ValueError:
        return None


def _is_open(start: date | None, off: date | None, as_of: date) -> bool:
    return start is not None and start <= as_of and (off is None or off > as_of)


def _entry_kinds(cells: pl.DataFrame) -> dict[tuple[int, str], str]:
    """How each Start/Off-hire cell was entered: an Excel date, or text typed d/m/y. ISO text is unambiguous."""
    hire_cells = cells.filter(pl.col("sheet_name") == "Hires 25-26", pl.col("col_letter").is_in(["F", "G"]))
    kinds = {}
    for r in hire_cells.iter_rows(named=True):
        if r["value_type"] == "date":
            kinds[(r["row_num"], r["col_letter"])] = "Excel date"
        elif r["value_type"] == "string" and "/" in (r["value_text"] or ""):
            kinds[(r["row_num"], r["col_letter"])] = "typed d/m/y"
    return kinds


@check(
    "HR016", "Reading a date month-first would not change whether the hire is open", "hire", "warning",
    "Dates are read day-first (Australian). Excel dates and typed d/m/y dates with a day of 12 or less could have been "
    "entered month-first; listed only where that would change whether the hire is open on the as-of date.",
)
def date_swap_changes_answer(t: Tables) -> pl.DataFrame:
    kinds = _entry_kinds(t.cells)
    rows = []
    for h in t.hires.filter(~pl.col("is_cancelled"), pl.col("start_marker").is_null()).iter_rows(named=True):
        base = _is_open(h["start_date"], h["off_hire_date"], t.as_of)
        for col, field, d in (("F", "start", h["start_date"]), ("G", "off_hire", h["off_hire_date"])):
            kind, alt = kinds.get((h["source_row"], col)), _swapped(d)
            if not kind or not alt:
                continue
            start, off = (alt, h["off_hire_date"]) if col == "F" else (h["start_date"], alt)
            if _is_open(start, off, t.as_of) == base:
                continue
            effect = "would not be open on 31 Oct" if base else "would be open on 31 Oct"
            rows.append({"hire_no": h["hire_no"], "source_tab": h["source_tab"], "source_row": h["source_row"], "field": field,
                         "raw": h[f"{field}_raw"], "message": f"{field.replace('_', '-').capitalize()} {d:%-d %b %Y} ({kind}); "
                         f"read month-first it is {alt:%-d %b %Y} and the hire {effect}."})
    frame = pl.DataFrame(rows, schema={"hire_no": pl.String, "source_tab": pl.String, "source_row": pl.Int32, "field": pl.String,
                                       "raw": pl.String, "message": pl.String})
    return frame.select(pl.col("hire_no").alias("entity_key"), "source_tab", "source_row", "field",
                        pl.col("raw").alias("raw_value"), "message")
