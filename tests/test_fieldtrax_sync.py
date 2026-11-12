"""The FieldTrax connector end to end: idempotent re-runs, change reporting, junk data, outages."""

from dataclasses import replace

import duckdb
import httpx
import pytest

from brackenfield.config import FieldTraxSettings, Settings
from brackenfield.pipeline import run

EX01 = {"id": "ftx_ex01", "name": "BE EX-01 Komatsu", "vin": "CPS7RLGCURFR7M10S", "rego": "BK101V", "retired_at": None, "unit": "h"}
MX03 = {"id": "ftx_mx03", "name": "NH MX-03 Kubota", "vin": "DHWA0WJ66KRHB7CAA", "rego": "BN167U", "retired_at": None, "unit": "h"}
TP06 = {"id": "ftx_tp06", "name": "NH TP-06 Hino", "vin": "BMU1DPD5T3ZB8ZFF3", "rego": "CK184T", "retired_at": None, "unit": "s"}
SPARE = {"id": "ftx_spare", "name": "Spare tracker 1", "vin": "S0SC01RFB9VEG4A01", "rego": "ZZZ0", "retired_at": None, "unit": "h"}


def reading(time: str, value, unit: str = "h") -> dict:
    return {"time": time, "metric": "engine_hours", "value": value, "unit": unit}


class FakeFieldTrax:
    """Deterministic stand-in for the kit's API; tests mutate devices/readings between runs."""

    def __init__(self):
        self.devices = [EX01, MX03, TP06, SPARE]
        self.readings = {
            "ftx_ex01": [reading("2026-10-03T22:00:00Z", 5030.3), reading("2026-10-04T18:00:00+10:00", 5038.2)],
            "ftx_mx03": [reading("2026-10-03T22:00:00Z", 100.0)],
            "ftx_tp06": [reading("2026-10-03T22:00:00Z", 3600000, "s")],
            "ftx_spare": [],
        }
        self.down = False
        self.junk_pages_left = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            return httpx.Response(503, json={"error": "upstream_unavailable"})
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "tok"})
        if self.junk_pages_left:
            self.junk_pages_left -= 1
            return httpx.Response(200, text="<html>gateway hiccup</html>")
        if request.url.path == "/v2/assets":
            return httpx.Response(200, json={"items": self.devices, "next_cursor": None})
        device_id = request.url.path.split("/")[3]
        if device_id not in self.readings:
            return httpx.Response(404, json={"error": "not_found"})
        return httpx.Response(200, json={"items": self.readings[device_id], "next_cursor": None})


@pytest.fixture
def env(tmp_path):
    api = FakeFieldTrax()
    settings = replace(
        Settings(), database_path=tmp_path / "t.duckdb", export_dir=tmp_path / "out", docs_dir=tmp_path / "docs",
        fieldtrax=FieldTraxSettings(base_url="http://fieldtrax.test", client_id="c", client_secret="s", max_retries=3),
    )
    sync = lambda: run(settings, transport=httpx.MockTransport(api))  # noqa: E731
    return api, settings, sync


