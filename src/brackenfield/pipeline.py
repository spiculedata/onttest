"""Run the whole pipeline: extract -> stage -> transform -> check -> load -> report."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
import polars as pl

from brackenfield import changes as change_log
from brackenfield import load, mdm, report, stage
from brackenfield.checks import hire_checks, machine_checks, telemetry_checks, workbook_checks  # noqa: F401 - register checks
from brackenfield.checks.registry import Tables, catalogue, run_rule_checks
from brackenfield.checks.schemas import contract_catalogue, validate_contracts
from brackenfield.config import Settings
from brackenfield.extract.fieldtrax import DEVICE_SCHEMA, ERROR_SCHEMA, READING_SCHEMA, FieldTraxError, fetch_snapshot
from brackenfield.extract.workbook import WorkbookExtract, read_workbook
from brackenfield.transform import hires as hire_tx
from brackenfield.transform import machines as machine_tx
from brackenfield.transform import reference, telemetry

log = logging.getLogger(__name__)

EMPTY_VERSIONS = pl.DataFrame(schema={**DEVICE_SCHEMA, "is_listed": pl.Boolean, "valid_from": pl.Datetime("us", "UTC"),
                                      "sync_run": pl.String})
EMPTY_READINGS = pl.DataFrame(schema={**READING_SCHEMA, "first_seen_run": pl.String, "first_seen_at": pl.Datetime("us", "UTC")})
EMPTY_ERRORS = pl.DataFrame(schema={"run_id": pl.String, **ERROR_SCHEMA})


@dataclass(frozen=True)
class SyncOutcome:
    refreshed: bool
    counts: dict[str, int] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)
    failure: str | None = None


@dataclass(frozen=True)
class RunResult:
    run_id: str
    row_counts: dict[str, int]
    issue_counts: dict[str, int]
    change_summary: dict[str, dict[str, int]]
    priya_items: int
    unaccounted_rows: int
    sync: SyncOutcome

    @property
    def fieldtrax_refreshed(self) -> bool:
        return self.sync.refreshed

    @property
    def ok(self) -> bool:
        return self.unaccounted_rows == 0


def _workbook_tables(extract: WorkbookExtract, settings: Settings) -> tuple[pl.DataFrame, dict[str, pl.DataFrame]]:
    stage.verify_layout(extract)
    dispositions = stage.build_dispositions(extract)
    rows = lambda name: stage.sheet_rows(extract, dispositions, name)  # noqa: E731
    plant = pl.concat([rows(stage.BE_PLANT), rows(stage.NH_FLEET)], how="diagonal_relaxed")
    machine_lines = machine_tx.build_machine_lines(plant)
    machines, register_lines = machine_tx.build_machines(machine_lines)
    projects = reference.build_projects(rows(stage.PROJECTS))
    hires = hire_tx.build_hires(rows(stage.HIRES), projects, settings.as_of)
    tables = {
        "organizations": reference.build_organizations(hires),
        "org_aliases": reference.build_org_aliases(hires),
        "sites": reference.build_sites(machine_lines),
        "projects": projects,
        "machines": machines,
        "machine_lines": register_lines,
        "hires": hires,
        "rate_card": reference.build_rate_card(rows(stage.OLD_RATES)),
    }
    return dispositions, tables


def _sync_fieldtrax(con, settings: Settings, run_id: str, skip: bool, transport) -> SyncOutcome:
    if skip:
        log.info("FieldTrax skipped by request")
        return SyncOutcome(refreshed=False, failure="skipped by request")
    try:
        snapshot = fetch_snapshot(settings.fieldtrax, transport=transport)
    except FieldTraxError as exc:
        log.warning("FieldTrax not refreshed: %s", exc)
        return SyncOutcome(refreshed=False, failure=str(exc))
    counts = load.append_fieldtrax_snapshot(con, run_id, snapshot)
    log.info("FieldTrax: %s; %s", counts, snapshot.stats.as_dict())
    return SyncOutcome(refreshed=True, counts=counts, stats=snapshot.stats.as_dict())


def _telemetry_tables(con, machines: pl.DataFrame, register_lines: pl.DataFrame) -> tuple[dict[str, pl.DataFrame], pl.DataFrame]:
    versions, readings, errors = load.read_fieldtrax_raw(con)
    if versions.is_empty():
        versions, readings = EMPTY_VERSIONS, EMPTY_READINGS
    if errors.is_empty():
        errors = EMPTY_ERRORS
    devices = telemetry.build_devices(versions, machines, register_lines)
    return {"devices": devices, "readings": telemetry.build_readings(readings, devices)}, errors


def mdm_usage(tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Every coded value seen in the workbook, resolved through the MDM."""
    lines, hires = tables["machine_lines"], tables["hires"]
    not_transfer = lines.filter(pl.col("status").ne_missing("transferred"))
    transfers = lines.filter(pl.col("status") == "transferred")
    return pl.concat([mdm.term_usage([
        ("category", lines, "description_raw"), ("category", hires, "category_raw"),
        ("category", tables["rate_card"], "category_raw"), ("status", not_transfer, "status_raw"),
        ("supplier", hires, "supplier_raw"), ("site", lines, "depot_raw"), ("rate_basis", hires, "basis_raw"),
        ("gst", hires, "gst_raw"), ("business", hires, "business_code_raw"),
    ]), mdm.pattern_usage("status", transfers, "status_raw", "transferred", "readme",
                          "pattern 'Transferred to <BE|NH> <period>' (READ ME: moved machines keep a line)")]).sort(
        "domain", "canonical", "raw_value", nulls_last=True)


