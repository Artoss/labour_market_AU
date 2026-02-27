"""
SALM (Small Area Labour Markets) Excel parser.
Normalizes SALM Excel workbooks into long-format records.

SALM Excel structure:
  - Multiple sheets, e.g. "Smoothed SA2 unemployment rate",
    "Smoothed SA2 unemployment", "Smoothed SA2 labour force",
    and equivalent LGA sheets. Also handles older naming conventions.
  - Header row at index 3 (0-based), with period columns as datetimes.
  - Multi-index: columns 0,1 are geo_name and geo_code (index_col=[0,1]).
  - Missing values represented as '-'.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger("labour_market_au.extraction.salm_parser")

# Map sheet name patterns to (measure, geo_level)
# Handles both old format ("Smoothed unemployment rate (SA2)")
# and new format ("Smoothed SA2 unemployment rate", "Smoothed LGA unemployment rates")
SHEET_MAP = {
    r"unemployment\s+rates?\b.*\bsa2\b": ("unemployment_rate", "sa2"),
    r"\bsa2\b.*unemployment\s+rates?": ("unemployment_rate", "sa2"),
    r"unemployed\s+persons?\b.*\bsa2\b": ("unemployed_persons", "sa2"),
    r"\bsa2\b.*\bunemployment\b(?!.*\brate)": ("unemployed_persons", "sa2"),
    r"\bsa2\b.*\bunemployed\b": ("unemployed_persons", "sa2"),
    r"labour\s+force.*\bsa2\b": ("labour_force", "sa2"),
    r"\bsa2\b.*labour\s+force": ("labour_force", "sa2"),
    r"unemployment\s+rates?\b.*\blga\b": ("unemployment_rate", "lga"),
    r"\blga\b.*unemployment\s+rates?": ("unemployment_rate", "lga"),
    r"unemployed\s+persons?\b.*\blga\b": ("unemployed_persons", "lga"),
    r"\blga\b.*\bunemployment\b(?!.*\brate)": ("unemployed_persons", "lga"),
    r"\blga\b.*\bunemployed\b": ("unemployed_persons", "lga"),
    r"labour\s+force.*\blga\b": ("labour_force", "lga"),
    r"\blga\b.*labour\s+force": ("labour_force", "lga"),
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
                    index_col=[0, 1],
                    na_values="-",
                )

                # The index levels are (geo_name, geo_code) after index_col=[0,1]
                # Drop any fully-empty rows
                df = df.dropna(how="all")

                # Period columns: may be strings or datetimes
                period_cols = [c for c in df.columns if not pd.isna(c)]

                for (geo_name, geo_code), row in df.iterrows():
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

                        # Normalize period to "Mon YYYY" string
                        if hasattr(period_col, "strftime"):
                            period_str = period_col.strftime("%b %Y")
                        else:
                            period_str = str(period_col).strip()

                        records.append({
                            "geo_code": geo_code_str,
                            "geo_name": geo_name_str,
                            "geo_level": geo_level,
                            "measure": measure,
                            "period": period_str,
                            "value": value,
                            "smoothed": True,
                        })

    except Exception as e:
        logger.error("Failed to parse SALM file %s: %s", filepath.name, e)
        raise

    logger.info("Parsed %d SALM records from %s", len(records), filepath.name)
    return records
