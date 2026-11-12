"""Master data management: one place that turns the yard's words into canonical values.

Reference data lives in `mdm/canonical.csv` (the master values per domain) and
`mdm/aliases.csv` (every known way of writing one, with its basis). Priya can edit
both without touching code.

Resolution of a raw value, in order:
  1. normalise it (case, spacing, punctuation, "&" = "and", "20 tonne" = "20t",
     company suffixes like "Pty Ltd" or "P/L" for suppliers)
  2. exact match on a canonical value or alias -> basis from the alias file
  3. fuzzy match (typos): best match at or above FUZZY_ACCEPT and clearly better than
     the runner-up -> basis "fuzzy" (applied, but sent to Priya to confirm)
  4. otherwise unmapped (null) with the nearest suggestions -> an error for Priya

Basis values: canonical, variant, readme, regional (applied, recorded) and
inferred, fuzzy (applied, sent to Priya to confirm).
"""

from __future__ import annotations

import csv
import difflib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import polars as pl

from brackenfield.config import PROJECT_ROOT

MDM_DIR = PROJECT_ROOT / "mdm"
BASES = ("canonical", "variant", "readme", "regional", "inferred", "fuzzy")
NEEDS_CONFIRMATION = ("inferred", "fuzzy")
# Short coded values (GST "inc"/"ex", basis "wk"/"mth", "BE"/"NH", "h"/"s") are too short to typo-match
# safely: "GST" alone would match "ex". Unknown values there are left unmapped instead.
NO_FUZZY_DOMAINS = {"gst", "rate_basis", "business", "unit"}
FUZZY_ACCEPT = 0.84
FUZZY_MARGIN = 0.06
LEGAL_SUFFIXES = r"\b(pty\s*ltd|pty\s*limited|p\s*l|pty|ltd|limited|co|inc)\b"


class MdmError(ValueError):
    pass


@dataclass(frozen=True)
class Resolution:
    raw: str | None
    canonical: str | None
    basis: str | None
    matched_on: str | None
    score: float | None
    suggestions: str | None


def mdm_key(text: str, domain: str = "") -> str:
    key = text.strip().lower()
    key = key.replace("&", " and ")
    key = re.sub(r"(\d+)\s*(?:t|tn|ton|tons|tonne|tonnes)\b", r"\1t", key)
    key = re.sub(r"[^a-z0-9+]+", " ", key)
    if domain == "supplier":
        key = re.sub(LEGAL_SUFFIXES, " ", key)
    return re.sub(r"\s+", " ", key).strip()


@dataclass(frozen=True)
class Domain:
    name: str
    canonicals: tuple[str, ...]
    attributes: dict[str, str]  # canonical -> code column
    entries: dict[str, tuple[str, str, str]]  # key -> (canonical, basis, written form)

    def resolve(self, raw: str | None) -> Resolution:
        if raw is None or not str(raw).strip():
            return Resolution(raw, None, None, None, None, None)
        key = mdm_key(str(raw), self.name)
        if key in self.entries:
            canonical, basis, written = self.entries[key]
            return Resolution(raw, canonical, basis, written, 1.0, None)
        if self.name in NO_FUZZY_DOMAINS:
            return Resolution(raw, None, None, None, None, ", ".join(self.canonicals))
        return self._fuzzy(raw, key)

    def _fuzzy(self, raw: str, key: str) -> Resolution:
        scored = sorted(
            ((difflib.SequenceMatcher(None, key, k).ratio(), k) for k in self.entries), reverse=True
        )
        best_score, best_key = scored[0] if scored else (0.0, None)
        best_canon = self.entries[best_key][0] if best_key else None
        rival = next((s for s, k in scored[1:] if self.entries[k][0] != best_canon), 0.0)
        suggestions = ", ".join(dict.fromkeys(self.entries[k][0] for _, k in scored[:3])) or None
        if best_key and best_score >= FUZZY_ACCEPT and best_score - rival >= FUZZY_MARGIN:
            return Resolution(raw, best_canon, "fuzzy", self.entries[best_key][2], round(best_score, 3), suggestions)
        return Resolution(raw, None, None, None, round(best_score, 3) if best_key else None, suggestions)


