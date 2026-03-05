"""
RLMI (Regional Labour Market Indicator) Excel parser.

Parses the RLMI workbook with 3 sheets:
  - Contents: methodology prose (captured as dataset notes)
  - <Month Year>: current snapshot with ratings + 10 indicators
  - Historical Timeseries: quarterly ratings 1-5 since 2012

Produces long-format records suitable for database loading.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger("labour_market_au.extraction.rlmi_parser")

_RATING_TEXT_TO_VALUE = {
    "Strong": 1,
    "Above average": 2,
    "Average": 3,
    "Below average": 4,
    "Poor": 5,
}
_RATING_VALUE_TO_TEXT = {v: k for k, v in _RATING_TEXT_TO_VALUE.items()}

# Ordered indicator measure names matching columns 3-12 in the snapshot sheet
_INDICATOR_MEASURES = [
    "working_age_employment_rate",
    "unemployment_rate",
    "prop_jobseeker_income_support",
    "prop_jobseeker_2plus_years",
    "job_vacancy_rate",
    "job_matching_efficiency_rate",
    "underemployment_rate",
    "vacancy_fill_rate",
    "annual_median_income_growth_rate",
    "skill_underutilisation_rate",
]


def _format_period(col) -> str:
    """Format a period column (datetime or string) to 'Mon YYYY'."""
    if hasattr(col, "strftime"):
        return col.strftime("%b %Y")
    return str(col).strip()


def _clean_sa4_code(raw) -> str:
    """Convert SA4 code to string, handling float/int/NaN."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    if isinstance(raw, (int, float)) and not pd.isna(raw):
        return str(int(raw))
    s = str(raw).strip()
    return s if s.lower() != "nan" else ""


def _clean_name(raw: str) -> str:
    """Strip footnote markers (trailing digits) from names."""
    return re.sub(r"\d+$", "", str(raw)).strip()


def _is_footnote_row(row, ncols: int) -> bool:
    """Detect footnote rows: text in col 0, rest empty."""
    val0 = row.iloc[0]
    if pd.isna(val0):
        return False
    s = str(val0).strip()
    if not s:
        return False
    # Footnotes start with a digit or a superscript reference
    if s[0].isdigit() and not s.isdigit():
        # Check that remaining cols are empty
        for ci in range(2, min(ncols, 5)):
            if pd.notna(row.iloc[ci]) and str(row.iloc[ci]).strip():
                return False
        return True
    return False


