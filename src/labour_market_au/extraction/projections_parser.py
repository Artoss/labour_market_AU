"""
Employment Projections Excel parser.

Parses the 6-table Employment Projections workbook into long-format records.

Each table has a consistent layout:
  - Rows 0-6: metadata/blank
  - Row 7: header row 1 (measure group labels)
  - Row 8: header row 2 (sub-headers with years)
  - Row 9+: data rows

Tables:
  1. Industry Division: 3 ID cols, 10 measures (with shares)
  2. Major Occupation: 3 ID cols, 10 measures (with shares)
  3. Skill Level: 1 ID col, 8 measures (no shares)
  4. State & Territory: 1 ID col, 8 measures (no shares)
  5. Industry Group: 4 ID cols, 7 measures (no shares)
  6. Occupation Unit Group: 5 ID cols, 7 measures (no shares)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

logger = logging.getLogger("labour_market_au.extraction.projections_parser")


@dataclass
class _SheetSpec:
    """Specification for parsing one projections table sheet."""
    sheet_prefix: str       # Matched against sheet names (case-insensitive startswith)
    dimension_type: str     # e.g. "industry_division"
    num_id_cols: int        # Number of leading ID columns
    code_col_idx: int | None  # Which ID col has the code (None = no code col)
    name_col_idx: int       # Which ID col has the name/label
    code_target: str        # Output field: "anzsco_code"|"industry_code"|"state"|""
    name_target: str        # Output field: "occupation_name"|"industry_name"|""
    has_share: bool         # Whether share-of-employment cols exist
    total_markers: list[str] = field(default_factory=lambda: ["total"])


_SHEET_SPECS: list[_SheetSpec] = [
    _SheetSpec(
        sheet_prefix="table_1",
        dimension_type="industry_division",
        num_id_cols=3,
        code_col_idx=1,
        name_col_idx=2,
        code_target="industry_code",
        name_target="industry_name",
        has_share=True,
        total_markers=["total"],
    ),
    _SheetSpec(
        sheet_prefix="table_2",
        dimension_type="major_occupation",
        num_id_cols=3,
        code_col_idx=1,
        name_col_idx=2,
        code_target="anzsco_code",
        name_target="occupation_name",
        has_share=True,
        total_markers=["total"],
    ),
    _SheetSpec(
        sheet_prefix="table_3",
        dimension_type="skill_level",
        num_id_cols=1,
        code_col_idx=None,
        name_col_idx=0,
        code_target="",
        name_target="occupation_name",
        has_share=True,
        total_markers=["total"],
    ),
    _SheetSpec(
        sheet_prefix="table_4",
        dimension_type="state_territory",
        num_id_cols=1,
        code_col_idx=None,
        name_col_idx=0,
        code_target="",
        name_target="",
        has_share=True,
        total_markers=["total", "australia"],
    ),
    _SheetSpec(
        sheet_prefix="table_5",
        dimension_type="industry_group",
        num_id_cols=4,
        code_col_idx=2,
        name_col_idx=3,
        code_target="industry_code",
        name_target="industry_name",
        has_share=False,
        total_markers=["total"],
    ),
    _SheetSpec(
        sheet_prefix="table_6",
        dimension_type="occupation_unit_group",
        num_id_cols=5,
        code_col_idx=2,
        name_col_idx=3,
        code_target="anzsco_code",
        name_target="occupation_name",
        has_share=False,
        total_markers=["total"],
    ),
]


def _clean_code(raw) -> str:
    """Clean a code value from Excel: handle float->int conversion, NaN, etc."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    s = str(raw).strip()
    if s.lower() == "nan" or not s:
        return ""
    # Convert "1111.0" -> "1111", "11.0" -> "11", but keep "A" as-is
    try:
        f = float(s)
        if f == int(f):
            return str(int(f))
    except (ValueError, TypeError, OverflowError):
        pass
    return s