@dataclass(frozen=True)
class Registry:
    domains: dict[str, Domain]

    def domain(self, name: str) -> Domain:
        if name not in self.domains:
            raise MdmError(f"Unknown MDM domain {name!r}")
        return self.domains[name]

    def canonicals(self, name: str) -> list[str]:
        return list(self.domain(name).canonicals)

    def attribute(self, name: str, canonical: str) -> str | None:
        return self.domain(name).attributes.get(canonical)


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise MdmError(f"MDM file missing: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_registry(directory: Path = MDM_DIR) -> Registry:
    """Load and validate the reference data. Fails fast on contradictions."""
    canon_rows = _read_csv(directory / "canonical.csv")
    alias_rows = _read_csv(directory / "aliases.csv")
    canon: dict[str, dict[str, str]] = {}
    for r in canon_rows:
        canon.setdefault(r["domain"], {})[r["canonical"]] = r.get("code") or ""
    entries: dict[str, dict[str, tuple[str, str, str]]] = {d: {} for d in canon}
    for domain, values in canon.items():
        for value in values:
            entries[domain][mdm_key(value, domain)] = (value, "canonical", value)
    for r in alias_rows:
        domain, alias, target, basis = r["domain"], r["alias"], r["canonical"], r["basis"]
        if domain not in canon or target not in canon[domain]:
            raise MdmError(f"aliases.csv: {alias!r} points at {domain}/{target!r}, which is not in canonical.csv")
        if basis not in BASES or basis in ("canonical", "fuzzy"):
            raise MdmError(f"aliases.csv: {alias!r} has basis {basis!r}; use variant, readme, regional or inferred")
        key = mdm_key(alias, domain)
        existing = entries[domain].get(key)
        if existing and existing[0] != target:
            raise MdmError(f"aliases.csv: {alias!r} maps to {target!r} but {existing[2]!r} already maps to {existing[0]!r}")
        if not existing:
            entries[domain][key] = (target, basis, alias)
    return Registry({d: Domain(d, tuple(canon[d]), canon[d], entries[d]) for d in canon})


@lru_cache(maxsize=1)
def registry() -> Registry:
    return load_registry()


def resolve_expr(column: str, domain: str, field: str = "canonical") -> pl.Expr:
    """Polars expression resolving a raw column through the MDM. `field`: canonical or basis."""
    dom = registry().domain(domain)

    def _map(series: pl.Series) -> pl.Series:
        lookup = {v: getattr(dom.resolve(v), field) for v in series.drop_nulls().unique().to_list()}
        return series.replace_strict(lookup, default=None, return_dtype=pl.String)

    return pl.col(column).map_batches(_map, return_dtype=pl.String)


USAGE_SCHEMA = {
    "domain": pl.String, "raw_value": pl.String, "canonical": pl.String, "basis": pl.String,
    "matched_on": pl.String, "score": pl.Float64, "suggestions": pl.String, "line_count": pl.UInt32,
    "source_refs": pl.String, "needs_confirmation": pl.Boolean,
}


def term_usage(observations: list[tuple[str, pl.DataFrame, str]]) -> pl.DataFrame:
    """Every raw value seen per domain, how it resolved, and where it appears.

    observations: (domain, frame with source_tab/source_row, raw column name)
    """
    frames = []
    for domain, frame, column in observations:
        if frame.is_empty():
            continue
        grouped = (
            frame.filter(pl.col(column).is_not_null())
            .sort("source_tab", "source_row")
            .group_by(column, maintain_order=True)
            .agg(pl.len().alias("line_count"),
                 pl.concat_str(pl.col("source_tab"), pl.lit("!"), pl.col("source_row").cast(pl.String)).str.join(", ").alias("source_refs"))
        )
        dom = registry().domain(domain)
        rows = []
        for raw, count, refs in grouped.iter_rows():
            r = dom.resolve(raw)
            rows.append({"domain": domain, "raw_value": raw, "canonical": r.canonical, "basis": r.basis,
                         "matched_on": r.matched_on, "score": r.score, "suggestions": r.suggestions,
                         "line_count": count, "source_refs": refs,
                         "needs_confirmation": r.canonical is None or r.basis in NEEDS_CONFIRMATION})
        frames.append(pl.DataFrame(rows, schema=USAGE_SCHEMA))
    if not frames:
        return pl.DataFrame(schema=USAGE_SCHEMA)
    usage = pl.concat(frames)
    # The same raw value can be observed from several tables in one domain; merge them.
    return (
        usage.group_by("domain", "raw_value")
        .agg(pl.all().exclude("line_count", "source_refs").first(), pl.col("line_count").sum(),
             pl.col("source_refs").str.join(", "))
        .select(list(USAGE_SCHEMA)).sort("domain", "canonical", "raw_value", nulls_last=True)
    )


def pattern_usage(domain: str, frame: pl.DataFrame, column: str, canonical: str, basis: str, rule: str) -> pl.DataFrame:
    """Usage rows for values resolved by a pattern rather than an alias (e.g. "Transferred to BE Jul-26")."""
    if frame.is_empty():
        return pl.DataFrame(schema=USAGE_SCHEMA)
    grouped = frame.filter(pl.col(column).is_not_null()).sort("source_tab", "source_row").group_by(column, maintain_order=True).agg(
        pl.len().alias("line_count"),
        pl.concat_str(pl.col("source_tab"), pl.lit("!"), pl.col("source_row").cast(pl.String)).str.join(", ").alias("source_refs"))
    return grouped.select(
        pl.lit(domain).alias("domain"), pl.col(column).alias("raw_value"), pl.lit(canonical).alias("canonical"),
        pl.lit(basis).alias("basis"), pl.lit(rule).alias("matched_on"), pl.lit(1.0).alias("score"),
        pl.lit(None, dtype=pl.String).alias("suggestions"), pl.col("line_count").cast(pl.UInt32), "source_refs",
        pl.lit(False).alias("needs_confirmation"),
    )


def reference_tables(reg: Registry | None = None) -> dict[str, pl.DataFrame]:
    reg = reg or registry()
    canon = [{"domain": d.name, "canonical": c, "code": d.attributes.get(c) or None} for d in reg.domains.values() for c in d.canonicals]
    aliases = [{"domain": d.name, "key": k, "written": w, "canonical": c, "basis": b}
               for d in reg.domains.values() for k, (c, b, w) in d.entries.items()]
    return {"canonical": pl.DataFrame(canon), "aliases": pl.DataFrame(aliases).sort("domain", "canonical", "key")}
