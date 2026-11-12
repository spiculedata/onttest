"""Fixed identifiers and naming helpers.

Term mappings (yard words, statuses, suppliers, depots, rate bases, GST) are master data
and live in `mdm/*.csv`, resolved by `brackenfield.mdm`. What stays here is structural:
the two businesses, fleet-number prefixes and how ids are built.
"""

from __future__ import annotations

import re

BUSINESSES = {
    "BE": "Brackenfield Earthworks",
    "NH": "Norland Haulage",
}

# Fleet-number prefix -> category, as used on both plant sheets.
FLEET_PREFIX_CATEGORY = {
    "EX": "Excavator 20t",
    "MX": "Excavator 5t",
    "SK": "Skid steer",
    "WC": "Water cart",
    "TP": "Tipper",
    "RL": "Roller",
    "LV": "Light vehicle",
    "GN": "Generator",
}

# NH Fleet: "Transferred to BE Jul-26". Rust-regex syntax, used from polars.
TRANSFER_STATUS_PATTERN = r"(?i)^transferred to (?P<business>BE|NH)\b\s*(?P<period>.*)$"

AU_STATES = ("ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def org_id_for_supplier(canonical: str) -> str:
    return f"org_{slug(canonical)}"


def org_id_for_business(code: str) -> str:
    return f"org_{code.lower()}"


def site_id_for(name: str) -> str:
    return f"site_{slug(name)}"