def _extract_years(header_row: pd.Series, num_id_cols: int) -> list[int]:
    """Extract projection years from the sub-header row.

    Looks for patterns like 'May 2025', '2030', etc. in measure columns.
    Returns sorted unique years found.
    """
    years: set[int] = set()
    for val in header_row.iloc[num_id_cols:]:
        s = str(val).strip()
        if not s or s == "nan":
            continue
        # Match "May 2025" or just "2025" or "2030('000)" etc
        for m in re.finditer(r"(\d{4})", s):
            yr = int(m.group(1))
            if 2000 <= yr <= 2100:
                years.add(yr)
    return sorted(years)


def _parse_sheet(df_raw: pd.DataFrame, spec: _SheetSpec, base_year: int) -> list[dict]:
    """Parse a single projections table sheet into record dicts.

    Args:
        df_raw: Raw DataFrame read with header=None, skiprows=7.
            Row 0 = sub-header, Row 1+ = data.
        spec: Sheet specification.
        base_year: The baseline year (earliest year found in headers).

    Returns:
        List of record dicts ready for DB upsert.
    """
    if df_raw.empty or len(df_raw) < 2:
        return []

    # Row 0 might be sub-header (old format) or main header (new format)
    sub_header = df_raw.iloc[0]
    years = _extract_years(sub_header, spec.num_id_cols)
    if len(years) < 2 and len(df_raw) > 2:
        # New format: row 0 = main header, row 1 = sub-header with years
        sub_header = df_raw.iloc[1]
        years = _extract_years(sub_header, spec.num_id_cols)
        data = df_raw.iloc[2:].reset_index(drop=True)
    else:
        data = df_raw.iloc[1:].reset_index(drop=True)

    if len(years) < 2:
        logger.warning(
            "Could not extract enough years from sub-header for %s, got %s",
            spec.dimension_type, years,
        )
        return []

    # Determine measure column positions after ID cols
    measure_start = spec.num_id_cols

    if spec.has_share:
        # Layout: 3 levels + 3 shares + 2 change(5yr) + 2 change(10yr) = 10
        # Levels: base, mid, end
        # Shares: base, mid, end
        # Change 5yr: level, %
        # Change 10yr: level, %
        expected_measures = 10
    else:
        # Layout: 3 levels + 2 change(5yr) + 2 change(10yr) = 7
        expected_measures = 7

    # Count available numeric-ish columns after ID cols
    avail_cols = len(data.columns) - measure_start

    # Trim trailing empty columns
    while avail_cols > expected_measures:
        col_idx = measure_start + avail_cols - 1
        if col_idx < len(data.columns) and data.iloc[:, col_idx].isna().all():
            avail_cols -= 1
        else:
            break

    if avail_cols < expected_measures:
        logger.warning(
            "Sheet %s: expected %d measure cols, found %d",
            spec.dimension_type, expected_measures, avail_cols,
        )
        return []

    # Build measure mapping: (col_offset, measure_name, projection_year)
    yr_base = years[0]
    yr_mid = years[1] if len(years) >= 2 else years[0] + 5
    yr_end = years[2] if len(years) >= 3 else yr_mid + 5

    measures: list[tuple[int, str, int]] = []
    offset = 0
    # Employment levels: base, mid, end
    measures.append((offset, "employment_level", yr_base))
    offset += 1
    measures.append((offset, "employment_level", yr_mid))
    offset += 1
    measures.append((offset, "employment_level", yr_end))
    offset += 1

    if spec.has_share:
        # Employment shares: base, mid, end
        measures.append((offset, "employment_share", yr_base))
        offset += 1
        measures.append((offset, "employment_share", yr_mid))
        offset += 1
        measures.append((offset, "employment_share", yr_end))
        offset += 1

    # Growth 5yr: level, %
    measures.append((offset, "growth_level_5yr", yr_mid))
    offset += 1
    measures.append((offset, "growth_rate_5yr", yr_mid))
    offset += 1
    # Growth 10yr: level, %
    measures.append((offset, "growth_level_10yr", yr_end))
    offset += 1
    measures.append((offset, "growth_rate_10yr", yr_end))
    offset += 1

    records: list[dict] = []

    for _, row in data.iterrows():
        # Get name value for filtering
        name_val = str(row.iloc[spec.name_col_idx]).strip()
        if not name_val or name_val.lower() == "nan":
            continue

        # Skip total/note rows
        name_lower = name_val.lower()
        if any(marker in name_lower for marker in spec.total_markers):
            continue
        if name_lower.startswith("note"):
            continue

        # Extract code
        code = ""
        if spec.code_col_idx is not None:
            raw_code = row.iloc[spec.code_col_idx]
            code = _clean_code(raw_code)
            if not code:
                continue

        # Build base record fields
        base_rec: dict = {
            "dimension_type": spec.dimension_type,
            "anzsco_code": "",
            "occupation_name": "",
            "industry_code": "",
            "industry_name": "",
            "geo_area": "",
            "geo_type": "",
            "base_year": yr_base,
        }

        # Set code target
        if spec.code_target == "anzsco_code":
            base_rec["anzsco_code"] = code
        elif spec.code_target == "industry_code":
            base_rec["industry_code"] = code
        elif spec.code_target == "state":
            base_rec["geo_area"] = name_val
            base_rec["geo_type"] = "state"

        # For skill_level: extract number from name like "Skill Level 1"
        if spec.dimension_type == "skill_level":
            m = re.search(r"(\d+)", name_val)
            if m:
                base_rec["anzsco_code"] = m.group(1)

        # For state_territory: put name in geo_area field
        if spec.dimension_type == "state_territory":
            base_rec["geo_area"] = name_val
            base_rec["geo_type"] = "state"

        # Set name target
        if spec.name_target == "occupation_name":
            base_rec["occupation_name"] = name_val
        elif spec.name_target == "industry_name":
            base_rec["industry_name"] = name_val

        # Emit one record per measure
        for col_offset, measure_name, proj_year in measures:
            col_idx = measure_start + col_offset
            if col_idx >= len(row):
                continue

            raw_val = row.iloc[col_idx]
            value = None
            if raw_val is not None and not (isinstance(raw_val, float) and pd.isna(raw_val)):
                try:
                    value = float(raw_val)
                except (ValueError, TypeError):
                    value = None

            rec = dict(base_rec)
            rec["measure"] = measure_name
            rec["projection_year"] = proj_year
            rec["value"] = value
            records.append(rec)

    return records


