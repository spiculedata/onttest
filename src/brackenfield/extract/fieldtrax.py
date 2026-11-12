"""FieldTrax telemetry API connector: devices (trackers) and their readings.

Treated like the workbook: nothing is interpreted here. Every item is kept as
received (its JSON text plus its fields as text); typing happens in the
transform, where unreadable values become nulls that the checks report.

Transport problems are handled, not fatal:
  - 429: wait for Retry-After and retry
  - 503 / network errors / unreadable pages: back off and retry
  - 401 token_expired: sign in again (tokens last a fixed number of requests)
  - 404 on a device's readings: recorded as "no readings"
If one device's readings still fail after retries, that is recorded as a sync
error and the other devices carry on. Only a failure to list devices aborts the
sync, because without the full device list we cannot tell what disappeared.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable

import httpx
import polars as pl

from brackenfield.config import FieldTraxSettings

log = logging.getLogger(__name__)

ASSET_PAGE_LIMIT = 25
READING_PAGE_LIMIT = 50
BACKOFF_SECONDS = 0.5
MAX_PAGES = 10_000  # guards against a cursor that never ends

DEVICE_FIELDS = ("name", "vin", "rego", "retired_at", "unit")
READING_FIELDS = ("time", "metric", "value", "unit")

DEVICE_SCHEMA = {"device_id": pl.String, **{f: pl.String for f in DEVICE_FIELDS}, "payload": pl.String}
READING_SCHEMA = {"device_id": pl.String, **{f: pl.String for f in READING_FIELDS}, "payload": pl.String}
ERROR_SCHEMA = {"scope": pl.String, "device_id": pl.String, "error": pl.String, "payload": pl.String}


class FieldTraxError(RuntimeError):
    pass


@dataclass
class SyncStats:
    requests: int = 0
    rate_limited: int = 0
    unavailable: int = 0
    transport_errors: int = 0
    bad_pages: int = 0
    reauths: int = 0

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class FieldTraxSnapshot:
    fetched_at: datetime
    devices: pl.DataFrame
    readings: pl.DataFrame
    errors: pl.DataFrame
    stats: SyncStats = field(default_factory=SyncStats)


def _as_text(value: object) -> str | None:
    """A JSON scalar as text, exactly enough to parse later; containers stay JSON."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _page_items(response: httpx.Response) -> tuple[list, str | None]:
    """Validate a page: JSON object with an `items` list and a string-or-null `next_cursor`."""
    try:
        body = response.json()
    except ValueError as exc:
        raise ValueError(f"page is not JSON: {response.text[:120]!r}") from exc
    if not isinstance(body, dict) or not isinstance(body.get("items"), list):
        raise ValueError(f"page has no items list: {response.text[:120]!r}")
    cursor = body.get("next_cursor")
    if cursor is not None and not isinstance(cursor, (str, int)):
        raise ValueError(f"next_cursor is not a cursor: {cursor!r}")
    return body["items"], None if cursor is None else str(cursor)