def q(settings, sql):
    con = duckdb.connect(str(settings.database_path), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def raw_counts(settings):
    return q(settings, "SELECT (SELECT count(*) FROM raw.fieldtrax_device_versions), (SELECT count(*) FROM raw.fieldtrax_reading_lines)")


def test_second_run_changes_nothing(env):
    api, settings, sync = env
    first = sync()
    raw_after_first = raw_counts(settings)

    second = sync()

    assert first.change_summary["devices"] == {"added": 4}
    assert second.change_summary == {}
    assert raw_counts(settings) == raw_after_first
    assert second.sync.counts["new_readings"] == 0 and second.sync.counts["new_device_versions"] == 0
    assert "Nothing. Every clean record is identical" in (settings.export_dir / "changes.md").read_text()


def test_advance_reports_exactly_what_changed(env):
    api, settings, sync = env
    sync()
    sync()
    api.devices = [{**EX01}, {**TP06, "name": "NH TP-06 Hino - reassigned"}, SPARE,
                   {"id": "ftx_sk05", "name": "BE SK-05 Bobcat", "vin": "RPUH6PNV5UUEFYY5L", "rego": "FR121U", "retired_at": None, "unit": "h"}]
    api.readings["ftx_ex01"].append(reading("2026-10-31T22:00:00Z", 5187.9))
    api.readings["ftx_sk05"] = [reading("2026-10-31T22:00:00Z", 10.0)]

    third = sync()

    changes = q(settings, f"""SELECT table_name, change_type, record_key, field, old_value, new_value FROM meta.record_changes
                              WHERE run_id = '{third.run_id}' AND table_name = 'devices' AND (field IS NULL OR field IN ('name', 'is_listed'))
                              ORDER BY 1, 2, 3, 4""")
    assert changes == [
        ("devices", "added", "ftx_sk05", None, None, None),
        ("devices", "changed", "ftx_mx03", "is_listed", "true", "false"),
        ("devices", "changed", "ftx_tp06", "name", "NH TP-06 Hino", "NH TP-06 Hino - reassigned"),
    ]
    assert third.change_summary["readings"] == {"added": 2}
    assert q(settings, "SELECT machine_id, link_method FROM clean.devices WHERE device_id = 'ftx_sk05'") == [("mch_rpuh6pnv5uuefyy5l", "vin")]
    assert q(settings, "SELECT count(*) FROM clean.readings WHERE device_id = 'ftx_mx03'") == [(1,)]  # kept


def test_unmatched_devices_are_reported(env):
    _, settings, sync = env

    sync()

    assert q(settings, "SELECT device_id FROM clean.devices WHERE machine_id IS NULL") == [("ftx_spare",)]
    assert q(settings, "SELECT entity_key FROM dq.priya_list WHERE check_id = 'DV002'") == [("ftx_spare",)]
    report = (settings.export_dir / "changes.md").read_text()
    assert "### Devices that match nothing (1)" in report and "Spare tracker 1" in report


def test_junk_items_are_kept_and_reported_not_fatal(env):
    api, settings, sync = env
    api.devices = api.devices + [{"name": "no id at all"}]
    api.readings["ftx_ex01"] += [reading("yesterday", 1.0), reading("2026-10-05T08:00:00Z", "n/a"), reading("2026-10-06T08:00:00Z", 1, "min")]
    api.junk_pages_left = 1

    result = sync()

    assert result.fieldtrax_refreshed and result.sync.stats["bad_pages"] == 1
    rejected = q(settings, "SELECT check_id, raw_value FROM dq.issues WHERE check_id = 'DV009'")
    assert rejected == [("DV009", '{"name": "no id at all"}')]
    unreadable = q(settings, "SELECT message FROM dq.issues WHERE check_id = 'RD007' ORDER BY 1")
    assert [m for (m,) in unreadable] == ["time yesterday is not ISO-8601 with an offset", "unit min is not h or s",
                                          "value n/a is not a number"]
    assert q(settings, "SELECT count(*) FROM clean.readings WHERE device_id = 'ftx_ex01'") == [(5,)]


def test_outage_keeps_previous_records_and_warns(env):
    api, settings, sync = env
    sync()
    api.down = True

    result = sync()

    assert not result.fieldtrax_refreshed
    assert result.change_summary == {}
    assert q(settings, "SELECT count(*) FROM dq.issues WHERE check_id = 'DV001'") == [(1,)]  # data team sees it
    assert q(settings, "SELECT count(*) FROM dq.priya_list WHERE check_id = 'DV001'") == [(0,)]  # Priya doesn't
    assert "Not refreshed this run" in (settings.export_dir / "changes.md").read_text()


def test_label_pins_the_pre_advance_sync_and_rejects_runs_without_one(env):
    from brackenfield import load

    api, settings, sync = env
    before = run(settings, transport=httpx.MockTransport(api), label="before_advance")
    api.readings["ftx_ex01"].append(reading("2026-10-31T22:00:00Z", 5187.9))
    skipped = run(settings, skip_fieldtrax=True, label="before_advance")  # no sync: must not move the label

    assert q(settings, "SELECT run_id FROM meta.run_labels WHERE label = 'before_advance'") == [(before.run_id,)]
    with load.connect(settings.database_path) as con, pytest.raises(load.LabelError):
        load.label_run(con, "before_advance", skipped.run_id)


def test_a_running_unmatched_tracker_is_flagged_for_priya(env):
    api, settings, sync = env
    api.readings["ftx_spare"] = [reading("2026-10-20T22:00:00Z", 100.0), reading("2026-10-21T08:00:00Z", 106.5)]

    sync()

    hits = q(settings, "SELECT entity_key, message FROM dq.priya_list WHERE check_id = 'DV012'")
    assert len(hits) == 1 and hits[0][0] == "ftx_spare" and "6.5 h" in hits[0][1]
