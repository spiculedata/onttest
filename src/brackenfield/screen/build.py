"""Build Priya's screen: one self-contained HTML file with its records embedded."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import polars as pl

from brackenfield.config import WORKING_DAYS_PER_MONTH, WORKING_DAYS_PER_WEEK, Settings
from brackenfield.screen import analysis as an
from brackenfield.screen import questions, summary
from brackenfield.transform import telemetry

TEMPLATE = Path(__file__).with_name("template.html")

# Who signs off ending a hire. The register doesn't state an approval rule; the READ ME names
# Priya N. as Group Plant Manager and keeper of the register, and the project owner confirmed
# she is the one who signs. Change this if the rule changes (e.g. by business or by value).
SIGN_OFF: dict = {
    "rule": "Priya N., Group Plant Manager, signs each proposal to end a hire before the supplier is contacted.",
    "approvers": ["Priya N. (Group Plant Manager)"],
    "source": "READ ME A1 names Priya N. as Group Plant Manager and keeper of the register; confirmed by Tom Barber, 12 Nov 2026.",
}

BASIS_WORDS = {"day": "per day", "wk": "per week", "mth": "per month"}
BASIS_DAYS = {"day": 1, "wk": WORKING_DAYS_PER_WEEK, "mth": WORKING_DAYS_PER_MONTH}
# Data-quality findings that bear on "could this hire end, and would this machine do it".
# Others (e.g. a TBC capital cost) are real but do not change the answer, so they stay on Priya's list only.
RELEVANT_HIRE_CHECKS = {"HR002", "HR004", "HR006", "HR007", "HR009", "HR011", "HR013", "HR014"}
# Register-based only. FieldTrax-based findings are recomputed for each view (before / after the
# advance) from that view's own data, never read from the latest run's issue list.
RELEVANT_MACHINE_CHECKS = {"MC003", "MC005", "MC006", "MC007", "MC011"}


@dataclass(frozen=True)
class Warehouse:
    tables: dict[str, pl.DataFrame]
    versions: pl.DataFrame
    reading_lines: pl.DataFrame
    syncs: pl.DataFrame
    run_id: str | None
    labels: dict[str, str]
    be_typed_total: float | None = None


def read_warehouse(db_path: Path) -> Warehouse:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        con.execute("SET TimeZone = 'UTC'")
        t = lambda name: con.sql(f"SELECT * FROM {name}").pl()  # noqa: E731
        tables = {n: t(f"clean.{n}") for n in ("hires", "projects", "machines", "machine_lines", "sites", "organizations")}
        tables["issues"] = t("dq.issues")
        tables["mdm_usage"] = t("mdm.term_usage")
        return Warehouse(
            tables=tables, versions=t("raw.fieldtrax_device_versions"), reading_lines=t("raw.fieldtrax_reading_lines"),
            syncs=t("meta.fieldtrax_syncs").sort("run_id"), run_id=con.execute("SELECT max(run_id) FROM meta.runs").fetchall()[0][0],
            labels=dict(con.execute("SELECT label, run_id FROM meta.run_labels").fetchall()),
            be_typed_total=_be_typed_total(con),
        )
    finally:
        con.close()


def _be_typed_total(con) -> float | None:
    """The capital cost typed on the BE Plant TOTAL row (never loaded as data; compared with the lines)."""
    rows = con.execute("""
        SELECT c.value_text FROM raw.workbook_cells c
        JOIN raw.workbook_rows r ON r.sheet_name = c.sheet_name AND r.row_num = c.row_num AND r.disposition = 'total'
        WHERE c.sheet_name = 'BE Plant' AND c.col_letter = 'J'""").fetchall()
    return float(rows[0][0]) if len(rows) == 1 else None


BEFORE_ADVANCE = "before_advance"


def advance_boundary(syncs: pl.DataFrame, labels: dict[str, str] | None = None) -> tuple[str | None, str | None, str]:
    """(last sync before the advance, last sync after it, how the first was chosen).

    Preferred: the sync labelled "before_advance" (`brackenfield run --label before_advance`).
    Otherwise inferred: the advance shows up as a sync that brought new data after an earlier
    one had. If only one sync ever brought data, no advance has been seen.
    """
    if syncs.is_empty():
        return None, None, "no FieldTrax sync"
    if labels and BEFORE_ADVANCE in labels:
        return labels[BEFORE_ADVANCE], syncs["run_id"][-1], "labelled before_advance"
    latest = syncs["run_id"][-1]
    changing = syncs.filter((pl.col("new_readings") > 0) | (pl.col("new_device_versions") > 0))["run_id"].to_list()
    if len(changing) < 2:
        return latest, latest, "inferred: no advance seen yet"
    before = syncs.filter(pl.col("run_id") < changing[-1])["run_id"][-1]
    return before, latest, "inferred from the sync history (no before_advance label)"


def world_inputs(wh: Warehouse, as_of, cutoff_run: str | None) -> an.Inputs:
    """Inputs as FieldTrax stood at `cutoff_run`: only device versions and readings seen by then."""
    tb = wh.tables
    versions = wh.versions.filter(pl.col("sync_run") <= cutoff_run) if cutoff_run else wh.versions.head(0)
    lines = wh.reading_lines.filter(pl.col("first_seen_run") <= cutoff_run) if cutoff_run else wh.reading_lines.head(0)
    devices = telemetry.build_devices(versions, tb["machines"], tb["machine_lines"])
    return an.Inputs(
        as_of=as_of, hires=tb["hires"], projects=tb["projects"], machines=tb["machines"], sites=tb["sites"],
        devices=devices, readings=telemetry.build_readings(lines, devices), issues=tb["issues"],
        organizations=tb["organizations"],
    )


def _money(x: float | None) -> str:
    return "?" if x is None else f"${x:,.2f}"


def _rate_working(h: dict) -> str:
    basis = h["rate_basis"]
    gst_src = "from the GST column" if h["gst_basis"] == "gst_column" else f"GST blank, so {h['business_code']} default per READ ME"
    steps = [f"{h['rate_raw']} {BASIS_WORDS.get(basis, basis)}, {h['gst_treatment']} GST ({gst_src})"]
    if h["gst_treatment"] == "inc":
        steps.append(f"÷ 1.1 = {_money(h['rate_ex_gst'])} ex GST")
    if basis != "day":
        steps.append(f"÷ {BASIS_DAYS[basis]} working days = {_money(h['day_rate_ex_gst'])}/day")
    return " → ".join(steps)


def _blocking_reasons(machine: dict | None) -> list[str]:
    """What makes the pair unconfirmed under the rules: the machine's idleness is not confirmed."""
    if machine and machine["idle_status"] == "unconfirmed":
        return [f"{machine['business_code']} {machine['fleet_no']}: {machine['idle_reason']}"]
    return []


