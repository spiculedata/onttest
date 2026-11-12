"""Machines: one row per physical machine, from both plant sheets.

The same machine can appear on both sheets (READ ME: "Machines moved between
businesses keep a line on the old sheet. VIN or rego tells you it's the same
machine."). Register lines are linked into machines by shared VIN or rego; every
line is kept in `machine_register_lines` with its tab and row.
"""

from __future__ import annotations

import polars as pl

from brackenfield import mdm, vocab
from brackenfield.stage import BE_PLANT, NH_FLEET
from brackenfield.transform.parsing import clean_text, normalise_rego, normalise_vin, parse_int, parse_money

SHEET_BUSINESS = {BE_PLANT: "BE", NH_FLEET: "NH"}


def _status_columns() -> list[pl.Expr]:
    transfer = pl.col("status_raw").str.extract_groups(vocab.TRANSFER_STATUS_PATTERN)
    is_transfer = pl.col("status_raw").str.contains(vocab.TRANSFER_STATUS_PATTERN)
    return [
        pl.when(is_transfer).then(pl.lit("transferred")).otherwise(mdm.resolve_expr("status_raw", "status")).alias("status"),
        pl.when(is_transfer).then(pl.lit("canonical")).otherwise(mdm.resolve_expr("status_raw", "status", "basis")).alias("status_basis"),
        transfer.struct.field("business").str.to_uppercase().alias("transferred_to"),
        pl.when(is_transfer).then(transfer.struct.field("period").str.strip_chars()).alias("transfer_period"),
    ]


def build_machine_lines(plant_rows: pl.DataFrame) -> pl.DataFrame:
    """One clean row per register line (BE Plant + NH Fleet), before de-duplication."""
    fleet_prefix = pl.col("fleet_no").str.extract(r"^([A-Z]{2})-\d{2}$", 1)
    return (
        plant_rows.with_columns(
            pl.col("source_tab").replace_strict(SHEET_BUSINESS).alias("business_code"),
            clean_text("fleet_no").str.to_uppercase().alias("fleet_no"),
            pl.col("description").alias("description_raw"),
            pl.col("rego").alias("rego_raw"),
            pl.col("vin").alias("vin_raw"),
            pl.col("year").alias("year_raw"),
            pl.col("status").alias("status_raw"),
            pl.col("depot").alias("depot_raw"),
            pl.col("capital_cost").alias("capital_cost_raw"),
        )
        .with_columns(
            mdm.resolve_expr("description_raw", "category").alias("category"),
            mdm.resolve_expr("description_raw", "category", "basis").alias("category_basis"),
            mdm.resolve_expr("depot_raw", "site").alias("depot"),
            mdm.resolve_expr("depot_raw", "site", "basis").alias("depot_basis"),
            fleet_prefix.replace_strict(vocab.FLEET_PREFIX_CATEGORY, default=None).alias("fleet_prefix_category"),
            clean_text("make").alias("make"),
            clean_text("model").alias("model"),
            normalise_rego("rego_raw").alias("rego"),
            normalise_vin("vin_raw").alias("vin"),
            parse_int("year_raw").alias("year"),
            *_status_columns(),

            parse_money("capital_cost_raw").alias("capital_cost_aud"),
            clean_text("operator_mobile").alias("operator_mobile"),
        )
        .with_columns(
            (pl.col("vin") != pl.col("vin_raw")).fill_null(False).alias("vin_was_normalised"),
            pl.col("depot").map_elements(vocab.site_id_for, return_dtype=pl.String).alias("site_id"),
        )
        .select(
            "source_tab", "source_row", "business_code", "fleet_no", "description_raw", "category", "category_basis",
            "fleet_prefix_category", "make", "model", "rego_raw", "rego", "vin_raw", "vin", "vin_was_normalised",
            "year_raw", "year", "status_raw", "status", "status_basis", "transferred_to", "transfer_period",
            "depot_raw", "depot", "depot_basis", "site_id", "capital_cost_raw", "capital_cost_aud", "operator_mobile", "strike", "comments",
        )
    )


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self.parent.setdefault(item, item)
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        self.parent[item] = root
        return root

    def union(self, a: str, b: str) -> None:
        self.parent[self.find(a)] = self.find(b)


