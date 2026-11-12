"""Pandera contracts for each clean table: types, required fields, formats, ranges.

A failure becomes an issue that points back at the source tab and row. When a
required field is null because its raw text could not be parsed, the issue
carries the raw text (via RAW_COMPANION) so Priya sees what was written.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandera.polars as pa
import polars as pl

from brackenfield import mdm, vocab
from brackenfield.config import EARLIEST_PLAUSIBLE_YEAR, REGISTER_AS_OF
from brackenfield.checks.registry import ISSUE_SCHEMA
from brackenfield.transform.parsing import REGO_PATTERN, VIN_PATTERN

CATEGORY_VALUES = mdm.registry().canonicals("category")
STATUS_VALUES = mdm.registry().canonicals("status")
BUSINESS_CODES = list(vocab.BUSINESSES)
HIRE_STATUSES = ["cancelled", "not_started", "on_hire", "off_hired"]
SOURCE_TABS = ["BE Plant", "NH Fleet", "Projects", "Hires 25-26", "_old rates"]


class OrganizationSchema(pa.DataFrameModel):
    org_id: str = pa.Field(unique=True)
    name: str = pa.Field(unique=True)
    org_type: str = pa.Field(isin=["group_business", "supplier"])


class SiteSchema(pa.DataFrameModel):
    site_id: str = pa.Field(unique=True)
    name: str
    state: str = pa.Field(isin=list(vocab.AU_STATES))


class ProjectSchema(pa.DataFrameModel):
    project_code: str = pa.Field(unique=True, str_matches=r"^P-\d{4}$")
    name: str = pa.Field(unique=True)
    state: str = pa.Field(isin=list(vocab.AU_STATES))
    business_code: str = pa.Field(isin=BUSINESS_CODES)
    source_tab: str = pa.Field(isin=SOURCE_TABS)
    source_row: pl.Int32 = pa.Field(ge=1)


class MachineLineSchema(pa.DataFrameModel):
    """Every line on BE Plant and NH Fleet."""

    fleet_no: str
    business_code: str = pa.Field(isin=BUSINESS_CODES)
    category: str = pa.Field(isin=CATEGORY_VALUES)
    rego: str = pa.Field(str_matches=REGO_PATTERN)
    vin: str = pa.Field(nullable=True, str_matches=VIN_PATTERN)
    year: pl.Int32 = pa.Field(ge=EARLIEST_PLAUSIBLE_YEAR, le=REGISTER_AS_OF.year)
    status: str = pa.Field(isin=STATUS_VALUES)
    site_id: str
    capital_cost_aud: float = pa.Field(nullable=True, gt=0)
    source_tab: str = pa.Field(isin=SOURCE_TABS)
    source_row: pl.Int32 = pa.Field(ge=1)


class MachineSchema(pa.DataFrameModel):
    """One row per physical machine."""

    machine_id: str = pa.Field(unique=True)
    owner_org_id: str = pa.Field(isin=[vocab.org_id_for_business(c) for c in BUSINESS_CODES])
    vin: str = pa.Field(nullable=True)  # unique by construction: machines are grouped on VIN
    rego: str = pa.Field(unique=True)
    source_tab: str = pa.Field(isin=SOURCE_TABS)
    source_row: pl.Int32 = pa.Field(ge=1)


class HireSchema(pa.DataFrameModel):
    hire_no: str = pa.Field(str_matches=r"^H-\d{4}$")
    status: str = pa.Field(isin=HIRE_STATUSES)
    supplier_org_id: str
    category: str = pa.Field(isin=CATEGORY_VALUES)
    project_code: str
    business_code: str = pa.Field(isin=BUSINESS_CODES)
    rate_amount: float = pa.Field(gt=0)
    rate_basis: str = pa.Field(isin=["day", "wk", "mth"])
    gst_treatment: str = pa.Field(isin=["inc", "ex"])
    day_rate_ex_gst: float = pa.Field(gt=0)
    source_tab: str = pa.Field(isin=SOURCE_TABS)
    source_row: pl.Int32 = pa.Field(ge=1)


class RateCardSchema(pa.DataFrameModel):
    category: str = pa.Field(unique=True, isin=CATEGORY_VALUES)
    day_rate: float = pa.Field(gt=0)


class DeviceSchema(pa.DataFrameModel):
    device_id: str = pa.Field(unique=True)
    name: str
    unit: str = pa.Field(isin=["h", "s"])
    vin: str = pa.Field(nullable=True, str_matches=VIN_PATTERN)
    is_listed: bool


class ReadingSchema(pa.DataFrameModel):
    """Unreadable time/value/unit load as null and are reported by RD007."""

    device_id: str
    time_utc: pl.Datetime(time_zone="UTC") = pa.Field(nullable=True)  # type: ignore[valid-type]
    engine_hours: float = pa.Field(nullable=True, ge=0)


@dataclass(frozen=True)
class Contract:
    table: str
    schema: type[pa.DataFrameModel]
    key: str
    raw_companion: dict[str, str]


CONTRACTS = (
    Contract("organizations", OrganizationSchema, "org_id", {}),
    Contract("sites", SiteSchema, "site_id", {}),
    Contract("projects", ProjectSchema, "project_code", {}),
    Contract(
        "machine_lines",
        MachineLineSchema,
        "fleet_no",
        {"category": "description_raw", "rego": "rego_raw", "vin": "vin_raw", "year": "year_raw",
         "status": "status_raw", "site_id": "depot_raw", "capital_cost_aud": "capital_cost_raw"},
    ),
    Contract("machines", MachineSchema, "machine_id", {}),
    Contract(
        "hires",
        HireSchema,
        "hire_no",
        {"supplier_org_id": "supplier_raw", "category": "category_raw", "project_code": "project_raw",
         "business_code": "business_code_raw", "rate_amount": "rate_raw", "rate_basis": "basis_raw",
         "gst_treatment": "gst_raw", "day_rate_ex_gst": "rate_raw"},
    ),
    Contract("rate_card", RateCardSchema, "category", {"category": "category_raw", "day_rate": "day_rate_raw"}),
    Contract("devices", DeviceSchema, "device_id", {"vin": "vin_raw"}),
    Contract("readings", ReadingSchema, "device_id", {"time_utc": "time_raw", "engine_hours": "value_raw"}),
)


INTERNAL_TABLES = {"devices", "readings"}  # FieldTrax plumbing: data team, not Priya


def contract_check_id(table: str, column: str) -> str:
    return f"SC-{table}.{column}"


def _failures_to_issues(contract: Contract, frame: pl.DataFrame, failures: pl.DataFrame) -> pl.DataFrame:
    indexed = frame.with_row_index("_idx").with_columns(pl.col("_idx").cast(pl.Int32))
    has_source = "source_tab" in frame.columns
    rows = []
    for f in failures.iter_rows(named=True):
        column, idx = f["column"], f["index"]
        src = indexed.row(idx, named=True) if idx is not None and idx < indexed.height else {}
        raw_col = contract.raw_companion.get(column)
        raw_value = src.get(raw_col) if raw_col else f["failure_case"]
        rows.append(
            {
                "check_id": contract_check_id(contract.table, column or "_table"),
                "check_title": f"{contract.table}.{column}: {f['check']}",
                "entity": contract.table,
                "severity": "error",
                "for_priya": contract.table not in INTERNAL_TABLES,
                "entity_key": None if not src else str(src.get(contract.key)),
                "source_tab": src.get("source_tab") if has_source else None,
                "source_row": src.get("source_row") if has_source else None,
                "field": column,
                "raw_value": None if raw_value is None else str(raw_value),
                "message": f"{column} failed {f['check']} (value: {f['failure_case']!r})",
            }
        )
    return pl.DataFrame(rows, schema=ISSUE_SCHEMA)


def validate_contracts(frames: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Validate every table that has rows. Returns issues; never raises on bad data."""
    issues = [pl.DataFrame(schema=ISSUE_SCHEMA)]
    for contract in CONTRACTS:
        frame = frames[contract.table]
        if frame.is_empty():
            continue
        try:
            contract.schema.validate(frame, lazy=True)
        except pa.errors.SchemaErrors as exc:
            issues.append(_failures_to_issues(contract, frame, exc.failure_cases))
    return pl.concat(issues)


def contract_catalogue() -> pl.DataFrame:
    rows = []
    for contract in CONTRACTS:
        for name, column in contract.schema.to_schema().columns.items():
            rules = [f"{c.name}({', '.join(f'{k}={v!r}' for k, v in (c.statistics or {}).items())})" for c in column.checks]
            if not column.nullable:
                rules.insert(0, "required")
            if column.unique:
                rules.append("unique")
            rules.insert(0, f"type {column.dtype}")
            rows.append(
                {
                    "check_id": contract_check_id(contract.table, name),
                    "kind": "contract",
                    "entity": contract.table,
                    "severity": "error",
                    "for_priya": contract.table not in INTERNAL_TABLES,
                    "audience": "internal" if contract.table in INTERNAL_TABLES else "priya",
                    "title": f"{contract.table}.{name}: " + "; ".join(rules),
                    "rationale": (contract.schema.__doc__ or "Output contract for the clean table.").strip().splitlines()[0],
                }
            )
    return pl.DataFrame(rows)
