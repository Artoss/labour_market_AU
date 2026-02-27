"""
SALM (Small Area Labour Markets) Excel parser.
Normalizes SALM Excel workbooks into long-format records.

SALM Excel structure:
  - Multiple sheets: "Smoothed unemployment rate (SA2)",
    "Smoothed unemployed persons (SA2)", "Smoothed labour force (SA2)",
    and equivalent LGA sheets.
  - Header row at index 3 (0-based), with period columns (e.g. "Jun 2024").
  - Multi-index: columns 0,1 are geo_name and geo_code (reversed: index_col=[1,0]).
  - Missing values represented as '-'.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger("labour_market_au.extraction.salm_parser")

# Map sheet name patterns to (measure, geo_level)
SHEET_MAP = {
    r"unemployment\s+rate.*sa2": ("unemployment_rate", "sa2"),
    r"unemployed\s+persons.*sa2": ("unemployed_persons", "sa2"),
    r"labour\s+force.*sa2": ("labour_force", "sa2"),
    r"unemployment\s+rate.*lga": ("unemployment_rate", "lga"),
    r"unemployed\s+persons.*lga": ("unemployed_persons", "lga"),
    r"labour\s+force.*lga": ("labour_force", "lga"),
}


def _classify_sheet(sheet_name: str) -> tuple[str, str] | None:
    """Classify a sheet name into (measure, geo_level) or None if unrecognized."""
    lower = sheet_name.lower()
    for pattern, (measure, geo_level) in SHEET_MAP.items():
        if re.search(pattern, lower):
            return measure, geo_level
    return None


def parse_salm_excel(filepath: Path) -> list[dict]:
    """Parse a SALM Excel workbook into a list of record dicts.

    Each dict has keys: geo_code, geo_name, geo_level, measure, period, value, smoothed.
    """
    records: list[dict] = []
    logger.info("Parsing SALM file: %s", filepath.name)

    try:
        with pd.ExcelFile(filepath) as xlsx:
            for sheet_name in xlsx.sheet_names:
                classification = _classify_sheet(sheet_name)
                if classification is None:
                    logger.debug("Skipping unrecognized sheet: '%s'", sheet_name)
                    continue

                measure, geo_level = classification
                logger.info(
                    "Processing sheet '%s' -> measure=%s, geo_level=%s",
                    sheet_name, measure, geo_level,
                )

                df = pd.read_excel(
                    xlsx,
                    sheet_name=sheet_name,
                    header=3,
                    index_col=[1, 0],
                    na_values="-",
                )

                # The index levels are (geo_code, geo_name) after index_col=[1,0]
                # Drop any fully-empty rows
                df = df.dropna(how="all")

                # Period columns are everything that's not in the index
                period_cols = [c for c in df.columns if isinstance(c, str)]

                for (geo_code, geo_name), row in df.iterrows():
                    geo_code_str = str(geo_code).strip()
                    geo_name_str = str(geo_name).strip()

                    if not geo_code_str or geo_code_str.lower() == "nan":
                        continue

                    for period_col in period_cols:
                        val = row.get(period_col)
                        if pd.isna(val):
                            value = None
                        else:
                            try:
                                value = float(val)
                            except (ValueError, TypeError):
                                value = None

                        records.append({
                            "geo_code": geo_code_str,
                            "geo_name": geo_name_str,
                            "geo_level": geo_level,
                            "measure": measure,
                            "period": str(period_col).strip(),
                            "value": value,
                            "smoothed": True,
                        })

    except Exception as e:
        logger.error("Failed to parse SALM file %s: %s", filepath.name, e)
        raise

    logger.info("Parsed %d SALM records from %s", len(records), filepath.name)
    return records
