"""Open questions for Priya, built from the data so they stay true when the data changes.

Two groups:
  answer  the reply could change today's answer (which hires, how much a day)
  other   worth knowing, but today's answer does not depend on it
Each question carries the records behind it, what it does to the answer, and what we need.
"""

from __future__ import annotations

import re

import polars as pl

from brackenfield.screen import analysis as an


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _swaps(hires: list[dict]) -> list[dict]:
    return [h for h in hires if h["outcome"] in ("end_confirmed", "end_unconfirmed")]


def _q(qid, group, title, finding, effect, ask, *, per_day=None, hire_rows=(), machine_ids=(), refs=()) -> dict:
    return {"id": qid, "group": group, "title": title, "finding": finding, "effect": effect, "ask": ask,
            "effect_per_day": None if per_day is None else round(per_day, 2), "hire_rows": list(hire_rows),
            "machine_ids": list(machine_ids), "refs": list(refs)}


def sign_off(hires: list[dict], rule: dict | None) -> dict | None:
    """Only an open question while nobody is named to sign."""
    if rule and rule.get("approvers"):
        return None
    swaps = _swaps(hires)
    total = sum(h["day_ex"] for h in swaps)
    return _q("sign_off", "answer", "Who signs off ending a hire?",
              "Nothing in the register, the READ ME or FieldTrax says who approves ending a hire.",
              f"Blocks every proposal: {len(swaps)} hires, {_money(total)} a day.",
              "The approver (or rule, e.g. by business or by value) for ending a hire.",
              per_day=total, hire_rows=[h["row"] for h in swaps])


def available_but_working(hire_frame: pl.DataFrame, machines: pl.DataFrame, readings: pl.DataFrame, current: dict[int, str],
                          hires: list[dict]) -> dict | None:
    working = machines.filter(pl.col("idle_status") == "working")
    if working.is_empty():
        return None
    if_idle = an.match(hire_frame, machines.with_columns(
        pl.when(pl.col("idle_status") == "working").then(pl.lit("confirmed")).otherwise(pl.col("idle_status")).alias("idle_status")))
    extra_rows = sorted(set(if_idle) - set(current))
    rate = {h["row"]: h["day_ex"] for h in hires}
    extra = sum(rate[r] for r in extra_rows)
    drops = readings.filter(pl.col("machine_id").is_in(working["machine_id"].to_list()), pl.col("hours_delta") < -1)
    hrs = working["hours_run"]
    weekly = (hrs / 2).median()  # the window is two weeks
    reset_text = ""
    if drops.height:
        days = sorted({t.astimezone(an.AEST).strftime("%-d %b") for t in drops["time_utc"].to_list()})
        reset_text = f" {drops['machine_id'].n_unique()} of them had an hour meter reset on {' and '.join(days)}."
    return _q("available_but_working", "answer", "Are these machines really Available?",
              f"{working.height} machines are Available on the register, but FieldTrax shows {hrs.min():.0f}–{hrs.max():.0f} h run "
              f"from 18 to 31 Oct, about {weekly:.0f} h a week, like machines out on jobs.{reset_text}",
              f"If the register is right and they are idle, {len(extra_rows)} more hires could end: +{_money(extra)} a day. "
              "As it stands they are not offered.",
              "For each: is it in the yard, or out working? If working, which job, so the register can be updated.",
              per_day=extra, hire_rows=extra_rows, machine_ids=working["machine_id"].to_list())


def no_tracker(hires: list[dict], machines: pl.DataFrame) -> dict | None:
    unconf = machines.filter(pl.col("idle_status") == "unconfirmed")
    if unconf.is_empty():
        return None
    affected = [h for h in hires if h["outcome"] == "end_unconfirmed"]
    total = sum(h["day_ex"] for h in affected)
    names = ", ".join(f"{m['business_code']} {m['fleet_no']}" for m in unconf.iter_rows(named=True))
    return _q("no_tracker", "answer", "Are these machines idle? FieldTrax can't tell us.",
              f"{names} are Available, but have no FieldTrax data for 18–31 Oct, so they can't be confirmed idle.",
              f"{len(affected)} hires ({_money(total)} a day) depend on them and are shown as unconfirmed.",
              "Confirm each is sitting in the yard and fit to go out.",
              per_day=total, hire_rows=[h["row"] for h in affected], machine_ids=unconf["machine_id"].to_list())