class FieldTraxClient:
    def __init__(
        self,
        settings: FieldTraxSettings,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._http = httpx.Client(base_url=settings.base_url, timeout=settings.timeout_seconds, transport=transport)
        self._sleep = sleep
        self._token: str | None = None
        self.stats = SyncStats()

    def close(self) -> None:
        self._http.close()

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        """One HTTP call with retry on 429/503 and network errors."""
        for attempt in range(1, self._settings.max_retries + 1):
            self.stats.requests += 1
            try:
                response = self._http.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                self.stats.transport_errors += 1
                log.warning("FieldTrax %s %s network error (attempt %d): %s", method, path, attempt, exc)
                self._sleep(BACKOFF_SECONDS * attempt)
                continue
            if response.status_code == 429:
                self.stats.rate_limited += 1
                self._sleep(_retry_after(response))
                continue
            if response.status_code in (502, 503, 504):
                self.stats.unavailable += 1
                self._sleep(BACKOFF_SECONDS * attempt)
                continue
            return response
        raise FieldTraxError(f"{method} {path}: gave up after {self._settings.max_retries} attempts")

    def _authenticate(self) -> None:
        response = self._send(
            "POST", "/oauth/token",
            data={"client_id": self._settings.client_id, "client_secret": self._settings.client_secret},
        )
        token = None
        if response.status_code == 200:
            try:
                token = response.json().get("access_token")
            except ValueError:
                token = None
        if not isinstance(token, str) or not token:
            raise FieldTraxError(f"Authentication failed: HTTP {response.status_code} {response.text[:200]}")
        self._token = token

    def _get(self, path: str, params: dict) -> httpx.Response:
        """Authenticated GET; signs in again once when the token has expired."""
        for _ in range(2):
            if self._token is None:
                self._authenticate()
            response = self._send("GET", path, params=params, headers={"authorization": f"Bearer {self._token}"})
            if response.status_code != 401:
                return response
            self.stats.reauths += 1
            self._token = None
        raise FieldTraxError(f"GET {path}: still unauthorised after signing in again")

    def _get_page(self, path: str, limit: int, cursor: str) -> tuple[list, str | None] | None:
        """One page, retried if the body is unreadable. None when the resource is 404."""
        for attempt in range(1, self._settings.max_retries + 1):
            response = self._get(path, {"limit": limit, "cursor": cursor})
            if response.status_code == 404:
                return None
            if response.status_code != 200:
                raise FieldTraxError(f"GET {path}: HTTP {response.status_code} {response.text[:200]}")
            try:
                return _page_items(response)
            except ValueError as exc:
                self.stats.bad_pages += 1
                log.warning("FieldTrax %s cursor %s: %s (attempt %d)", path, cursor, exc, attempt)
                self._sleep(BACKOFF_SECONDS * attempt)
        raise FieldTraxError(f"GET {path} cursor {cursor}: unreadable page after {self._settings.max_retries} attempts")

    def _paginate(self, path: str, limit: int) -> list | None:
        items: list = []
        cursor: str | None = "0"
        for _ in range(MAX_PAGES):
            page = self._get_page(path, limit, cursor)
            if page is None:
                return None
            page_items, cursor = page
            items.extend(page_items)
            if cursor is None:
                return items
        raise FieldTraxError(f"GET {path}: more than {MAX_PAGES} pages; cursor never ended")

    def fetch(self) -> FieldTraxSnapshot:
        fetched_at = datetime.now(UTC)
        devices, errors = _device_rows(self._paginate("/v2/assets", ASSET_PAGE_LIMIT) or [])
        readings: list[dict] = []
        for device_id in [d["device_id"] for d in devices]:
            try:
                items = self._paginate(f"/v2/assets/{device_id}/readings", READING_PAGE_LIMIT)
            except FieldTraxError as exc:
                errors.append({"scope": "readings", "device_id": device_id, "error": str(exc), "payload": None})
                continue
            if items is None:
                errors.append({"scope": "readings_not_found", "device_id": device_id, "error": "HTTP 404", "payload": None})
                continue
            row_list, bad = _reading_rows(device_id, items)
            readings.extend(row_list)
            errors.extend(bad)
        return FieldTraxSnapshot(
            fetched_at=fetched_at,
            devices=pl.DataFrame(devices, schema=DEVICE_SCHEMA),
            readings=pl.DataFrame(readings, schema=READING_SCHEMA),
            errors=pl.DataFrame(errors, schema=ERROR_SCHEMA),
            stats=self.stats,
        )


def _retry_after(response: httpx.Response) -> float:
    try:
        return max(0.0, float(response.headers.get("retry-after", 1)))
    except ValueError:
        return 1.0


def _device_rows(items: list) -> tuple[list[dict], list[dict]]:
    """Devices as text. An item with no usable id cannot be keyed, so it is recorded as an error."""
    rows, errors, seen = [], [], set()
    for item in items:
        payload = json.dumps(item, sort_keys=True)
        device_id = _as_text(item.get("id")) if isinstance(item, dict) else None
        if not device_id or device_id in seen:
            reason = "device item is not an object" if not isinstance(item, dict) else (
                "device has no id" if not device_id else f"device id {device_id} listed twice")
            errors.append({"scope": "device", "device_id": device_id, "error": reason, "payload": payload})
            continue
        seen.add(device_id)
        rows.append({"device_id": device_id, **{f: _as_text(item.get(f)) for f in DEVICE_FIELDS}, "payload": payload})
    return rows, errors


def _reading_rows(device_id: str, items: list) -> tuple[list[dict], list[dict]]:
    rows, errors = [], []
    for item in items:
        payload = json.dumps(item, sort_keys=True)
        if not isinstance(item, dict):
            errors.append({"scope": "reading", "device_id": device_id, "error": "reading item is not an object", "payload": payload})
            continue
        rows.append({"device_id": device_id, **{f: _as_text(item.get(f)) for f in READING_FIELDS}, "payload": payload})
    return rows, errors


def fetch_snapshot(settings: FieldTraxSettings, transport: httpx.BaseTransport | None = None) -> FieldTraxSnapshot:
    if not settings.is_configured:
        raise FieldTraxError("FieldTrax is not configured (FIELDTRAX_BASE_URL / CLIENT_ID / CLIENT_SECRET)")
    client = FieldTraxClient(settings, transport=transport)
    try:
        return client.fetch()
    finally:
        client.close()
