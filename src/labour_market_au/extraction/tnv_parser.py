"""
Total New Vacancies (TNV) Excel parser.

Parses the TNV workbook (3 sheets: Notes, Region, Occupation) into
long-format records suitable for database loading.

Region sheet: Level, Region_Name, Jurisdiction, State_Name, <quarterly periods>
Occupation sheet: ANZSCO Level, ANZSCO Code, Occupation Name, <quarterly periods>
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger("labour_market_au.extraction.tnv_parser")


def _format_period(col) -> str:
    """Format a period column (datetime or string) to 'Mon YYYY'."""
    if hasattr(col, "strftime"):
        return col.strftime("%b %Y")
    return str(col).strip()


def _parse_region_sheet(df: pd.DataFrame) -> list[dict]:
    """Parse the Region sheet into long-format records.

    Columns: Level, Region_Name, Jurisdiction, State_Name, <period datetimes>
    """
    cols = list(df.columns)
    id_cols = cols[:4]  # Level, Region_Name, Jurisdiction, State_Name
    period_cols = [c for c in cols[4:] if not pd.isna(c)]

    if not period_cols:
        return []

    # Filter out empty rows
    name_col = cols[1]  # Region_Name
    df = df[df[name_col].astype(str).str.strip().ne("")]
    df = df[~df[name_col].astype(str).str.strip().str.lower().isin(["nan"])]
    df = df.dropna(how="all")

    melted = df.melt(
        id_vars=id_cols,
        value_vars=period_cols,
        var_name="_period_raw",
        value_name="value",
    )

    period_lookup = {c: _format_period(c) for c in period_cols}
    melted["period"] = melted["_period_raw"].map(period_lookup)

    # Coerce values to numeric ('-' -> NaN)
    melted["value"] = pd.to_numeric(
        melted["value"].replace({"-": None, "": None, ".": None}),
        errors="coerce",
    )

    # Map Jurisdiction to geo_type
    _jurisdiction_to_geo_type = {
        "national": "national",
        "state": "state",
        "sa4": "sa4",
        "sa4 sub": "sa4_sub",
    }

    records: list[dict] = []
    for _, row in melted.iterrows():
        val = row["value"]
        if val is not None and pd.isna(val):
            val = None
        jurisdiction = str(row[cols[2]]).strip().lower()
        geo_type = _jurisdiction_to_geo_type.get(jurisdiction, "")
        records.append({
            "dimension_type": "region",
            "level": int(row[cols[0]]),
            "anzsco_code": "",
            "anzsco_title": "",
            "geo_type": geo_type,
            "geo_area": str(row[cols[1]]).strip(),
            "parent_geo": str(row[cols[3]]).strip(),
            "period": row["period"],
            "value": val,
        })

    return records


def _parse_occupation_sheet(df: pd.DataFrame) -> list[dict]:
    """Parse the Occupation sheet into long-format records.

    Columns: ANZSCO Level, ANZSCO Code, Occupation Name, <period datetimes>
    """
    cols = list(df.columns)
    id_cols = cols[:3]  # ANZSCO Level, ANZSCO Code, Occupation Name
    period_cols = [c for c in cols[3:] if not pd.isna(c)]

    if not period_cols:
        return []

    # Filter out empty rows
    name_col = cols[2]  # Occupation Name
    df = df[df[name_col].astype(str).str.strip().ne("")]
    df = df[~df[name_col].astype(str).str.strip().str.lower().isin(["nan"])]
    df = df.dropna(how="all")

    melted = df.melt(
        id_vars=id_cols,
        value_vars=period_cols,
        var_name="_period_raw",
        value_name="value",
    )

    period_lookup = {c: _format_period(c) for c in period_cols}
    melted["period"] = melted["_period_raw"].map(period_lookup)

    # Coerce values to numeric ('-' -> NaN)
    melted["value"] = pd.to_numeric(
        melted["value"].replace({"-": None, "": None, ".": None}),
        errors="coerce",
    )

    records: list[dict] = []
    for _, row in melted.iterrows():
        val = row["value"]
        if val is not None and pd.isna(val):
            val = None

        # ANZSCO Code as string (int->str for clean codes)
        raw_code = row[cols[1]]
        if raw_code is None or (isinstance(raw_code, float) and pd.isna(raw_code)):
            code = ""
        else:
            code = str(int(raw_code)) if isinstance(raw_code, (int, float)) and not pd.isna(raw_code) else str(raw_code).strip()

        records.append({
            "dimension_type": "occupation",
            "level": int(row[cols[0]]),
            "anzsco_code": code,
            "anzsco_title": str(row[cols[2]]).strip(),
            "geo_type": "",
            "geo_area": "",
            "parent_geo": "",
            "period": row["period"],
            "value": val,
        })

    return records


def parse_tnv_excel(filepath: Path) -> list[dict]:
    """Parse a TNV Excel workbook into a list of record dicts.

    Each dict has keys: dimension_type, level, code, name, geo_area, period, value.
    """
    logger.info("Parsing TNV file: %s", filepath.name)

    records: list[dict] = []
    try:
        with pd.ExcelFile(filepath) as xlsx:
            sheet_map = {s.lower(): s for s in xlsx.sheet_names}

            if "region" in sheet_map:
                df = pd.read_excel(xlsx, sheet_name=sheet_map["region"], header=0)
                df = df.dropna(how="all")
                region_recs = _parse_region_sheet(df)
                records.extend(region_recs)
                logger.info("Region sheet: %d records", len(region_recs))

            if "occupation" in sheet_map:
                df = pd.read_excel(xlsx, sheet_name=sheet_map["occupation"], header=0)
                df = df.dropna(how="all")
                occ_recs = _parse_occupation_sheet(df)
                records.extend(occ_recs)
                logger.info("Occupation sheet: %d records", len(occ_recs))

    except Exception as e:
        logger.error("Failed to parse TNV file %s: %s", filepath.name, e)
        raise

    logger.info("Parsed %d TNV records from %s", len(records), filepath.name)
    return records


def extract_tnv_notes(filepath: Path) -> dict | None:
    """Extract Notes sheet content from a TNV Excel workbook.

    Returns a dict with dataset, file_type, source_type, source_ref,
    note_text, note_tables, and content_hash. Returns None if no Notes sheet.
    """
    try:
        with pd.ExcelFile(filepath) as xlsx:
            sheet_names_lower = {s.lower(): s for s in xlsx.sheet_names}
            if "notes" not in sheet_names_lower:
                return None

            df = pd.read_excel(
                xlsx,
                sheet_name=sheet_names_lower["notes"],
                header=None,
            )
    except Exception as e:
        logger.error("Failed to read Notes sheet from %s: %s", filepath.name, e)
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
    table_regions: list[tuple[int, int]] = []  # (start, end) inclusive
    i = 0
    while i < len(in_table):
        if in_table[i]:
            start = i
            while i < len(in_table) and in_table[i]:
                i += 1
            end = i - 1  # inclusive
            if end - start + 1 >= 3:
                table_regions.append((start, end))
        else:
            i += 1

    # Build set of row indices belonging to tables
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

    # Compute content hash
    hash_input = note_text + json.dumps(tables, sort_keys=True)
    content_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

    return {
        "dataset": "total_vacancies",
        "file_type": "",
        "source_type": "excel_notes_sheet",
        "source_ref": filepath.name,
        "note_text": note_text,
        "note_tables": tables,
        "content_hash": content_hash,
    }
