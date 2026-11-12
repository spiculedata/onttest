"""Organizations, sites, projects and the superseded rate card."""

from __future__ import annotations

import polars as pl

from brackenfield import mdm, vocab
from brackenfield.transform.parsing import clean_text, parse_money

BUSINESS_NOTES = {
    "BE": "Owns the BE Plant tab.",
    "NH": "Owns the NH Fleet tab. Bought by the group in Jul-25 (READ ME).",
}


def build_organizations(hire_lines: pl.DataFrame) -> pl.DataFrame:
    """The two group businesses plus every supplier that resolves from the hire sheet."""
    businesses = pl.DataFrame(
        {
            "org_id": [vocab.org_id_for_business(code) for code in vocab.BUSINESSES],
            "name": list(vocab.BUSINESSES.values()),
            "org_type": "group_business",
            "short_code": list(vocab.BUSINESSES),
            "notes": [BUSINESS_NOTES[code] for code in vocab.BUSINESSES],
        }
    )
    suppliers = (
        hire_lines.select(pl.col("supplier_name").drop_nulls().unique().sort())
        .with_columns(
            pl.col("supplier_name").map_elements(vocab.org_id_for_supplier, return_dtype=pl.String).alias("org_id"),
            pl.lit("supplier").alias("org_type"),
            pl.lit(None, dtype=pl.String).alias("short_code"),
            pl.lit("Hire supplier, from Hires 25-26.").alias("notes"),
        )
        .rename({"supplier_name": "name"})
        .select(businesses.columns)
    )
    return pl.concat([businesses, suppliers])


def build_org_aliases(hire_lines: pl.DataFrame) -> pl.DataFrame:
    """Each supplier spelling seen, what it resolved to and on what basis."""
    return (
        hire_lines.filter(pl.col("supplier_raw").is_not_null())
        .group_by("supplier_raw")
        .agg(
            pl.col("supplier_org_id").first().alias("org_id"),
            pl.col("supplier_basis").first().alias("basis"),
            pl.len().alias("line_count"),
            pl.concat_str(pl.col("source_tab"), pl.lit("!"), pl.col("source_row")).sort().str.join(", ").alias("source_refs"),
        )
        .rename({"supplier_raw": "alias"})
        .sort("org_id", "alias")
    )


def build_sites(machine_lines: pl.DataFrame) -> pl.DataFrame:
    return (
        machine_lines.filter(pl.col("site_id").is_not_null())
        .group_by("site_id")
        .agg(
            pl.col("depot").first().alias("name"),
            pl.col("depot_raw").unique().sort().str.join(" | ").alias("written_as"),
            pl.col("business_code").unique().sort().str.join(",").alias("used_by_business"),
            pl.len().alias("register_line_count"),
        )
        .with_columns(
            pl.lit("depot").alias("site_type"),
            pl.col("name").map_elements(lambda n: mdm.registry().attribute("site", n), return_dtype=pl.String).alias("state"),
            pl.lit("MDM site reference (inferred from town name)").alias("state_basis"),
        )
        .select("site_id", "name", "written_as", "site_type", "state", "state_basis", "used_by_business", "register_line_count")
        .sort("site_id")
    )


def build_projects(project_rows: pl.DataFrame) -> pl.DataFrame:
    return project_rows.select(
        clean_text("project_code").str.to_uppercase().alias("project_code"),
        clean_text("name").alias("name"),
        clean_text("state").str.to_uppercase().alias("state"),
        clean_text("business_code").str.to_uppercase().alias("business_code"),
        clean_text("business_code")
        .str.to_lowercase()
        .map_elements(lambda code: f"org_{code}", return_dtype=pl.String)
        .alias("business_org_id"),
        "source_tab",
        "source_row",
    )


def build_rate_card(rate_rows: pl.DataFrame) -> pl.DataFrame:
    """The hidden `_old rates` tab: day rates superseded in Jan-25. Kept for reference."""
    return rate_rows.select(
        mdm.resolve_expr("category", "category").alias("category"),
        pl.col("category").alias("category_raw"),
        parse_money("day_rate").alias("day_rate"),
        pl.col("day_rate").alias("day_rate_raw"),
        pl.lit("Jan-25").alias("superseded"),
        pl.lit("unknown").alias("gst_treatment"),
        "source_tab",
        "source_row",
    )