def _parse_snapshot_sheet(df: pd.DataFrame) -> list[dict]:
    """Parse the snapshot sheet into long-format records.

    Layout:
      Row 6: column headers
      Row 7: per-indicator reference periods (datetimes)
      Row 8: annotations
      Rows 9+: data (until footnote rows)
      Col 0: SA4 Code; Col 1: SA4 Name; Col 2: Rating text
      Cols 3-12: 10 indicator measures
    """
    if len(df) < 10:
        return []

    ncols = len(df.columns)

    # Extract per-indicator reference periods from row 7
    indicator_periods: list[str] = []
    for ci in range(3, min(3 + len(_INDICATOR_MEASURES), ncols)):
        raw = df.iloc[7, ci]
        indicator_periods.append(_format_period(raw) if pd.notna(raw) else "")

    records: list[dict] = []
    for ri in range(9, len(df)):
        row = df.iloc[ri]

        # Stop at footnote rows
        if _is_footnote_row(row, ncols):
            break

        # Need at least a name in col 1
        name_raw = row.iloc[1] if ncols > 1 else None
        if pd.isna(name_raw) or not str(name_raw).strip():
            # Check col 0 as well
            code_raw = row.iloc[0] if ncols > 0 else None
            if pd.isna(code_raw) or not str(code_raw).strip():
                continue

        sa4_code = _clean_sa4_code(row.iloc[0])
        sa4_name = _clean_name(str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else "")
        geo_type = "sa4" if sa4_code else "aggregate"

        # Rating (col 2)
        rating_text = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        rating_value = _RATING_TEXT_TO_VALUE.get(rating_text)

        # Determine overall rating period -- use the first indicator period
        # (snapshot sheet name gives the quarter, but per-indicator periods
        # from row 7 are more precise; the "Rating" itself is current quarter)
        rating_period = indicator_periods[0] if indicator_periods else ""

        # Emit overall_rating record (only if there's a rating)
        if rating_text and rating_value is not None:
            records.append({
                "data_source": "snapshot",
                "sa4_code": sa4_code,
                "sa4_name": sa4_name,
                "geo_type": geo_type,
                "measure": "overall_rating",
                "period": rating_period,
                "value": None,
                "rating_value": rating_value,
                "rating_text": rating_text,
            })

        # Emit indicator records (cols 3-12)
        for mi, measure in enumerate(_INDICATOR_MEASURES):
            ci = 3 + mi
            if ci >= ncols:
                break
            raw_val = row.iloc[ci]
            val = None
            if pd.notna(raw_val):
                try:
                    val = float(raw_val)
                except (ValueError, TypeError):
                    val = None

            period = indicator_periods[mi] if mi < len(indicator_periods) else ""
            records.append({
                "data_source": "snapshot",
                "sa4_code": sa4_code,
                "sa4_name": sa4_name,
                "geo_type": geo_type,
                "measure": measure,
                "period": period,
                "value": val,
                "rating_value": None,
                "rating_text": "",
            })

    return records


def _parse_timeseries_sheet(df: pd.DataFrame) -> list[dict]:
    """Parse the Historical Timeseries sheet into long-format records.

    Layout:
      Row 6: headers (SA4 Code, SA4 Name, then quarterly datetimes)
      Rows 7+: data (until footnote rows)
      Values: integers 1-5 (rating values)
    """
    if len(df) < 8:
        return []

    ncols = len(df.columns)

    # Period columns start at col 2
    period_cols: list[int] = []
    period_labels: dict[int, str] = {}
    for ci in range(2, ncols):
        raw = df.iloc[6, ci]
        if pd.notna(raw):
            label = _format_period(raw)
            if label:
                period_cols.append(ci)
                period_labels[ci] = label

    if not period_cols:
        return []

    records: list[dict] = []
    for ri in range(7, len(df)):
        row = df.iloc[ri]

        # Stop at footnote rows
        if _is_footnote_row(row, ncols):
            break

        # Need at least a name
        name_raw = row.iloc[1] if ncols > 1 else None
        if pd.isna(name_raw) or not str(name_raw).strip():
            continue

        sa4_code = _clean_sa4_code(row.iloc[0])
        sa4_name = _clean_name(str(row.iloc[1]).strip())
        geo_type = "sa4" if sa4_code else "aggregate"

        for ci in period_cols:
            raw_val = row.iloc[ci]
            if pd.isna(raw_val):
                continue
            try:
                rating_val = int(float(raw_val))
            except (ValueError, TypeError):
                continue

            records.append({
                "data_source": "timeseries",
                "sa4_code": sa4_code,
                "sa4_name": sa4_name,
                "geo_type": geo_type,
                "measure": "overall_rating",
                "period": period_labels[ci],
                "value": None,
                "rating_value": rating_val,
                "rating_text": _RATING_VALUE_TO_TEXT.get(rating_val, ""),
            })

    return records