def _open_questions(h: dict, dup_rows: dict[str, list[int]]) -> list[str]:
    """Details I could not confirm that do not change the counted saving."""
    notes = []
    if h["supplier_basis"] == "inferred":
        notes.append(f"Supplier written as '{h['supplier_raw']}'; read as {h['supplier_name']}. Not confirmed.")
    rows = dup_rows.get(h["hire_no"], [])
    if len(rows) > 1:
        notes.append(f"{h['hire_no']} is on rows {' and '.join(map(str, rows))} with identical details. Counted once; one hire or two?")
    return notes


def _iso(v) -> str | None:
    return None if v is None else v.isoformat()


def _hire_payload(h: dict, machine: dict | None, inp: an.Inputs, dup_rows: dict) -> dict:
    issues = [i for i in an.issues_for(inp.issues, h["source_tab"], h["source_row"], [])
              if i["check_id"] in RELEVANT_HIRE_CHECKS or i["check_id"].startswith("SC-hires")]
    machine_issues = []
    if machine:
        keys = [machine["machine_id"], *(machine["device_ids"] or "").split(", ")]
        machine_issues = [i for i in an.issues_for(inp.issues, machine["source_tab"], machine["source_row"], [k for k in keys if k])
                          if i["check_id"] in RELEVANT_MACHINE_CHECKS]
    blocking = _blocking_reasons(machine)
    notes = _open_questions(h, dup_rows) + [f"{i['check_id']}: {i['message']}" for i in issues + machine_issues]
    if h["is_duplicate_line"]:
        outcome = "duplicate"
    elif machine is None:
        outcome = "no_match"
    else:
        outcome = "end_unconfirmed" if blocking else "end_confirmed"
    days_left = an.working_days_until(inp.as_of, h["off_hire_date"])
    return {
        "hire_no": h["hire_no"], "tab": h["source_tab"], "row": h["source_row"], "outcome": outcome,
        "supplier": h["supplier_name"], "supplier_raw": h["supplier_raw"], "category": h["category"],
        "category_raw": h["category_raw"], "project_code": h["project_code"], "project_name": h["project_name"],
        "project_raw": h["project_raw"], "state": h["project_state"], "business": h["business_code"],
        "start": _iso(h["start_date"]), "start_raw": h["start_raw"], "off_hire": _iso(h["off_hire_date"]),
        "off_hire_raw": h["off_hire_raw"], "rate_raw": h["rate_raw"], "basis_raw": h["basis_raw"], "gst_raw": h["gst_raw"],
        "day_ex": h["day_rate_ex_gst"], "day_inc": an.ex_to_inc(h["day_rate_ex_gst"]), "working": _rate_working(h),
        "duplicate_of_row": h["duplicate_of_row"], "notes": h["notes"], "comments": h["comments"],
        "machine_id": machine["machine_id"] if machine else None, "unconfirmed": blocking, "open_questions": notes,
        "days_to_planned_off_hire": days_left,
        "saving_to_planned_off_hire": None if days_left is None else round(days_left * h["day_rate_ex_gst"], 2),
    }