def duplicate_hire(hires: list[dict], machines: pl.DataFrame) -> dict | None:
    dups = [h for h in hires if h["outcome"] == "duplicate"]
    if not dups:
        return None
    h = dups[0]
    used = {x["machine_id"] for x in _swaps(hires)}
    spare = machines.filter(pl.col("idle_status") != "working", ~pl.col("machine_id").is_in(list(used)),
                            pl.col("category") == h["category"], pl.col("state") == h["state"])
    tail = (f"An idle {h['category'].lower()} is still free in {h['state']}." if spare.height
            else f"No idle {h['category'].lower()} is left in {h['state']} to replace it.")
    return _q("duplicate_hire", "answer", f"Is {h['hire_no']} one hire or two?",
              f"{h['hire_no']} is on rows {h['duplicate_of_row']} and {h['row']} of Hires 25-26, identical in every cell. Counted once.",
              f"If it is two machines, another {_money(h['day_ex'])} a day is on hire. {tail}",
              "One hire entered twice (we'll mark the second line), or two machines (it needs its own hire number).",
              per_day=h["day_ex"], hire_rows=[h["duplicate_of_row"], h["row"]])


def supplier_spelling(hires: list[dict], usage: pl.DataFrame) -> dict | None:
    rows = usage.filter(pl.col("domain") == "supplier", pl.col("basis") == "inferred")
    if rows.is_empty():
        return None
    r = rows.row(0, named=True)
    open_rows = [h["row"] for h in hires if h["supplier_raw"] == r["raw_value"]]
    return _q("supplier_spelling", "answer", f"Is '{r['raw_value']}' the same company as {r['canonical']}?",
              f"'{r['raw_value']}' is written as two words on {r['line_count']} lines. We read it as {r['canonical']}.",
              "Doesn't change the saving; it decides which supplier is asked to off-hire.",
              "Same company, or a different supplier?",
              hire_rows=open_rows, refs=[x for x in r["source_refs"].split(", ") if x not in {f"Hires 25-26!{n}" for n in open_rows}])


def blank_vin(hires: list[dict], machines: pl.DataFrame, issues: pl.DataFrame) -> dict | None:
    mc003 = issues.filter(pl.col("check_id") == "MC003")
    in_swaps = {h["machine_id"]: h for h in _swaps(hires)}
    hit = machines.filter(pl.col("machine_id").is_in(list(in_swaps))).join(
        mc003.select("source_tab", "source_row", "message"), on=["source_tab", "source_row"], how="inner")
    if hit.is_empty():
        return None
    m = hit.row(0, named=True)
    h = in_swaps[m["machine_id"]]
    others = mc003.filter((pl.col("source_tab") != m["source_tab"]) | (pl.col("source_row") != m["source_row"]))
    also = f" {others.height} other machines also have no VIN ({_names(others, 'entity_key')}); they aren't in any proposal." if others.height else ""
    return _q("blank_vin", "answer", f"What is {m['business_code']} {m['fleet_no']}'s VIN?",
              f"The register's VIN is blank. {m['message'].replace('VIN blank; ', '')}.{also}",
              f"It is the machine proposed for {h['hire_no']} ({_money(h['day_ex'])} a day). The tracker showing it idle is matched by rego only.",
              "Confirm the VIN so the register and the tracker agree.",
              hire_rows=[h["row"]], machine_ids=[m["machine_id"]])


def contract_terms(hires: list[dict]) -> dict:
    swaps = _swaps(hires)
    monthly = [h for h in swaps if (h["basis_raw"] or "").lower() in ("mth", "month", "monthly")]
    weekly = [h for h in swaps if (h["basis_raw"] or "").lower() in ("wk", "week", "weekly")]
    terms = f"{len(weekly)} of the hires to end are on weekly rates" + (f" and {len(monthly)} on monthly" if monthly else "") + "."
    return _q("contract_terms", "answer", "What notice or minimum hire do the suppliers need?",
              f"Notice periods and minimum hire terms aren't in the register. {terms}",
              "The day saving may start later than the day a hire ends; a weekly or monthly hire may be charged to the end of its period.",
              "Each supplier's notice period and minimum hire, or where the contracts are kept.",
              hire_rows=[h["row"] for h in monthly + weekly] or [h["row"] for h in swaps])


def _num(text: str, i: int) -> float:
    return float(re.findall(r"[\d.]+", text)[i])


def _names(hits: pl.DataFrame, column: str = "raw_value") -> str:
    vals = [v for v in hits[column].to_list() if v]
    return ", ".join(vals[:-1]) + (" and " if len(vals) > 1 else "") + vals[-1] if vals else ""


