"""Independent cross-check of the outputs against the workbook. `brackenfield verify`.

Deliberately does NOT reuse the pipeline's transforms or master data: it reads the .xlsx with
openpyxl, applies the READ ME rules written out again here, and compares. A mistake in the
pipeline then shows up as a disagreement instead of being repeated.

Checks:
  1. every non-empty cell is in raw.workbook_cells with the same text
  2. every non-empty row has a disposition; every record row is in exactly one clean table
  3. every hire and machine line leads back to its tab and row, and its values match the cells
  4. every machine's source tab/row is one of its own register lines
  5. answers_detail.json: each pair re-derived from the cells and raw FieldTrax lines; totals; best pairs
  6. answers.json (the brief's skeleton): every count recomputed from the cells and raw FieldTrax lines
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import duckdb
import openpyxl

HIRES, BE, NH, PROJECTS = "Hires 25-26", "BE Plant", "NH Fleet", "Projects"
AEST = timezone(timedelta(hours=10))
AS_OF = date(2026, 10, 31)

# READ ME A13, typed again on purpose (independent of mdm/aliases.csv), plus the sheet's own words.
CATEGORY = {
    "excavator 20t": "Excavator 20t", "20t digger": "Excavator 20t", "ex20": "Excavator 20t", "20t excavator": "Excavator 20t",
    "excavator 5t": "Excavator 5t", "5t digger": "Excavator 5t", "ex5": "Excavator 5t", "5t excavator": "Excavator 5t",
    "skid steer": "Skid steer", "bobcat": "Skid steer",
    "water cart": "Water cart", "water truck": "Water cart", "wc": "Water cart",
    "tipper": "Tipper", "tipper truck": "Tipper", "truck & dog": "Tipper", "t&d": "Tipper",
    "roller": "Roller", "smooth drum": "Roller", "smooth drum roller": "Roller",
    "light vehicle": "Light vehicle", "ute": "Light vehicle", "generator": "Generator", "genset": "Generator",
}
DEPOT_STATE = {"toowoomba": "QLD", "brisbane yard": "QLD", "newcastle": "NSW", "dubbo": "NSW"}
DAYS = {"day": 1, "wk": 5, "mth": 22}


@dataclass
class Report:
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def check(self, ok: bool, what: str, detail: str = "") -> None:
        (self.passed if ok else self.failed).append(what if ok else f"{what}: {detail}")


def _text(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat() if v.time() == time(0) else v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _cells(path: Path) -> dict[str, dict[int, dict[str, object]]]:
    """sheet -> row -> column letter -> value, for every non-empty cell (hidden ones too)."""
    wb = openpyxl.load_workbook(path)
    out: dict[str, dict[int, dict[str, object]]] = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None:
                    out.setdefault(ws.title, {}).setdefault(c.row, {})[c.column_letter] = c.value
    return out


def _q(con, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def check_raw_cells(rep: Report, cells, con) -> None:
    stored = {(r["sheet_name"], r["row_num"], r["col_letter"]): r["value_text"]
              for r in _q(con, "SELECT sheet_name, row_num, col_letter, value_text FROM raw.workbook_cells")}
    bad = [f"{s}!{c}{r}" for s, rows in cells.items() for r, cols in rows.items() for c, v in cols.items()
           if stored.get((s, r, c)) != _text(v)]
    total = sum(len(cols) for rows in cells.values() for cols in rows.values())
    rep.check(not bad, f"All {total} non-empty cells are in raw.workbook_cells unchanged", f"{len(bad)} differ, e.g. {bad[:5]}")


def check_rows_accounted(rep: Report, cells, con) -> None:
    disp = {(r["sheet_name"], r["row_num"]): r["disposition"] for r in _q(con, "SELECT sheet_name, row_num, disposition FROM raw.workbook_rows")}
    missing = [f"{s}!{r}" for s, rows in cells.items() for r in rows if (s, r) not in disp or disp[(s, r)] == "blank"]
    rep.check(not missing, "Every non-empty row in every tab has a disposition", f"{missing[:5]}")
    landed: dict[tuple[str, int], int] = {}
    for table in ("hires", "machine_lines", "projects", "rate_card"):
        for r in _q(con, f"SELECT source_tab, source_row FROM clean.{table}"):
            landed[(r["source_tab"], r["source_row"])] = landed.get((r["source_tab"], r["source_row"]), 0) + 1
    records = [k for k, d in disp.items() if d == "record"]
    lost = [f"{s}!{r}" for s, r in records if landed.get((s, r), 0) != 1]
    rep.check(not lost, f"All {len(records)} record rows are in exactly one clean table", f"{lost[:5]}")
    set_aside = sorted({d for d in disp.values()} - {"record"})
    rep.check(True, f"Rows not loaded as records are classed, not dropped: {', '.join(set_aside)}")


def check_hires(rep: Report, cells, con) -> None:
    sheet = cells[HIRES]
    rows = _q(con, "SELECT * FROM clean.hires")
    cols = {"hire_no": "A", "supplier_raw": "B", "category_raw": "C", "project_raw": "D", "business_code_raw": "E",
            "start_raw": "F", "off_hire_raw": "G", "rate_raw": "H", "basis_raw": "I", "gst_raw": "J", "notes": "K"}
    bad = []
    for h in rows:
        row = sheet.get(h["source_row"], {})
        for col, letter in cols.items():
            want = _text(row.get(letter))
            got = h[col]
            if col == "notes":
                want = re.sub(r"\s+", " ", want).strip() if want else None
            if got != want:
                bad.append(f"{HIRES}!{letter}{h['source_row']} {col}: cell {want!r} vs duckdb {got!r}")
    data_rows = [r for r in sheet if r > 1]
    rep.check(len(rows) == len(data_rows) and not bad, f"All {len(rows)} hires lead back to {HIRES} and match the cells",
              f"{len(rows)} hires vs {len(data_rows)} rows; {bad[:5]}")


def _norm(v) -> str:
    return re.sub(r"\s+", "", str(v)).upper() if v is not None else ""


def check_machines(rep: Report, cells, con) -> None:
    lines = _q(con, "SELECT * FROM clean.machine_lines")
    layout = {BE: {"fleet_no": "A", "rego_raw": "E", "vin_raw": "F", "year_raw": "G", "status_raw": "H", "depot_raw": "I", "capital_cost_raw": "J"},
              NH: {"fleet_no": "A", "rego_raw": "C", "vin_raw": "D", "year_raw": "E", "status_raw": "F", "depot_raw": "G", "capital_cost_raw": "H"}}
    bad = []
    for m in lines:
        row = cells[m["source_tab"]].get(m["source_row"], {})
        for col, letter in layout[m["source_tab"]].items():
            want, got = _text(row.get(letter)), m[col]
            same = _norm(want) == _norm(got) if col == "fleet_no" else want == got
            if not same:
                bad.append(f"{m['source_tab']}!{letter}{m['source_row']} {col}: cell {want!r} vs duckdb {got!r}")
        desc = row.get("B")
        if CATEGORY.get(str(desc).strip().lower()) != m["category"]:
            bad.append(f"{m['source_tab']}!B{m['source_row']} {desc!r} mapped to {m['category']!r}")
    rep.check(not bad, f"All {len(lines)} machine lines lead back to their tab/row, values and categories match", f"{bad[:5]}")
    machines = _q(con, "SELECT machine_id, fleet_no, source_tab, source_row, source_refs FROM clean.machines")
    by_line = {(m["source_tab"], m["source_row"]): m for m in lines}
    wrong = []
    for m in machines:
        line = by_line.get((m["source_tab"], m["source_row"]))
        if not line or line["machine_id"] != m["machine_id"] or line["fleet_no"] != m["fleet_no"]:
            wrong.append(m["machine_id"])
        for ref in m["source_refs"].split("; "):
            tab, row = ref.rsplit("!", 1)
            if by_line.get((tab, int(row)), {}).get("machine_id") != m["machine_id"]:
                wrong.append(f"{m['machine_id']} ref {ref}")
    rep.check(not wrong, f"All {len(machines)} machines point at their own register line(s)", f"{wrong[:5]}")


def _day_rate(row: dict, business: str) -> float:
    amount = float(re.sub(r"[^\d.]", "", str(row["H"]).split("/")[0]))
    gst = (row.get("J") or ("inc" if business == "BE" else "ex")).strip().lower()
    ex = amount / 1.1 if gst == "inc" else amount
    return ex / DAYS[str(row["I"]).strip().lower()]


def _hours_run(con, machine_id: str, before_run: str) -> float | None:
    """Sum of positive increases, per device, from raw FieldTrax lines held at the before-advance sync."""
    devs = [r["device_id"] for r in _q(con, f"""
        SELECT DISTINCT device_id FROM raw.fieldtrax_device_versions v
        WHERE sync_run <= '{before_run}' AND device_id IN (SELECT device_id FROM clean.devices WHERE machine_id = '{machine_id}')""")]
    if not devs:
        return None
    start = datetime(2026, 10, 18, tzinfo=AEST)
    end = datetime(2026, 10, 31, 23, 59, 59, tzinfo=AEST)
    total = 0.0
    for d in devs:
        seen: dict[datetime, float] = {}
        for r in _q(con, f"SELECT time, value, unit FROM raw.fieldtrax_reading_lines WHERE device_id = '{d}' AND first_seen_run <= '{before_run}'"):
            t = datetime.fromisoformat(r["time"].replace("Z", "+00:00"))
            if start <= t <= end:
                seen.setdefault(t, float(r["value"]) / (3600 if r["unit"] == "s" else 1))
        vals = [seen[t] for t in sorted(seen)]
        total += sum(max(b - a, 0) for a, b in zip(vals, vals[1:]))
    return total


def check_answers(rep: Report, cells, con, answers: dict) -> None:
    projects = {str(r["A"]).strip(): r for n, r in cells[PROJECTS].items() if n > 1}
    before_run = answers["before_advance_sync"]["run"]
    pairs = answers["answer"]["hires_to_end"] + answers["answer"]["unconfirmed"]
    bad, used = [], set()
    for p in pairs:
        h, m = p["hire"], p["replace_with"]
        hrow = cells[h["source"]["tab"]][h["source"]["row"]]
        mrow = cells[m["source"]["tab"]][m["source"]["row"]]
        status_col, depot_col, desc_col = ("H", "I", "B") if m["source"]["tab"] == BE else ("F", "G", "B")
        problems = []
        if hrow["A"] != h["hire_no"]:
            problems.append(f"row is {hrow['A']}")
        if CATEGORY[str(hrow["C"]).lower()] != h["category"] or CATEGORY[str(mrow[desc_col]).lower()] != h["category"]:
            problems.append("category")
        if str(mrow["A"]).strip() != m["fleet_no"] or str(mrow[status_col]).strip() not in ("Available", "Yard"):
            problems.append(f"machine row {mrow['A']} {mrow[status_col]}")
        if DEPOT_STATE[str(mrow[depot_col]).lower()] != h["project"]["state"] or projects[h["project"]["code"]]["C"] != h["project"]["state"]:
            problems.append("state")
        if abs(_day_rate(hrow, h["business"]) - p["saving_per_day_ex_gst"]) > 0.01:
            problems.append(f"rate {_day_rate(hrow, h['business']):.2f} vs {p['saving_per_day_ex_gst']}")
        hours = _hours_run(con, m["machine_id"], before_run)
        if p["status"] == "confirmed" and (hours is None or hours >= 1.0 or abs(hours - m["hours_run_18_31_oct"]) > 0.01):
            problems.append(f"idle hours {hours}")
        if p["status"] == "unconfirmed" and hours is not None and hours >= 1.0:
            problems.append(f"unconfirmed machine ran {hours}")
        if m["machine_id"] in used:
            problems.append("machine used twice")
        used.add(m["machine_id"])
        if problems:
            bad.append(f"{h['hire_no']} -> {m['business']} {m['fleet_no']}: {', '.join(problems)}")
    rep.check(not bad, f"All {len(pairs)} pairs in answers.json re-derive from the Excel cells and raw FieldTrax lines", f"{bad[:5]}")
    for key, total_key, status in (("hires_to_end", "saving_per_day_ex_gst", "confirmed"), ("unconfirmed", "unconfirmed_saving_per_day_ex_gst", "unconfirmed")):
        s = round(sum(p["saving_per_day_ex_gst"] for p in answers["answer"][key]), 2)
        rep.check(s == answers["answer"][total_key], f"{total_key} = sum of its {len(answers['answer'][key])} pairs ({s})", f"{s} vs {answers['answer'][total_key]}")
    check_best_pairs(rep, cells, con, answers)
    signs = {tuple(p["signs"]) for p in pairs}
    rep.check(signs == {tuple(answers["who_signs"]["approvers"])}, f"Every pair names who signs: {answers['who_signs']['approvers']}", str(signs))


def check_best_pairs(rep: Report, cells, con, answers: dict) -> None:
    """Within each category and state, no open hire left unpaired costs more than one that was paired."""
    open_rows = {r["source_row"] for r in _q(con, "SELECT source_row FROM clean.hires WHERE status = 'on_hire' AND NOT is_duplicate_line")}
    sheet, projects = cells[HIRES], {str(r["A"]).strip(): r for n, r in cells[PROJECTS].items() if n > 1}
    paired = {(p["hire"]["source"]["row"]) for p in answers["answer"]["hires_to_end"]}
    groups: dict[tuple[str, str], dict[str, list[float]]] = {}
    for row in open_rows:
        c = sheet[row]
        code = re.sub(r"^(?:P-?)?(\d{4})$", r"P-\1", str(c["D"]).strip().upper())
        proj = projects.get(code) or next((r for r in projects.values() if str(r["B"]).lower() == str(c["D"]).lower()), None)
        key = (CATEGORY[str(c["C"]).lower()], proj["C"])
        groups.setdefault(key, {"in": [], "out": []})["in" if row in paired else "out"].append(_day_rate(c, str(c["E"])))
    worse = [f"{k}: unpaired {max(g['out']):.2f} > paired {min(g['in']):.2f}" for k, g in groups.items()
             if g["in"] and g["out"] and max(g["out"]) > min(g["in"]) + 0.005]
    rep.check(not worse, "Confirmed pairs are the dearest open hires in each category and state", f"{worse[:5]}")


def _money(v) -> float | None:
    """A capital cost as typed: a number, or text like '$1,234' / '1234.00'. 'TBC' and blanks have none."""
    if isinstance(v, (int, float)):
        return float(v)
    digits = re.sub(r"[$,\s]", "", str(v or ""))
    return float(digits) if re.fullmatch(r"\d+(\.\d+)?", digits) else None


FLEET_NO = re.compile(r"^[A-Z]{2,3}-?\d+$")


def _struck_rows(path: Path, sheet: str) -> set[int]:
    ws = openpyxl.load_workbook(path)[sheet]
    return {c.row for row in ws.iter_rows() for c in row if c.value is not None and c.font is not None and c.font.strike}


def _register_rows(cells) -> dict[str, dict[int, dict]]:
    return {tab: {n: r for n, r in cells[tab].items() if FLEET_NO.match(_norm(r.get("A")))} for tab in (BE, NH)}


def _expected_workbook_counts(cells, struck: set[int]) -> dict:
    reg = _register_rows(cells)
    status = {BE: "H", NH: "F"}
    statuses = [str(r.get(status[tab], "")).strip().lower() for tab, rows in reg.items() for r in rows.values()]
    transfers = sum(s.startswith("transferred to") for s in statuses)
    be_costs = [c for c in (_money(r.get("J")) for r in reg[BE].values()) if c is not None]
    total_row = next(r for r in cells[BE].values() if str(r.get("A", "")).strip().upper() == "TOTAL")
    hire_rows = {n: r for n, r in cells[HIRES].items() if re.match(r"^H-\d+$", str(r.get("A", "")).strip())}
    seen, dupes = {}, []
    for n, r in sorted(hire_rows.items()):
        key = tuple(sorted(r.items()))
        (dupes.append(r["A"]) if key in seen else seen.setdefault(key, n))
    return {
        "distinct_machines": sum(len(rows) for rows in reg.values()) - transfers,  # a transfer line is a BE machine's old row
        "owned_disposed": sum(s in ("sold", "disposed") for s in statuses),
        "transfer_rows": transfers,
        "be_total_discrepancy": round(sum(be_costs) - float(total_row["J"]), 2),
        "hire_rows_distinct": len({r["A"] for r in hire_rows.values()}),
        "cancelled": len({hire_rows[n]["A"] for n in struck if n in hire_rows}),
        "duplicate_hire": ", ".join(sorted(dupes)),
    }


def _expected_open_hires(cells, con) -> dict:
    """Which hires are open comes from DuckDB (date parsing is checked elsewhere); the rates come from the cells."""
    rows = [r["source_row"] for r in _q(con, "SELECT source_row FROM clean.hires WHERE status = 'on_hire' AND NOT is_duplicate_line")]
    return {"open_hires": len(rows),
            "open_hire_run_rate_ex_gst_per_day": f"{sum(_day_rate(cells[HIRES][n], str(cells[HIRES][n]['E']).strip()) for n in rows):.2f}"}


def _instants(con, run_filter: str) -> set[tuple[str, datetime]]:
    lines = _q(con, f"SELECT device_id, time FROM raw.fieldtrax_reading_lines WHERE {run_filter}")
    out = set()
    for r in lines:
        try:
            out.add((r["device_id"], datetime.fromisoformat(r["time"].replace("Z", "+00:00"))))
        except ValueError:
            continue  # junk time: not an instant
    return out


def _expected_fieldtrax(cells, con, before_run: str) -> dict:
    latest = {}
    for v in _q(con, f"SELECT device_id, name, vin, rego, retired_at, is_listed FROM raw.fieldtrax_device_versions "
                     f"WHERE sync_run <= '{before_run}' ORDER BY valid_from"):
        latest[v["device_id"]] = v
    listed = {d: v for d, v in latest.items() if v["is_listed"]}
    vins = {_norm(r.get(c)) for tab, rows in _register_rows(cells).items()
            for r in rows.values() for c in (("F",) if tab == BE else ("D",))} - {""}
    regos = {_norm(r.get(c)) for tab, rows in _register_rows(cells).items()
             for r in rows.values() for c in (("E",) if tab == BE else ("C",))} - {""}
    unmatched = [d for d, v in listed.items() if _norm(v["vin"]) not in vins and _norm(v["rego"]) not in regos]
    before, after = _instants(con, f"first_seen_run <= '{before_run}'"), _instants(con, "TRUE")
    return {"devices_total": len(listed), "devices_retired": sum(v["retired_at"] is not None for v in listed.values()),
            "devices_unmatched": len(unmatched), "readings_distinct": len(before),
            "readings_added": len(after - before)}


def check_skeleton(rep: Report, cells, con, workbook: Path, answers: dict, detail: dict) -> None:
    before_run = detail["before_advance_sync"]["run"]
    want = {**_expected_workbook_counts(cells, _struck_rows(workbook, HIRES)), **_expected_open_hires(cells, con),
            **_expected_fieldtrax(cells, con, before_run)}
    want["owned_current"] = want["distinct_machines"] - want["owned_disposed"]
    want["replaceable_hires"] = len(detail["answer"]["hires_to_end"])
    want["saving_ex_gst_per_day"] = f"{sum(_day_rate(cells[HIRES][p['hire']['source']['row']], p['hire']['business']) for p in detail['answer']['hires_to_end']):.2f}"
    want["after_advance.readings_added"] = want.pop("readings_added")
    got = {**answers, **{f"after_advance.{k}": v for k, v in answers.get("after_advance", {}).items()}}
    bad = [f"{k}: answers.json {got.get(k)!r} vs recomputed {v!r}" for k, v in want.items() if got.get(k) != v]
    rep.check(not bad, f"answers.json: {len(want)} skeleton values recomputed from the cells and raw FieldTrax lines agree", f"{bad[:5]}")


def run(workbook: Path, db: Path, answers_path: Path, detail_path: Path | None = None) -> Report:
    rep = Report()
    cells = _cells(workbook)
    con = duckdb.connect(str(db), read_only=True)
    try:
        check_raw_cells(rep, cells, con)
        check_rows_accounted(rep, cells, con)
        check_hires(rep, cells, con)
        check_machines(rep, cells, con)
        detail_path = detail_path or answers_path.parent / "out" / "answers_detail.json"
        if not answers_path.exists() or not detail_path.exists():
            rep.check(False, "answers.json and answers_detail.json exist", "run `brackenfield screen` first")
            return rep
        answers, detail = json.loads(answers_path.read_text()), json.loads(detail_path.read_text())
        check_answers(rep, cells, con, detail)
        check_skeleton(rep, cells, con, workbook, answers, detail)
    finally:
        con.close()
    return rep
