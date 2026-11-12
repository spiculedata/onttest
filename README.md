# Brackenfield register → DuckDB

Reads `brackenfield-plant-register.xlsx` exactly as it is (every tab, including the hidden
`_old rates` tab, the hidden *Operator mobile* column, strike-through, and cell comments). It
turns the workbook into clean records, pulls devices and readings from the FieldTrax API, runs
the data quality checks and loads everything into `warehouse/brackenfield.duckdb`. Every run
rebuilds the clean layer from scratch, so it is safe to re-run.

## Deliverables

| File | What it is |
|---|---|
| `answers.json` | The brief's skeleton, flat: machine and hire counts, the BE total discrepancy, the open-hire run rate, device and reading counts before `/__advance`, idle and replaceable counts, the saving a day (ex GST), and what `/__advance` changed. Money is a string to the cent, summed from full-precision day rates and rounded once. |
| `out/answers_detail.json` | The answer behind those numbers: each hire to end with its tab/row, the owned machine replacing it, its idle hours, what is unconfirmed and why, who signs, the open questions; for both the as-of view and `after_advance`. |
| `out/priya_screen.html` | Priya's one screen: the same answer, the records behind every number, a proposal panel for each hire, and the open questions. Single self-contained file. |
| `out/note_for_priya.md` | The note to Priya (under 150 words). |
| `warehouse/brackenfield.duckdb` | Everything: raw cells and API snapshots, master data, clean records, checks and issues, run history. |
| `out/for_priya.md`, `out/term_mapping.md`, `out/tables/*.csv` | Priya's list of things to resolve, every word and how it was mapped, CSV copies of the clean tables. |
| `out/internal/` | Data team only: DQ & MDM console and reports. |
| `docs/CHECKS.md`, `docs/INTERPRETATIONS.md` | Every check with its last result; every rule and how it was read. |

## Run it