def _series(inp: an.Inputs, machine_ids: list[str]) -> dict[str, list]:
    """Engine hours for each candidate machine across the idle window, all devices combined."""
    start, end = an.idle_window(inp.as_of)
    rows = inp.readings.filter(
        pl.col("machine_id").is_in(machine_ids), pl.col("engine_hours").is_not_null(),
        pl.col("time_utc") >= start, pl.col("time_utc") <= end,
    ).sort("device_id", "time_utc").with_columns(pl.col("engine_hours").diff().over("device_id").alias("step")).sort("time_utc")
    out: dict[str, list] = {}
    for mid, t, step in rows.select("machine_id", "time_utc", "step").iter_rows():
        out.setdefault(mid, []).append([t.isoformat(), round(max(step or 0.0, 0.0), 2)])
    return out


def build_world(inp: an.Inputs, machine_lines: pl.DataFrame, cutoff_run: str | None, usage: pl.DataFrame) -> dict:
    machines = an.machine_evidence(inp, machine_lines)
    hires = an.on_hire(inp)
    matches = an.match(hires, machines)
    by_id = {m["machine_id"]: m for m in machines.to_dicts()}
    dup_rows = {k: sorted(v) for k, v in hires.group_by("hire_no").agg(pl.col("source_row")).iter_rows() if len(v) > 1}
    assigned = {mid: row for row, mid in matches.items()}
    hire_payload = [_hire_payload(h, by_id.get(matches.get(h["source_row"])), inp, dup_rows) for h in hires.to_dicts()]
    keep = ("machine_id", "business_code", "fleet_no", "category", "make", "model", "depot", "state", "status_raw",
            "source_tab", "source_row", "source_refs", "device_ids", "readings_in_window", "idle_status", "idle_reason")
    return {
        "fieldtrax_run": cutoff_run,
        "devices_known": inp.devices.height,
        "hires": hire_payload,
        "open_questions": questions.build(inp, hires, machines, matches, hire_payload, usage, SIGN_OFF),
        "machines": [
            {**{k: m[k] for k in keep},
             "status_label": an.STATUS_LABEL,
             "hours_run": None if m["hours_run"] is None else round(m["hours_run"], 2),
             "first_reading": _iso(m["first_reading"]), "last_reading": _iso(m["last_reading"]),
             "assigned_hire_row": assigned.get(m["machine_id"])}
            for m in machines.sort("state", "category", "business_code", "fleet_no").to_dicts()
        ],
        "series": _series(inp, machines["machine_id"].to_list()),
    }