def _finding(check_id: str, hits: pl.DataFrame) -> str:
    if check_id == "WB009":
        msg = hits["message"][0]
        typed, lines = _num(msg, 0), _num(msg, 1)
        return (f"The typed BE total is {_money(typed)}; the machine lines add up to {_money(lines)} "
                f"({_money(lines - typed)} more). The typed subtotals agree with the lines.")
    if check_id == "MC009":
        return f"Capital cost says TBC for BE {_names(hits, 'entity_key')}."
    if check_id == "MC012":
        return f"BE {_names(hits, 'entity_key')} are Disposed, but their Year is 2026."
    if check_id == "DV002":
        return f"{hits.height} trackers ({_names(hits)}) match no machine on the register."
    if check_id == "MC015":
        pairs = list(dict.fromkeys(hits["message"].str.replace(" share this operator mobile", "").to_list()))
        mobiles = list(dict.fromkeys(hits["raw_value"].to_list()))
        return " ".join(f"{p} share operator mobile {n}." for p, n in zip(pairs, mobiles)) + " (Hidden column K on BE Plant.)"
    if check_id == "VC001":
        parts = [f"'{r['raw_value']}' ({_num(r['message'], 0) if False else r['message'].split(' on ')[1].split(' line')[0]} lines)"
                 for r in hits.iter_rows(named=True)]
        return f"NH writes {' and '.join(parts)}. We read them as On project and Workshop."
    return " ".join(dict.fromkeys(hits["message"].to_list()[:3]))


OTHER_CHECKS = {
    "WB009": ("Which BE total is right?", "Which figure should the BE register total show?"),
    "MC009": ("What did these machines cost?", "The capital cost for each machine marked TBC."),
    "MC012": ("Built and disposed in 2026?", "Is the Year or the Status wrong on these lines?"),
    "VC001": ("Do 'On job' and 'Repairs' mean On project and Workshop?", "Confirm how NH's status words map to BE's."),
    "MC015": ("Is one operator on two machines?", "Is it the same operator on both, or has a number been copied across?"),
}


def other_findings(issues: pl.DataFrame) -> list[dict]:
    out = []
    for check_id, (title, ask) in OTHER_CHECKS.items():
        hits = issues.filter(pl.col("check_id") == check_id, pl.col("for_priya"))
        if check_id == "VC001":
            hits = hits.filter(pl.col("raw_value").is_in(["On job", "Repairs"]))
        if hits.is_empty():
            continue
        refs = [f"{r['source_tab']}!{r['source_row']}" if r["source_row"] is not None else (r["entity_key"] or "")
                for r in hits.iter_rows(named=True)]
        out.append(_q(check_id, "other", title, _finding(check_id, hits), "Doesn't change today's answer.", ask, refs=refs))
    return out


ACTIVE_STATUSES = ("available", "on_project", "workshop")


def untracked_machines(inp: an.Inputs) -> pl.DataFrame:
    """Machines in use or Available with no FieldTrax device, in this view's FieldTrax data."""
    tracked = inp.devices.filter(pl.col("machine_id").is_not_null()).select("machine_id").unique()
    return inp.machines.filter(pl.col("status").is_in(ACTIVE_STATUSES)).join(tracked, on="machine_id", how="anti").sort(
        "business_code", "fleet_no")


def running_spares(inp: an.Inputs) -> pl.DataFrame:
    """Devices matching no machine that ran 1 h or more in the idle window, in this view's data."""
    start, end = an.idle_window(inp.as_of)
    spares = inp.devices.filter(pl.col("machine_id").is_null()).select("device_id", "name")
    window = inp.readings.join(spares, on="device_id", how="inner").filter(
        pl.col("time_utc") >= start, pl.col("time_utc") <= end, pl.col("engine_hours").is_not_null())
    ran = window.sort("device_id", "time_utc").with_columns(pl.col("engine_hours").diff().over("device_id").alias("step")).group_by(
        "device_id", "name").agg(pl.col("step").filter(pl.col("step") > 0).sum().alias("hours"), pl.col("time_utc").min().alias("first"))
    return ran.filter(pl.col("hours") >= 1.0).sort("name")


def _labels(frame: pl.DataFrame, joiner: str = "and") -> str:
    vals = [f"{r['business_code']} {r['fleet_no']}" for r in frame.iter_rows(named=True)]
    return ", ".join(vals[:-1]) + (f" {joiner} " if len(vals) > 1 else "") + vals[-1] if vals else ""


