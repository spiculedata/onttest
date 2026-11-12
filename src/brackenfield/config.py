"""Paths and business constants for the pipeline.

Business constants come straight from the workbook's READ ME tab, so they are
documented here once and referenced everywhere else.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# READ ME: "GST is 10%."
GST_RATE = 0.10
# READ ME: "We count a week as 5 working days and a month as 22."
WORKING_DAYS_PER_WEEK = 5
WORKING_DAYS_PER_MONTH = 22
# READ ME: "Last touched 31 Oct 2026." / BE Plant: "Printed 31/10/2026".
REGISTER_AS_OF = date(2026, 10, 31)

EARLIEST_PLAUSIBLE_YEAR = 1990
SECONDS_PER_HOUR = 3600


@dataclass(frozen=True)
class FieldTraxSettings:
    base_url: str
    client_id: str
    client_secret: str
    max_retries: int = 6
    timeout_seconds: float = 10.0

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.client_id and self.client_secret)


@dataclass(frozen=True)
class Settings:
    workbook_path: Path = PROJECT_ROOT / "brackenfield-plant-register.xlsx"
    database_path: Path = PROJECT_ROOT / "warehouse" / "brackenfield.duckdb"
    export_dir: Path = PROJECT_ROOT / "out"
    docs_dir: Path = PROJECT_ROOT / "docs"
    as_of: date = REGISTER_AS_OF
    fieldtrax: FieldTraxSettings = field(
        default_factory=lambda: FieldTraxSettings(
            base_url=os.environ.get("FIELDTRAX_BASE_URL", ""),
            client_id=os.environ.get("FIELDTRAX_CLIENT_ID", ""),
            client_secret=os.environ.get("FIELDTRAX_CLIENT_SECRET", ""),
        )
    )