def dst_check(readings: pl.DataFrame, as_of) -> dict:
    """Would reading the window in AEDT (UTC+11, NSW daylight time) instead of AEST change anything?

    The two readings differ only in the first and last hour of the window; count readings there.
    """
    start, end = an.idle_window(as_of)
    hour = timedelta(hours=1)
    timed = readings.filter(pl.col("time_utc").is_not_null())
    edge = timed.filter(((pl.col("time_utc") >= start - hour) & (pl.col("time_utc") < start))
                        | ((pl.col("time_utc") > end - hour) & (pl.col("time_utc") <= end)))
    times = sorted(set(timed["time_utc"].dt.strftime("%H:%M").to_list()))
    return {"edge_readings": edge.height, "times_utc": times}


def device_changes(before: pl.DataFrame, after: pl.DataFrame) -> list[dict]:
    """What the advance did to the device list, in words."""
    b = {r["device_id"]: r for r in before.to_dicts()}
    a = {r["device_id"]: r for r in after.to_dicts()}
    out = []
    for did, r in sorted(a.items()):
        old = b.get(did)
        if old is None:
            out.append({"device_id": did, "change": "added", "detail": f"New device '{r['name']}' (linked by {r['link_method'] or 'nothing'})"})
        elif old["is_listed"] and not r["is_listed"]:
            out.append({"device_id": did, "change": "gone", "detail": f"'{r['name']}' no longer listed by FieldTrax; its readings are kept"})
        elif old["name"] != r["name"]:
            out.append({"device_id": did, "change": "renamed", "detail": f"'{old['name']}' is now '{r['name']}'"})
    return out


def build_payload(wh: Warehouse, as_of) -> dict:
    before_run, after_run, before_basis = advance_boundary(wh.syncs, wh.labels)
    lines = wh.tables["machine_lines"]
    start, end = an.idle_window(as_of)
    before_inp, after_inp = world_inputs(wh, as_of, before_run), world_inputs(wh, as_of, after_run)
    before_world = build_world(before_inp, lines, before_run, wh.tables["mdm_usage"])
    changes = device_changes(before_inp.devices, after_inp.devices)
    return {
        "meta": {
            "as_of": as_of.isoformat(), "as_of_label": "31 October 2026, end of day AEST",
            "window_start": start.isoformat(), "window_end": end.isoformat(), "idle_max_hours": an.IDLE_MAX_HOURS,
            "run_id": wh.run_id, "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "week_days": WORKING_DAYS_PER_WEEK, "month_days": WORKING_DAYS_PER_MONTH,
            "advance_seen": before_run != after_run,
            "before_run": before_run, "before_basis": before_basis, "after_run": after_run,
        },
        "sign_off": SIGN_OFF,
        "worlds": {
            "before": before_world,
            "after_advance": build_world(after_inp, lines, after_run, wh.tables["mdm_usage"]),
        },
        "advance_device_changes": changes,
        "summary": summary.skeleton(wh.tables, wh.be_typed_total, before_inp, after_inp, before_world, changes),
        "dst_check": {"before": dst_check(before_inp.readings, as_of), "after_advance": dst_check(after_inp.readings, as_of)},
    }


def render(payload: dict) -> str:
    data = json.dumps(payload, default=str).replace("</", "<\\/")
    return TEMPLATE.read_text().replace("/*__DATA__*/null", data)