def parse_rlmi_excel(filepath: Path) -> list[dict]:
    """Parse an RLMI Excel workbook into a list of record dicts."""
    logger.info("Parsing RLMI file: %s", filepath.name)

    records: list[dict] = []
    try:
        with pd.ExcelFile(filepath) as xlsx:
            sheet_names = xlsx.sheet_names

            # Identify snapshot sheet (not Contents, not Historical Timeseries)
            for sn in sheet_names:
                lower = sn.lower()
                if lower == "contents" or "historical" in lower or "timeseries" in lower:
                    continue
                # This is the snapshot sheet
                df = pd.read_excel(xlsx, sheet_name=sn, header=None)
                snap_recs = _parse_snapshot_sheet(df)
                records.extend(snap_recs)
                logger.info("Snapshot sheet '%s': %d records", sn, len(snap_recs))
                break

            # Historical Timeseries
            ts_name = None
            for sn in sheet_names:
                if "historical" in sn.lower() or "timeseries" in sn.lower():
                    ts_name = sn
                    break
            if ts_name:
                df = pd.read_excel(xlsx, sheet_name=ts_name, header=None)
                ts_recs = _parse_timeseries_sheet(df)
                records.extend(ts_recs)
                logger.info("Timeseries sheet '%s': %d records", ts_name, len(ts_recs))

    except Exception as e:
        logger.error("Failed to parse RLMI file %s: %s", filepath.name, e)
        raise

    logger.info("Parsed %d RLMI records from %s", len(records), filepath.name)
    return records


def extract_rlmi_notes(filepath: Path) -> dict | None:
    """Extract Contents sheet content from an RLMI Excel workbook.

    Returns a dict with dataset, file_type, source_type, source_ref,
    note_text, note_tables, and content_hash. Returns None if no Contents sheet.
    """
    try:
        with pd.ExcelFile(filepath) as xlsx:
            sheet_names_lower = {s.lower(): s for s in xlsx.sheet_names}
            if "contents" not in sheet_names_lower:
                return None

            df = pd.read_excel(
                xlsx,
                sheet_name=sheet_names_lower["contents"],
                header=None,
            )
    except Exception as e:
        logger.error("Failed to read Contents sheet from %s: %s", filepath.name, e)
        return None

    if df.empty or df.isna().all().all():
        return None

    # Classify each row: count non-empty cells
    row_fills = []
    for idx in range(len(df)):
        row = df.iloc[idx]
        non_empty = sum(
            1 for v in row
            if pd.notna(v) and str(v).strip() != ""
        )
        row_fills.append(non_empty)

    # Identify table regions: contiguous blocks of 3+ rows with 2+ filled cols
    in_table = [fill >= 2 for fill in row_fills]
    table_regions: list[tuple[int, int]] = []
    i = 0
    while i < len(in_table):
        if in_table[i]:
            start = i
            while i < len(in_table) and in_table[i]:
                i += 1
            end = i - 1
            if end - start + 1 >= 3:
                table_regions.append((start, end))
        else:
            i += 1

    table_rows: set[int] = set()
    for start, end in table_regions:
        table_rows.update(range(start, end + 1))

    # Collect prose text from non-table rows
    prose_lines: list[str] = []
    for idx in range(len(df)):
        if idx in table_rows:
            continue
        row = df.iloc[idx]
        for v in row:
            if pd.notna(v) and str(v).strip():
                prose_lines.append(str(v).strip())

    # Collect tables
    tables: list[dict] = []
    for start, end in table_regions:
        header_row = df.iloc[start]
        headers = [
            str(v).strip() if pd.notna(v) and str(v).strip() else f"col_{ci}"
            for ci, v in enumerate(header_row)
        ]
        rows: list[list[str]] = []
        for ri in range(start + 1, end + 1):
            data_row = df.iloc[ri]
            rows.append([
                str(v).strip() if pd.notna(v) else ""
                for v in data_row
            ])
        tables.append({"title": "", "headers": headers, "rows": rows})

    note_text = "\n".join(prose_lines)
    if not note_text and not tables:
        return None

    hash_input = note_text + json.dumps(tables, sort_keys=True)
    content_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

    return {
        "dataset": "rlmi",
        "file_type": "",
        "source_type": "excel_contents_sheet",
        "source_ref": filepath.name,
        "note_text": note_text,
        "note_tables": tables,
        "content_hash": content_hash,
    }