def assign_identity_groups(lines: pl.DataFrame) -> pl.DataFrame:
    """Add `identity_group`. Only a "Transferred to ..." line is linked to the line(s) sharing its
    VIN or rego (READ ME: moved machines keep a line on the old sheet). Two live lines that share
    a VIN or rego stay separate machines, so a typo cannot make a machine vanish; MC005 reports them.
    """
    uf = _UnionFind()
    rows = lines.select("source_tab", "source_row", "vin", "rego", "status").to_dicts()
    line_key = lambda r: f"line:{r['source_tab']}!{r['source_row']}"  # noqa: E731
    by_identity: dict[str, list[str]] = {}
    for r in rows:
        uf.find(line_key(r))
        if r["status"] != "transferred":
            for kind in ("vin", "rego"):
                if r[kind]:
                    by_identity.setdefault(f"{kind}:{r[kind]}", []).append(line_key(r))
    for r in rows:
        if r["status"] == "transferred":
            for kind in ("vin", "rego"):
                for other in by_identity.get(f"{kind}:{r[kind]}", []) if r[kind] else []:
                    uf.union(line_key(r), other)
    return lines.with_columns(pl.Series("identity_group", [uf.find(line_key(r)) for r in rows], dtype=pl.String))


def _unique_ids(ids: list[str], tabs: list[str], rows: list[int]) -> list[str]:
    """Keep ids stable; a repeat (two live lines on one VIN) gets its tab and row appended."""
    seen: set[str] = set()
    out = []
    for mid, tab, row in zip(ids, tabs, rows):
        out.append(mid if mid not in seen else f"{mid}_{vocab.slug(tab)}_{row}")
        seen.add(mid)
    return out


def _machine_id(vin: str | None, rego: str | None, tab: str, row: int) -> str:
    if vin:
        return f"mch_{vin.lower()}"
    if rego:
        return f"mch_rego_{rego.lower()}"
    return f"mch_{vocab.slug(tab)}_{row}"


def build_machines(lines: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return (machines, machine_register_lines).

    Within an identity group the *primary* line is the one that is not a
    "Transferred to ..." line (the receiving sheet is the current record);
    ties keep sheet order. Attributes missing on the primary line are filled
    from the other lines of the same machine.
    """
    grouped = assign_identity_groups(lines).with_columns(
        (pl.col("status") == "transferred").fill_null(False).alias("_is_transfer_line"),
        (pl.col("source_tab") != BE_PLANT).alias("_sheet_order"),
    )
    ordered = grouped.sort("identity_group", "_is_transfer_line", "_sheet_order", "source_row")
    fill_cols = ["vin", "rego", "make", "model", "year", "capital_cost_aud", "operator_mobile", "site_id"]
    machines = (
        ordered.group_by("identity_group", maintain_order=True)
        .agg(
            pl.col("business_code").first(),
            pl.col("fleet_no").first(),
            pl.col("category").drop_nulls().first(),
            pl.col("status").first(),
            *[pl.col(c).drop_nulls().first() for c in fill_cols],
            pl.col("source_tab").first(),
            pl.col("source_row").first(),
            pl.col("business_code").filter(pl.col("_is_transfer_line")).first().alias("previous_business_code"),
            pl.col("transfer_period").drop_nulls().first(),
            pl.concat_str(pl.col("source_tab"), pl.lit("!"), pl.col("source_row")).str.join("; ").alias("source_refs"),
            pl.len().alias("register_line_count"),
        )
    )
    ids = _unique_ids(
        [_machine_id(r["vin"], r["rego"], r["source_tab"], r["source_row"])
         for r in machines.select("vin", "rego", "source_tab", "source_row").iter_rows(named=True)],
        machines["source_tab"].to_list(), machines["source_row"].to_list(),
    )
    machines = machines.with_columns(
        pl.Series("machine_id", ids, dtype=pl.String),
        pl.col("business_code").str.to_lowercase().map_elements(lambda c: f"org_{c}", return_dtype=pl.String).alias("owner_org_id"),
    )
    register_lines = grouped.join(machines.select("identity_group", "machine_id"), on="identity_group", how="left")
    machines = machines.select(
        "machine_id", "business_code", "owner_org_id", "fleet_no", "category", "make", "model", "rego", "vin",
        "year", "status", "site_id", "capital_cost_aud", "operator_mobile", "previous_business_code",
        "transfer_period", "source_tab", "source_row", "source_refs", "register_line_count",
    ).sort("business_code", "fleet_no")
    register_lines = register_lines.drop("_is_transfer_line", "_sheet_order").sort("source_tab", "source_row")
    return machines, register_lines
