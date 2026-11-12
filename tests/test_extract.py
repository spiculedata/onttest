import json

import httpx
import openpyxl
import pytest
from openpyxl.comments import Comment
from openpyxl.styles import Font

from brackenfield.config import FieldTraxSettings
from brackenfield.extract.fieldtrax import FieldTraxClient, FieldTraxError
from brackenfield.extract.workbook import WorkbookReadError, read_workbook


@pytest.fixture
def tricky_workbook(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Visible"
    ws.append(["Code", "Value"])
    ws.append(["A", 1])
    ws.append(["B", 2.0])
    for cell in ws[3]:
        cell.font = Font(strike=True)
    ws["B2"].comment = Comment("look at me", "someone")
    ws.column_dimensions["B"].hidden = True
    hidden = wb.create_sheet("_secret")
    hidden.sheet_state = "hidden"
    hidden["A1"] = "still read"
    path = tmp_path / "tricky.xlsx"
    wb.save(path)
    return path


def test_reads_hidden_tabs_hidden_columns_strike_and_comments(tricky_workbook):
    extract = read_workbook(tricky_workbook)

    sheets = {r["sheet_name"]: r for r in extract.sheets.iter_rows(named=True)}
    assert sheets["_secret"]["sheet_state"] == "hidden"
    assert sheets["Visible"]["hidden_cols"] == "B"
    cells = {r["coordinate"] if r["sheet_name"] == "Visible" else "secret": r for r in extract.cells.iter_rows(named=True)}
    assert cells["secret"]["value_text"] == "still read"
    assert cells["B2"]["comment_text"] == "look at me" and cells["B2"]["is_hidden_col"]
    assert cells["A3"]["is_strike"] and not cells["A2"]["is_strike"]
    assert cells["B3"]["value_text"] == "2" and cells["B3"]["value_type"] == "number"


def test_missing_workbook_raises_clear_error(tmp_path):
    with pytest.raises(WorkbookReadError, match="not found"):
        read_workbook(tmp_path / "nope.xlsx")


class FlakyFieldTrax:
    """Mimics the kit: tokens expire after N requests, every 3rd call is rate-limited, one 503."""

    def __init__(self, token_life: int = 3):
        self.calls = 0
        self.token_life = token_life
        self.tokens: dict[str, int] = {}
        self.devices = [{"id": f"d{i}", "name": f"BE EX-0{i}", "vin": None, "rego": None, "retired_at": None, "unit": "h"}
                        for i in range(3)]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.calls == 5:
            return httpx.Response(503, json={"error": "upstream_unavailable"})
        if self.calls % 3 == 0:
            return httpx.Response(429, json={"error": "rate_limited"}, headers={"retry-after": "1"})
        if request.url.path == "/oauth/token":
            token = f"t{self.calls}"
            self.tokens[token] = self.token_life
            return httpx.Response(200, json={"access_token": token})
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if self.tokens.get(token, 0) <= 0:
            return httpx.Response(401, json={"error": "token_expired"})
        self.tokens[token] -= 1
        cursor, limit = int(request.url.params["cursor"]), int(request.url.params["limit"])
        if request.url.path == "/v2/assets":
            items = self.devices[cursor:cursor + 2]  # force pagination
            nxt = str(cursor + 2) if cursor + 2 < len(self.devices) else None
            return httpx.Response(200, json={"items": items, "next_cursor": nxt})
        if request.url.path == "/v2/assets/d2/readings":
            return httpx.Response(404, json={"error": "not_found"})
        reading = {"time": "2026-10-04T08:00:00Z", "metric": "engine_hours", "value": 10, "unit": "h"}
        return httpx.Response(200, json={"items": [reading], "next_cursor": None})


SETTINGS = FieldTraxSettings(base_url="http://fieldtrax.test", client_id="c", client_secret="s")


def test_client_survives_rate_limits_503s_expired_tokens_and_pagination():
    server = FlakyFieldTrax()
    sleeps: list[float] = []
    client = FieldTraxClient(SETTINGS, transport=httpx.MockTransport(server), sleep=sleeps.append)

    snapshot = client.fetch()

    assert snapshot.devices["device_id"].to_list() == ["d0", "d1", "d2"]
    assert snapshot.readings["device_id"].to_list() == ["d0", "d1"]  # d2 is 404: no readings
    assert snapshot.readings["value"].to_list() == ["10", "10"]  # kept as received; parsed later
    assert snapshot.errors.select("scope", "device_id").rows() == [("readings_not_found", "d2")]
    assert 1.0 in sleeps  # honoured retry-after
    assert snapshot.stats.rate_limited > 0 and snapshot.stats.unavailable == 1 and snapshot.stats.reauths > 0


def test_client_gives_up_after_max_retries():
    always_down = httpx.MockTransport(lambda _r: httpx.Response(503, json={}))
    client = FieldTraxClient(SETTINGS, transport=always_down, sleep=lambda _s: None)

    with pytest.raises(FieldTraxError, match="gave up"):
        client.fetch()


def test_client_reports_bad_credentials():
    rejecting = httpx.MockTransport(lambda _r: httpx.Response(401, text=json.dumps({"error": "invalid_client"})))
    client = FieldTraxClient(SETTINGS, transport=rejecting, sleep=lambda _s: None)

    with pytest.raises(FieldTraxError, match="Authentication failed"):
        client.fetch()