def _pair(h: dict, machines: dict[str, dict]) -> dict:
    m = machines[h["machine_id"]]
    return {
        "hire": {"hire_no": h["hire_no"], "source": {"tab": h["tab"], "row": h["row"]}, "supplier": h["supplier"],
                 "category": h["category"], "project": {"code": h["project_code"], "name": h["project_name"], "state": h["state"]},
                 "business": h["business"], "rate_as_written": {"rate": h["rate_raw"], "basis": h["basis_raw"], "gst": h["gst_raw"]},
                 "day_rate_ex_gst": round(h["day_ex"], 2), "working": h["working"]},
        "replace_with": {"machine_id": m["machine_id"], "business": m["business_code"], "fleet_no": m["fleet_no"],
                         "category": m["category"], "depot": m["depot"], "state": m["state"], "register_status": m["status_label"],
                         "source": {"tab": m["source_tab"], "row": m["source_row"]}, "fieldtrax_devices": m["device_ids"],
                         "hours_run_18_31_oct": m["hours_run"], "readings_in_window": m["readings_in_window"]},
        "saving_per_day_ex_gst": round(h["day_ex"], 2),
        "status": "confirmed" if h["outcome"] == "end_confirmed" else "unconfirmed",
        "unconfirmed_because": h["unconfirmed"], "open_details": h["open_questions"],
        "signs": SIGN_OFF["approvers"],
    }


def _world_answer(world: dict) -> dict:
    machines = {m["machine_id"]: m for m in world["machines"]}
    ranked = sorted(world["hires"], key=lambda h: -h["day_ex"])
    confirmed = [h for h in ranked if h["outcome"] == "end_confirmed"]
    unconfirmed = [h for h in ranked if h["outcome"] == "end_unconfirmed"]
    total = lambda hs: round(sum(h["day_ex"] for h in hs), 2)  # noqa: E731  exact day rates, rounded once
    return {
        "fieldtrax_sync": world["fieldtrax_run"],
        "hires_to_end": [_pair(h, machines) for h in confirmed],
        "saving_per_day_ex_gst": total(confirmed),
        "unconfirmed": [_pair(h, machines) for h in unconfirmed],
        "unconfirmed_saving_per_day_ex_gst": total(unconfirmed),
        "open_hires": len([h for h in world["hires"] if h["outcome"] != "duplicate"]),
        "available_machines": {s: len([m for m in world["machines"] if m["idle_status"] == s]) for s in ("confirmed", "unconfirmed", "working")},
        "open_questions": [{**{k: q[k] for k in ("id", "group", "title", "finding", "effect", "ask")},
                            "effect_per_day": None if q["effect_per_day"] is None else round(q["effect_per_day"], 2)}
                           for q in world["open_questions"]],
    }


def answers(payload: dict) -> dict:
    """The answer as data: the same numbers as the screen, for the before and after-advance views."""
    meta = payload["meta"]
    return {
        "question": "Which hires could I end right now because we own something idle that would do the job, "
                    "and what would that save me a day?",
        "as_of": meta["window_end"],
        "rules": {
            "open_hire": "READ ME rules; start on or before 31 Oct 2026 and off-hire after it or none; $/day ex GST "
                         f"(week = {meta['week_days']} days, month = {meta['month_days']}, inc GST / 1.1, blank GST: BE inc, NH ex).",
            "idle": f"Register Available or Yard, and FieldTrax under {meta['idle_max_hours']} engine hour from "
                    f"{meta['window_start']} to {meta['window_end']} (sum of positive increases, all devices). No device = unconfirmed.",
            "replaceable": "Same category, project in the same state as the machine's depot; pairs chosen to save the most.",
            "dates": "Read day-first (Australian).",
        },
        "before_advance_sync": {"run": meta["before_run"], "chosen_by": meta["before_basis"]},
        "who_signs": SIGN_OFF,
        "answer": _world_answer(payload["worlds"]["before"]),
        "after_advance": {**_world_answer(payload["worlds"]["after_advance"]), "device_changes": payload["advance_device_changes"]},
        "pipeline_run": meta["run_id"],
    }


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False) + "\n")


def build_screen(settings: Settings, out_path: Path, answers_path: Path | None = None, detail_path: Path | None = None) -> Path:
    """The screen, plus answers.json (the brief's skeleton) and the detail behind it (pairs, records, who signs)."""
    payload = build_payload(read_warehouse(settings.database_path), settings.as_of)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(payload))
    if answers_path:
        _write_json(answers_path, payload["summary"])
    if detail_path:
        _write_json(detail_path, answers(payload))
    return out_path
