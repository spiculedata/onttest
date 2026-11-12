"""Command line: `uv run brackenfield run [--skip-fieldtrax] [--workbook PATH] [--db PATH]`."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

from brackenfield.config import Settings
from brackenfield.extract.workbook import WorkbookReadError
from brackenfield.pipeline import run
from brackenfield.stage import HeaderMismatchError, UnknownSheetError

EXIT_ROWS_UNACCOUNTED = 2
EXIT_BAD_INPUT = 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brackenfield", description="Load the Brackenfield plant register into DuckDB.")
    sub = parser.add_subparsers(dest="command", required=True)
    run_cmd = sub.add_parser("run", help="Run the full pipeline (re-runnable).")
    run_cmd.add_argument("--workbook", type=Path, help="Path to the .xlsx register")
    run_cmd.add_argument("--db", type=Path, help="Path to the DuckDB file")
    run_cmd.add_argument("--skip-fieldtrax", action="store_true", help="Do not call the FieldTrax API this run")
    run_cmd.add_argument("--label", help="Name this run's FieldTrax sync, e.g. before_advance")
    label_cmd = sub.add_parser("label", help="Name an earlier run's FieldTrax sync, e.g. before_advance.")
    label_cmd.add_argument("run_id")
    label_cmd.add_argument("name")
    label_cmd.add_argument("--db", type=Path, help="Path to the DuckDB file")
    screen_cmd = sub.add_parser("screen", help="Build Priya's one-screen answer as a single HTML file.")
    screen_cmd.add_argument("--db", type=Path, help="Path to the DuckDB file")
    screen_cmd.add_argument("--out", type=Path, help="Where to write the HTML (default out/priya_screen.html)")
    verify_cmd = sub.add_parser("verify", help="Cross-check DuckDB and answers.json against the workbook, independently.")
    verify_cmd.add_argument("--db", type=Path, help="Path to the DuckDB file")
    internal_cmd = sub.add_parser("internal", help="Build the internal DQ & MDM console and reports (not for Priya).")
    internal_cmd.add_argument("--db", type=Path, help="Path to the DuckDB file")
    internal_cmd.add_argument("--out", type=Path, help="Output folder (default out/internal)")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = _parser().parse_args(argv)
    settings = Settings()
    if getattr(args, "workbook", None):
        settings = replace(settings, workbook_path=args.workbook.resolve())
    if args.db:
        settings = replace(settings, database_path=args.db.resolve())
    if args.command == "verify":
        return _verify(settings)
    if args.command == "label":
        return _label(settings, args.run_id, args.name)
    if args.command == "screen":
        return _screen(settings, args.out)
    if args.command == "internal":
        return _internal(settings, args.out)
    try:
        result = run(settings, skip_fieldtrax=args.skip_fieldtrax, label=args.label)
    except (WorkbookReadError, UnknownSheetError, HeaderMismatchError) as exc:
        print(f"Input problem, nothing written: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT
    print(f"Run {result.run_id}")
    print("Rows: " + ", ".join(f"{k}={v}" for k, v in result.row_counts.items()))
    print("Issues: " + ", ".join(f"{k}={v}" for k, v in result.issue_counts.items()))
    print(f"FieldTrax refreshed: {result.fieldtrax_refreshed}" + ("" if result.sync.refreshed else f" ({result.sync.failure})"))
    if result.change_summary:
        print("Changes: " + "; ".join(f"{t} " + ", ".join(f"{k} {v}" for k, v in c.items()) for t, c in result.change_summary.items()))
    else:
        print("Changes: none (every clean record identical to the previous run)")
    print(f"Change report: {settings.export_dir / 'changes.md'}")
    print(f"For Priya: {result.priya_items} item(s) -> {settings.export_dir / 'for_priya.md'}")
    if not result.ok:
        print(f"{result.unaccounted_rows} workbook row(s) were not accounted for (WB001)", file=sys.stderr)
        return EXIT_ROWS_UNACCOUNTED
    return 0


def _screen(settings: Settings, out: Path | None) -> int:
    from brackenfield.screen.build import build_screen  # keeps `run` free of screen-only imports

    if not settings.database_path.exists():
        print(f"No database at {settings.database_path}; run `brackenfield run` first.", file=sys.stderr)
        return EXIT_BAD_INPUT
    from brackenfield.config import PROJECT_ROOT

    answers_path, detail_path = PROJECT_ROOT / "answers.json", settings.export_dir / "answers_detail.json"
    path = build_screen(settings, out or settings.export_dir / "priya_screen.html", answers_path, detail_path)
    print(f"Screen written to {path}")
    print(f"Answers written to {answers_path} (detail: {detail_path})")
    return 0


def _verify(settings: Settings) -> int:
    from brackenfield import verify
    from brackenfield.config import PROJECT_ROOT

    if not settings.database_path.exists():
        print(f"No database at {settings.database_path}; run `brackenfield run` first.", file=sys.stderr)
        return EXIT_BAD_INPUT
    report = verify.run(settings.workbook_path, settings.database_path, PROJECT_ROOT / "answers.json",
                        settings.export_dir / "answers_detail.json")
    for line in report.passed:
        print(f"PASS  {line}")
    for line in report.failed:
        print(f"FAIL  {line}")
    print(f"{len(report.passed)} passed, {len(report.failed)} failed")
    return 1 if report.failed else 0


def _label(settings: Settings, run_id: str, name: str) -> int:
    from brackenfield import load

    if not settings.database_path.exists():
        print(f"No database at {settings.database_path}", file=sys.stderr)
        return EXIT_BAD_INPUT
    with load.connect(settings.database_path) as con:
        try:
            load.label_run(con, name, run_id)
        except load.LabelError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_BAD_INPUT
    print(f"Labelled {run_id} as {name}")
    return 0


def _internal(settings: Settings, out: Path | None) -> int:
    from brackenfield.internal.build import build_internal

    if not settings.database_path.exists():
        print(f"No database at {settings.database_path}; run `brackenfield run` first.", file=sys.stderr)
        return EXIT_BAD_INPUT
    for path in build_internal(settings, out or settings.export_dir / "internal"):
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