def _run_checks(extract, dispositions, tables, settings, refreshed, errors, usage) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    ctx = Tables(as_of=settings.as_of, sheets=extract.sheets, cells=extract.cells, dispositions=dispositions,
                 fieldtrax_refreshed=refreshed, fieldtrax_errors=errors, mdm_usage=usage, **tables)
    rule_issues, rule_results = run_rule_checks(ctx)
    contract_issues = validate_contracts(tables)
    cat = pl.concat([catalogue(), contract_catalogue()])
    contract_counts = contract_issues.group_by("check_id").len().rename({"len": "violations"})
    contract_results = (
        cat.filter(pl.col("kind") == "contract").select("check_id")
        .join(contract_counts, on="check_id", how="left")
        .with_columns(pl.col("violations").fill_null(0).cast(pl.Int64))
    )
    issues = pl.concat([rule_issues, contract_issues])
    return issues, pl.concat([rule_results, contract_results]), cat


def run(
    settings: Settings | None = None, skip_fieldtrax: bool = False, transport: httpx.BaseTransport | None = None,
    label: str | None = None,
) -> RunResult:
    """One re-runnable pass. `transport` lets tests stand in for the FieldTrax API."""
    settings = settings or Settings()
    started = datetime.now(UTC)
    run_id = started.strftime("run_%Y%m%dT%H%M%S%fZ")
    extract = read_workbook(settings.workbook_path)
    dispositions, tables = _workbook_tables(extract, settings)

    with load.connect(settings.database_path) as con:
        with load.transaction(con):
            sync = _sync_fieldtrax(con, settings, run_id, skip_fieldtrax, transport)
            telemetry_tables, sync_errors = _telemetry_tables(con, tables["machines"], tables["machine_lines"])
            tables = {**tables, **telemetry_tables}
            usage = mdm_usage(tables)
            issues, results, cat = _run_checks(extract, dispositions, tables, settings, sync.refreshed, sync_errors, usage)
            changes = change_log.diff_tables(load.read_clean_tables(con, list(tables)), tables)
            result = RunResult(
                run_id=run_id,
                row_counts={name: frame.height for name, frame in tables.items()},
                issue_counts={sev: issues.filter(pl.col("severity") == sev).height for sev in ("error", "warning", "info")},
                change_summary=change_log.summarise(changes),
                priya_items=report.priya_list(issues).height,
                unaccounted_rows=issues.filter(pl.col("check_id") == "WB001").height,
                sync=sync,
            )
            raw_tables = {"workbook_sheets": extract.sheets, "workbook_cells": extract.cells, "workbook_rows": dispositions}
            mdm_tables = {**mdm.reference_tables(), "term_usage": usage}
            load.write_run(con, run_id, raw_tables, tables, issues, results, cat, changes, _run_row(result, started, settings, extract),
                           mdm_tables=mdm_tables)
            if label and sync.refreshed:
                load.label_run(con, label, run_id)
            elif label:
                log.warning("Not labelled %r: FieldTrax was not refreshed this run (%s)", label, sync.failure)

    _write_reports(settings, tables, issues, results, cat, changes, result)
    (settings.export_dir / "term_mapping.md").write_text(report.render_mdm_markdown(usage))
    return result


def _run_row(result: RunResult, started: datetime, settings: Settings, extract: WorkbookExtract) -> dict:
    return {
        "run_id": result.run_id, "started_at": started, "finished_at": datetime.now(UTC),
        "workbook_path": str(settings.workbook_path), "workbook_sha256": extract.sha256,
        "fieldtrax_refreshed": result.sync.refreshed, "fieldtrax_requests": result.sync.stats.get("requests", 0),
        "row_counts": json.dumps(result.row_counts), "issue_counts": json.dumps(result.issue_counts),
        "change_counts": json.dumps(result.change_summary),
        "status": "ok" if result.ok else "rows_unaccounted",
    }


def _write_reports(settings, tables, issues, results, cat, changes, result: RunResult) -> None:
    out = settings.export_dir
    report.export_tables(tables, out / "tables")
    items = report.priya_list(issues)
    issues.write_csv(out / "issues.csv")
    items.write_csv(out / "for_priya.csv")
    changes.write_csv(out / "changes.csv")
    (out / "for_priya.md").write_text(report.render_priya_markdown(items, settings.as_of.isoformat(), result.run_id))
    (out / "changes.md").write_text(report.render_changes_markdown(changes, tables, result))
    settings.docs_dir.mkdir(parents=True, exist_ok=True)
    (settings.docs_dir / "CHECKS.md").write_text(report.render_checks_markdown(cat, results))