def spare_trackers(inp: an.Inputs, hires: list[dict], machines: pl.DataFrame) -> dict | None:
    spares = running_spares(inp)
    if spares.is_empty():
        return None
    unconf = machines.filter(pl.col("idle_status") == "unconfirmed")
    at_risk = [h for h in hires if h["outcome"] == "end_unconfirmed"]
    total = sum(h["day_ex"] for h in at_risk)
    hours = [f"{h:.1f}" for h in spares["hours"].to_list()]
    since = min(spares["first"].to_list()).astimezone(an.AEST).strftime("%-d %b")
    others = untracked_machines(inp).join(unconf.select("machine_id"), on="machine_id", how="anti")
    names = ", ".join(spares["name"].to_list()[:-1]) + " and " + spares["name"][-1] if spares.height > 1 else spares["name"][0]
    return _q("spare_trackers", "answer", "What are the spare trackers fitted to?",
              f"{names} match no machine on the register, but ran {', '.join(hours[:-1]) + ' and ' if len(hours) > 1 else ''}{hours[-1]} h "
              f"between 18 and 31 Oct (reporting since {since}). Each is fitted to something that is working.",
              f"If one is on {_labels(unconf, 'or')} (Available, no FieldTrax data of their own), that machine is working and its "
              f"proposal falls away: up to {_money(total)} a day." + (f" {others.height} other machines in use have no tracker either." if others.height else ""),
              "Which machine each spare tracker is fitted to, so FieldTrax can be linked to the register.",
              per_day=total, hire_rows=[h["row"] for h in at_risk], machine_ids=unconf["machine_id"].to_list(),
              refs=spares["device_id"].to_list())


def no_tracker_finding(inp: an.Inputs) -> dict | None:
    missing = untracked_machines(inp)
    if missing.is_empty():
        return None
    return _q("MC014", "other", "Should these machines have trackers?",
              f"{missing.height} machines in use or Available have no FieldTrax device: {_labels(missing)}.",
              "Doesn't change today's answer.", "Are generators tracked? Are the others missing a device?",
              refs=[f"{r['source_tab']}!{r['source_row']}" for r in missing.iter_rows(named=True)])


def _swap_text(hire_no: str, message: str) -> str:
    m = re.match(r"(Start|Off-hire) (\d+ \w+) \d+ \((.*?)\); read month-first it is (\d+ \w+)", message)
    return f"{hire_no} {m.group(1).lower()} {m.group(2)} would be {m.group(4)} ({m.group(3)})" if m else f"{hire_no}: {message}"


def date_order(hires: list[dict], issues: pl.DataFrame) -> dict | None:
    hits = issues.filter(pl.col("check_id") == "HR016")
    if hits.is_empty():
        return None
    by_row = {h["row"]: h for h in hires}
    rows = hits["source_row"].to_list()
    in_proposals = [by_row[r] for r in rows if r in by_row and by_row[r]["outcome"] in ("end_confirmed", "end_unconfirmed")]
    total = sum(h["day_ex"] for h in in_proposals)
    effect = (f"{len(in_proposals)} of them are in proposals ({', '.join(h['hire_no'] for h in in_proposals)}, {_money(total)} a day). "
              "If their dates were entered month-first, those hires were not open on 31 Oct and drop out of the answer."
              if in_proposals else "None is in a proposal, but each would change whether the hire is open on 31 Oct.")
    return _q("date_order", "answer", "Were these dates entered day-first?",
              f"Dates are read day-first (2/4/26 = 2 Apr). Read month-first, {hits.height} dates would change whether a hire is "
              "open on 31 Oct: " + "; ".join(_swap_text(k, m) for k, m in zip(hits["entity_key"], hits["message"])) + ".",
              effect, "Confirm these were entered day-first (Australian), or correct them.",
              per_day=total or None, hire_rows=rows)


def build(inp: an.Inputs, hire_frame: pl.DataFrame, machines: pl.DataFrame, matches: dict[int, str],
          hires: list[dict], usage: pl.DataFrame, sign_off_rule: dict | None = None) -> list[dict]:
    answer = [
        sign_off(hires, sign_off_rule),
        available_but_working(hire_frame, machines, inp.readings, matches, hires),
        no_tracker(hires, machines),
        spare_trackers(inp, hires, machines),
        date_order(hires, inp.issues),
        duplicate_hire(hires, machines),
        blank_vin(hires, machines, inp.issues),
        supplier_spelling(hires, usage),
        contract_terms(hires),
    ]
    other = other_findings(inp.issues)
    tracker_gap = no_tracker_finding(inp)
    if tracker_gap:
        other.insert(3, tracker_gap)
    return [q for q in answer if q] + other
