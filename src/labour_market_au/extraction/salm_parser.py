"""
SALM (Small Area Labour Markets) Excel parser.
Normalizes SALM Excel workbooks into long-format records.

Smoothed SALM Excel structure:
  - Multiple sheets, e.g. "Smoothed SA2 unemployment rate",
    "Smoothed SA2 unemployment", "Smoothed SA2 labour force",
    and equivalent LGA sheets. Also handles older naming conventions.
  - Header row at index 3 (0-based), with period columns as datetimes.
  - Multi-index: columns 0,1 are geo_name and geo_code (index_col=[0,1]).
  - Missing values represented as '-'.

Unsmoothed SALM Excel structure:
  - Single sheet per file (e.g. "SA2 unsmoothed data file", "Unsmoothed LGA").
  - Header row at index 2 (0-based).
  - Column 0 is "Data Item" (measure), columns 1,2 are geo_name and geo_code.
  - Period columns start at column 3 as datetimes.
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

# Map "Data Item" values in unsmoothed files to measure keys
_UNSMOOTHED_MEASURE_MAP = {
    "unemployment rate": "unemployment_rate",
    "unemployment (persons)": "unemployed_persons",
    "labour force (persons)": "labour_force",
}


def _classify_sheet(sheet_name: str) -> tuple[str, str] | None:
    """Classify a sheet name into (measure, geo_level) or None if unrecognized."""
    lower = sheet_name.lower()
    for pattern, (measure, geo_level) in SHEET_MAP.items():
        if re.search(pattern, lower):
            return measure, geo_level
    return None


def _classify_unsmoothed_measure(data_item: str) -> str | None:
    """Map an unsmoothed 'Data Item' value to a measure key."""
    lower = data_item.lower().replace("unsmoothed", "").strip()
    for pattern, measure in _UNSMOOTHED_MEASURE_MAP.items():
        if pattern in lower:
            return measure
    return None


def _detect_unsmoothed_geo_level(filepath: Path, columns: list) -> str:
    """Detect geo_level from column names or filename for unsmoothed files."""
    col_str = " ".join(str(c).lower() for c in columns[:3])
    if "lga" in col_str:
        return "lga"
    if "sa2" in col_str:
        return "sa2"
    # Fallback to filename
    fname = filepath.name.lower()
    if "lga" in fname:
        return "lga"
    return "sa2"


def _parse_unsmoothed(filepath: Path) -> list[dict]:
    """Parse an unsmoothed SALM Excel file (single-sheet, Data Item column)."""
    records: list[dict] = []
    df = pd.read_excel(filepath, header=2, na_values="-")

    geo_level = _detect_unsmoothed_geo_level(filepath, list(df.columns))
    logger.info("Unsmoothed file geo_level=%s", geo_level)

    # Columns: Data Item, geo_name, geo_code, then period datetimes
    data_item_col = df.columns[0]
    geo_name_col = df.columns[1]
    geo_code_col = df.columns[2]
    period_cols = [c for c in df.columns[3:] if not pd.isna(c)]

    for _, row in df.iterrows():
        data_item = str(row[data_item_col]).strip()
        measure = _classify_unsmoothed_measure(data_item)
        if measure is None:
            continue

        geo_code_str = str(row[geo_code_col]).strip()
        geo_name_str = str(row[geo_name_col]).strip()
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

            if hasattr(period_col, "strftime"):
                period_str = period_col.strftime("%b %Y")
            else:
                period_str = str(period_col).strip()

            records.append({
                "geo_code": geo_code_str,
                "geo_name": geo_name_str,
                "geo_type": geo_level,
                "measure": measure,
                "period": period_str,
                "value": value,
                "smoothed": False,
            })

    return records


def _is_unsmoothed_file(filepath: Path) -> bool:
    """Check if file is an unsmoothed SALM file based on filename."""
    return "unsmoothed" in filepath.name.lower()


def parse_salm_excel(filepath: Path) -> list[dict]:
    """Parse a SALM Excel workbook into a list of record dicts.

    Each dict has keys: geo_code, geo_name, geo_level, measure, period, value, smoothed.
    Handles both smoothed (multi-sheet) and unsmoothed (single-sheet) formats.
    """
    records: list[dict] = []
    logger.info("Parsing SALM file: %s", filepath.name)

    try:
        if _is_unsmoothed_file(filepath):
            records = _parse_unsmoothed(filepath)
        else:
            with pd.ExcelFile(filepath) as xlsx:
                for sheet_name in xlsx.sheet_names:
                    classification = _classify_sheet(sheet_name)
                    if classification is None:
                        logger.debug("Skipping unrecognized sheet: '%s'", sheet_name)
                        continue

                    measure, geo_level = classification
                    smoothed = "unsmoothed" not in sheet_name.lower()
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
                                "geo_type": geo_level,
                                "measure": measure,
                                "period": period_str,
                                "value": value,
                                "smoothed": smoothed,
                            })

    except Exception as e:
        logger.error("Failed to parse SALM file %s: %s", filepath.name, e)
        raise

    logger.info("Parsed %d SALM records from %s", len(records), filepath.name)
    return records