Needs [uv](https://docs.astral.sh/uv/) and Node (for the FieldTrax kit).

```bash
make install              # Python 3.12 deps
make test                 # tests with coverage

make kit                  # terminal 1: FieldTrax on 127.0.0.1:8799 (runs from .kit/ so the .xlsx here is untouched)
make demo                 # terminal 2: the brief's sequence, from an empty warehouse:
                          #   sync and label it before_advance -> sync again (no change) -> POST /__advance
                          #   -> sync -> Priya's screen + answers.json -> internal console
```

Day to day: `make run` (workbook + FieldTrax sync), `make run-workbook` (no FieldTrax), `make screen`,
`make internal`, `make verify`, `make all`.

`make verify` is an independent cross-check: it reads the .xlsx with openpyxl, without the pipeline's
transforms or master data. It confirms that every cell is stored unchanged and every row is accounted
for, and that every hire and machine leads back to its tab and row with matching values. It also
re-derives every pair in `out/answers_detail.json` from the cells and the raw FieldTrax lines: category, state,
Available or Yard, rate and GST, idle hours, totals, and that the dearest hires were chosen. And it
recomputes 17 of the `answers.json` skeleton values the same way (machine, transfer, disposal and hire
counts, strike-through cancellations, the BE total, the run rate, device and reading counts, readings
added by the advance). `make help` lists them. The CLI behind them is `uv run brackenfield
run | label | screen | internal`. `make demo` resets the kit it talks to; use `KIT_PORT=` to point
at another one.

Exit codes: `0` ok; `2` some workbook row was not accounted for (WB001); `3` bad input
(missing file, unknown tab or a changed header). Nothing is written in that case.

## Layout

```
src/brackenfield/
  config.py              paths + READ ME constants (GST 10%, 5-day week, 22-day month, as-of date)
  vocab.py               fixed identifiers (businesses, fleet prefixes) and id helpers
  stage.py               per-tab layout (SheetSpec), row dispositions, wide row frames
  extract/workbook.py    openpyxl: every cell + strike/hidden/comment/fill flags
  extract/fieldtrax.py   OAuth client; retries 429/503, re-auths on expired token, paginates
  transform/             polars: parsing, reference (orgs, sites, projects, rate card),
                         machines (VIN/rego identity), hires, telemetry (devices, readings)
  mdm.py                 master data: canonical values, aliases, typo matching (data in mdm/*.csv)
  checks/                rule checks (registry + 4 modules) and pandera table contracts
  screen/                Priya's screen: analysis (the rules), build (data + worlds), template.html
  internal/              internal DQ & MDM console and markdown reports
  load.py                DuckDB schemas raw / clean / dq / meta, one transaction per run
  report.py              Priya's list, CHECKS.md, CSV exports
  pipeline.py, cli.py
tests/                   unit + end-to-end (real workbook into a temp DuckDB)
docs/CHECKS.md           every check, generated each run, with its last result
out/for_priya.md         the list for Priya (also out/for_priya.csv, dq.priya_list)
out/tables/*.csv         CSV copy of every clean table
```

## What's in the database

| Schema | Tables |
|---|---|
| `raw` | `workbook_sheets`, `workbook_cells` (one row per non-empty cell, with formatting), `workbook_rows` (every row 1..max with its disposition), `fieldtrax_device_versions` (a row only when a device changes), `fieldtrax_reading_lines` (each reading as received, stored once) |
| `clean` | `organizations`, `org_aliases`, `sites`, `projects`, `machines`, `machine_lines`, `hires`, `rate_card`, `devices`, `readings` |
| `dq` | `check_catalogue`, `issues` (this run), `issue_history`, `check_results`, view `priya_list` |
| `meta` | `runs` (workbook hash, FieldTrax refresh, row/issue/change counts, status), `fieldtrax_syncs`, `fieldtrax_sync_errors`, `record_changes` |

- **Machines**: one row per physical machine. Lines on both sheets that share a VIN or rego
  are merged; the line that isn't a "Transferred to …" line is the current record.
  `source_tab`/`source_row` is that line and `source_refs` lists every line. All 104
  register lines are kept in `machine_lines`, each with its `machine_id`.
- **Hires**: one row per sheet line, including cancelled (struck-through) and duplicate lines,
  which are flagged, not dropped. Rates carry the raw text plus the amount, basis, GST
  treatment (and whether it came from the column or the READ ME default), and an ex-GST day rate.
- **Subtotals and totals** are never loaded as data. Checks WB008/WB009 reconcile them.
- **Notes and comments** are stored verbatim as data (e.g. H-1058's note and the K3 comment).
  The pipeline never acts on text found inside the workbook.

## Master data (term mapping)

Every coded value goes through `brackenfield.mdm`: categories, statuses, suppliers, depots, rate
basis, GST and business. The reference data is in two CSVs that Priya can edit without touching code:

- `mdm/canonical.csv`: the master values for each domain (e.g. category `Tipper`, code `TP`)
- `mdm/aliases.csv`: every known way of writing one, with its basis: `variant` (Tipper truck,
  Smooth drum roller), `readme` (T&D, Ute, Genset), `regional` (bakkie, pickup, dump truck) or
  `inferred` (On job, Repairs, Hire Well)

Matching ignores case, spacing and punctuation, reads `&` as "and", treats `20T` / `20 tonne` the
same, and drops company suffixes (Pty Ltd, P/L). Anything still unknown is fuzzy-matched for typos
("Excavtor 20t", "Tiper"). A close, unambiguous match is applied and flagged; anything else is left
blank, never guessed ("Excavator 50t" sits between 5t and 20t, so it is refused). Inferred and
typo matches go on Priya's list as VC001, and unmapped words as VC002. `mdm.term_usage` and
`out/term_mapping.md` show every word found, what it became and where it is.

## Priya's screen

`uv run brackenfield screen` writes `out/priya_screen.html`, a single self-contained file that
answers "Which hires could I end right now because we own something idle that would do the job,
and what would that save me a day?" The rules for the numbers are in `screen/analysis.py` and are
also printed on the screen. Every number opens the records behind it, and anything not confirmed
is shown hatched and labelled unconfirmed. Ending a hire is a proposal: the screen shows what would
change in the register, what isn't known and who signs. Nothing is sent and the register is not
changed. Proposals are signed by Priya N., Group Plant Manager: the READ ME names her as keeper of the
register, and the project owner confirmed it. Change `SIGN_OFF` in `screen/build.py` if the rule
changes. FieldTrax-based findings on the screen (trackers, idle hours, spare trackers) are
computed separately for the before-advance and after-advance views from each view's own data.
`make screen` also writes `answers.json` and `out/answers_detail.json`.

## Internal DQ & MDM console (data team, not for Priya)

`uv run brackenfield internal` writes three files to `out/internal/`:

- `dq_console.html`: one self-contained file with seven tabs:
  - **Overview:** issue counts, issues per run, a per-table scorecard and table counts
  - **Checks:** all 109 checks with last-run hits and the change since the previous run
  - **Issues:** every issue, filterable, plus new and resolved since the last run
  - **Row accounting:** every workbook row's disposition, showing nothing was dropped
  - **Master data:** coverage by domain, judgement calls, every written form, the alias reference
  - **FieldTrax:** syncs with their retry counts, and sync errors
  - **Runs & changes:** run history and record changes per run
- `dq_report.md`: scorecard, checks with hits, what moved, new and resolved issues, row
  accounting and FieldTrax syncs
- `mdm_report.md`: coverage by domain, terms needing a decision, everything seen, and aliases
  defined but unused

## FieldTrax connector

`extract/fieldtrax.py` syncs devices and readings into the same database and links each device
to a machine (by VIN, then rego, then the business + fleet number in its name).

- **Transport errors are retried, not fatal.** 429 waits for `Retry-After`. 503/502/504, network
  errors and unreadable (non-JSON) pages back off and retry. An expired token triggers a fresh
  sign-in. If one device's readings still fail, that device keeps its earlier readings and the
  others carry on (DV010). If the device list itself fails, the sync is skipped and the last good
  snapshot is used (DV001). Retry counts go into `meta.fieldtrax_syncs.stats`.
- **API data is handled like workbook cells.** Every item is stored as received: its fields as
  text plus its JSON `payload`. The transform parses them, unreadable times, values or units load
  as null, and RD007 reports them with the original JSON. Items that can't be keyed (no `id`,
  duplicate `id`, not an object) go to `meta.fieldtrax_sync_errors` and are reported by DV009.
- **Re-runs change nothing.** Device rows are versioned and get a new row only when the device's
  JSON or its listed/unlisted state changes. Reading lines are stored once. Clean records hold no
  per-run values.
- **Every run reports exactly what changed.** The clean tables are diffed field by field against
  the previous run into `meta.record_changes`, with `out/changes.md` and `out/changes.csv`
  alongside. The same report lists the devices that match nothing and the working machines
  that have no device.

`out/sync_demo/` holds the reports from: run, run again (no changes), `POST /__advance`, run.

**Answering as of a moment in time.** Every sync's data is kept exactly as received and tagged
with the run that fetched it (device versions and reading lines are append-only), so FieldTrax
"as it stood" at any earlier sync can be rebuilt exactly. Name the sync you answer from before
calling `/__advance`:

```bash
uv run brackenfield run --label before_advance     # then POST /__advance, then run again
uv run brackenfield label <run_id> before_advance  # or name an earlier sync afterwards
```

Priya's screen answers from the `before_advance` sync. If none is labelled it infers one from the
sync history, and the screen says which it used.

## Assumptions (all surfaced as checks)

- Text dates are Australian day-first (`02/04/26` = 2 Apr 2026). HR008 lists the ambiguous ones.
- Hire status is evaluated as at 31 Oct 2026, the register's date.
- `On job` = on project, `Repairs` = workshop and `Hire Well` = Hirewell are judgement calls,
  so VC001 asks Priya to confirm them.
- Depot states are inferred from the town name.
- Machine IDs are `mch_<vin>` (or `mch_rego_<rego>` when no VIN). If Priya adds a missing VIN,
  that machine's ID changes on the next run.
