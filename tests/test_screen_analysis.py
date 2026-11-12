from datetime import UTC, date, datetime

import polars as pl

from brackenfield.screen import analysis as an

AS_OF = date(2026, 10, 31)


def test_idle_window_is_18_to_31_october_aest():
    start, end = an.idle_window(AS_OF)

    assert start.astimezone(UTC) == datetime(2026, 10, 17, 14, 0, tzinfo=UTC)
    assert end.astimezone(UTC) == datetime(2026, 10, 31, 13, 59, 59, tzinfo=UTC)


def _inputs(readings: pl.DataFrame, devices: pl.DataFrame) -> an.Inputs:
    machines = pl.DataFrame({
        "machine_id": ["m_idle", "m_busy", "m_nodev"], "business_code": ["BE"] * 3, "fleet_no": ["EX-01", "EX-02", "EX-03"],
        "category": ["Excavator 20t"] * 3, "site_id": ["s"] * 3, "source_tab": ["BE Plant"] * 3, "source_row": [5, 6, 7],
        "status": ["available"] * 3, "make": [None] * 3, "model": [None] * 3, "source_refs": [""] * 3,
    })
    return an.Inputs(as_of=AS_OF, hires=pl.DataFrame(), projects=pl.DataFrame(), machines=machines,
                     sites=pl.DataFrame({"site_id": ["s"], "name": ["Toowoomba"], "state": ["QLD"]}),
                     devices=devices, readings=readings, issues=pl.DataFrame(), organizations=pl.DataFrame())


def test_idle_needs_under_one_hour_summed_across_devices_and_a_device_at_all():
    t = lambda d, h: datetime(2026, 10, d, h, tzinfo=UTC)  # noqa: E731
    readings = pl.DataFrame({
        "device_id": ["a", "a", "a", "b1", "b1", "b2", "b2"],
        "machine_id": ["m_idle"] * 3 + ["m_busy"] * 4,
        "time_utc": [t(20, 0), t(21, 0), t(22, 0), t(20, 0), t(21, 0), t(20, 0), t(21, 0)],
        # m_idle: +0.4 then a reset (ignored). m_busy: 0.6 on each of two devices = 1.2 h.
        "engine_hours": [100.0, 100.4, 0.0, 50.0, 50.6, 10.0, 10.6],
    }).with_columns(pl.col("time_utc").cast(pl.Datetime("us", "UTC")))
    devices = pl.DataFrame({"device_id": ["a", "b1", "b2"], "machine_id": ["m_idle", "m_busy", "m_busy"]})
    lines = pl.DataFrame({"source_tab": ["BE Plant"] * 3, "source_row": [5, 6, 7], "status_raw": ["Available", "Yard", "Available"]})

    out = an.machine_evidence(_inputs(readings, devices), lines).sort("machine_id")

    status = dict(zip(out["machine_id"], out["idle_status"]))
    hours = dict(zip(out["machine_id"], out["hours_run"]))
    assert status == {"m_busy": "working", "m_idle": "confirmed", "m_nodev": "unconfirmed"}
    assert round(hours["m_idle"], 2) == 0.4 and round(hours["m_busy"], 2) == 1.2


def test_matching_gives_idle_machines_to_the_dearest_hires_in_the_same_state():
    hires = pl.DataFrame({
        "source_row": [2, 3, 4, 5], "category": ["Tipper"] * 4, "project_state": ["QLD", "QLD", "NSW", "QLD"],
        "day_rate_ex_gst": [900.0, 1200.0, 2000.0, 1000.0], "is_duplicate_line": [False] * 4,
    }).sort("day_rate_ex_gst", descending=True)
    machines = pl.DataFrame({
        "machine_id": ["m1", "m2"], "category": ["Tipper", "Tipper"], "state": ["QLD", "QLD"],
        "idle_status": ["confirmed", "confirmed"], "business_code": ["BE", "BE"], "fleet_no": ["TP-01", "TP-02"],
    })

    pairs = an.match(hires, machines)

    assert set(pairs) == {3, 5}  # the two dearest QLD hires; the NSW one is out of state


def test_before_advance_label_wins_over_inference():
    from brackenfield.screen.build import advance_boundary

    syncs = pl.DataFrame({"run_id": ["r1", "r2", "r3", "r4"], "new_readings": [10, 0, 5, 0], "new_device_versions": [3, 0, 1, 0]})

    inferred = advance_boundary(syncs)
    labelled = advance_boundary(syncs, {"before_advance": "r1"})
    no_advance = advance_boundary(syncs.head(2))

    assert inferred[:2] == ("r2", "r4") and inferred[2].startswith("inferred")
    assert labelled == ("r1", "r4", "labelled before_advance")
    assert no_advance[0] == no_advance[1] == "r2"