def _match_spec(sheet_name: str) -> _SheetSpec | None:
    """Find the spec matching a sheet name by prefix."""
    lower = sheet_name.strip().lower().replace(" ", "_")
    for spec in _SHEET_SPECS:
        if lower.startswith(spec.sheet_prefix):
            return spec
    return None


def parse_projections_excel(filepath: Path) -> list[dict]:
    """Parse an Employment Projections Excel workbook into record dicts.

    Each dict has keys: dimension_type, anzsco_code, occupation_name,
    industry_code, industry_name, state, measure, base_year,
    projection_year, value.
    """
    logger.info("Parsing projections file: %s", filepath.name)

    records: list[dict] = []
    try:
        with pd.ExcelFile(filepath) as xlsx:
            for sheet_name in xlsx.sheet_names:
                spec = _match_spec(sheet_name)
                if spec is None:
                    logger.debug("Skipping unrecognized sheet: '%s'", sheet_name)
                    continue

                logger.info(
                    "Processing sheet '%s' -> dimension_type=%s",
                    sheet_name, spec.dimension_type,
                )

                df_raw = pd.read_excel(
                    xlsx,
                    sheet_name=sheet_name,
                    header=None,
                    skiprows=7,
                )

                # Extract base year from sub-header
                if df_raw.empty:
                    continue
                sub_header = df_raw.iloc[0]
                years = _extract_years(sub_header, spec.num_id_cols)
                if len(years) < 2 and len(df_raw) > 1:
                    # New format: row 0 = main header, row 1 = sub-header
                    years = _extract_years(df_raw.iloc[1], spec.num_id_cols)
                base_year = years[0] if years else 2025

                sheet_records = _parse_sheet(df_raw, spec, base_year)
                records.extend(sheet_records)
                logger.info(
                    "  Sheet '%s': %d records", sheet_name, len(sheet_records),
                )

    except Exception as e:
        logger.error("Failed to parse projections file %s: %s", filepath.name, e)
        raise

    logger.info("Parsed %d projections records from %s", len(records), filepath.name)
    return records
