"""
IVI (Internet Vacancy Index) Excel parser.
Normalizes IVI Excel workbooks into long-format records.

IVI file types (9 total, determined by filename):
  anzsco4_state         -- ANZSCO4 by states/territories
  anzsco4_remoteness    -- ANZSCO4 by JSA remoteness areas
  anzsco2_state         -- ANZSCO2 by states/territories
  anzsco2_gccsa         -- ANZSCO2 by GCCSA/SA4 regions
  anzsco2_region        -- ANZSCO2 by IVI regions
  skill_level_state     -- Skill level by states/territories
  skill_level_remoteness -- Skill level by JSA remoteness areas
  skill_level_gccsa     -- Skill level by GCCSA/SA4 regions
  skill_level_region    -- Skill level by IVI regions

Region variants have different column layouts and sheet names from base types.
The geographic column (region/remoteness/GCCSA) is stored in the 'geo_area' field.
The file_type distinguishes geographic classification in the database.

All files:
  - Header at row 0 (pandas default).
  - Period columns are datetimes starting from column 3 or 4.
  - Missing values can be '.' or NaN.
  - "Notes" sheet is skipped.
  - Uses pandas melt for fast wide-to-long conversion.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger("labour_market_au.extraction.ivi_parser")

# File type classification by filename regex (specific patterns before generic)
_FILE_TYPE_PATTERNS: list[tuple[str, str]] = [
    # ANZSCO4 (specific before generic)
    (r"anzsco4.*remoteness", "anzsco4_remoteness"),
    (r"anzsco4.*occupations", "anzsco4_state"),
    # Skill level (specific before generic -- both naming conventions)
    (r"skill_level.*remoteness", "skill_level_remoteness"),
    (r"skill_level.*gccsa", "skill_level_gccsa"),
    (r"skill_level.*region", "skill_level_region"),
    (r"anzsco_skill_level.*remoteness", "skill_level_remoteness"),
    (r"anzsco_skill_level.*gccsa", "skill_level_gccsa"),
    (r"anzsco_skill_level.*region", "skill_level_region"),
    (r"anzsco_skill_level", "skill_level_state"),
    (r"skill_level.*states?\b", "skill_level_state"),
    # ANZSCO2 (specific before generic)
    (r"anzsco2.*gccsa", "anzsco2_gccsa"),
    (r"anzsco2.*region", "anzsco2_region"),
    (r"anzsco2.*occupations", "anzsco2_state"),
]

# Sheet name to index_type mapping
_SHEET_TYPE_MAP: list[tuple[str, str]] = [
    (r"^seasonally\s+adjusted\s+index$", "seasonally_adjusted_index"),
    (r"^seasonally\s+adjusted$", "seasonally_adjusted"),
    (r"^trend\s+index$", "trend_index"),
    (r"^trend$", "trend"),
    (r"4\s*digit\s*3\s*month\s*average", "three_month_average"),
    # Region file sheets
    (r"^averaged$", "averaged"),
    (r"^indexed$", "indexed"),
    (r"^jsa\s+remoteness$", "jsa_remoteness"),
    (r"^jsa\s+northern\s+australia$", "jsa_northern_australia"),
]

# Sheets to skip (not data)
_SKIP_SHEETS = {"notes", "concordance"}

# Map file_type to geographic classification
_FILE_TYPE_TO_GEO_TYPE: dict[str, str] = {
    "anzsco4_state": "state",
    "anzsco4_remoteness": "remoteness",
    "anzsco2_state": "state",
    "anzsco2_gccsa": "gccsa",
    "anzsco2_region": "ivi_region",
    "skill_level_state": "state",
    "skill_level_remoteness": "remoteness",
    "skill_level_gccsa": "gccsa",
    "skill_level_region": "ivi_region",
}


def _classify_file(filepath: Path) -> str | None:
    """Classify an IVI file by filename into a file type key."""
    name = filepath.name.lower()
    for pattern, file_type in _FILE_TYPE_PATTERNS:
        if re.search(pattern, name):
            return file_type
    return None


def _classify_sheet(sheet_name: str) -> str | None:
    """Classify a sheet name into an index_type or None if unrecognized."""
    lower = sheet_name.strip().lower()
    if lower in _SKIP_SHEETS:
        return None
    for pattern, index_type in _SHEET_TYPE_MAP:
        if re.search(pattern, lower):
            return index_type
    return None


def _format_period(col) -> str:
    """Format a period column (datetime or string) to 'Mon YYYY'."""
    if hasattr(col, "strftime"):
        return col.strftime("%b %Y")
    return str(col).strip()


def _melt_to_records(
    df: pd.DataFrame,
    id_cols: list[str],
    index_type: str,
    col_map: dict[str, str],
    file_type: str = "",
    geo_type: str = "",
) -> list[dict]:
    """Melt a wide dataframe into long-format IVI records.

    Args:
        df: DataFrame with id columns + period date columns.
        id_cols: Column names to keep as identifiers.
        index_type: The index_type value for all records.
        col_map: Mapping from df column names to output dict keys.
        file_type: Source file type (e.g. 'anzsco4_state').
        geo_type: Geographic classification (e.g. 'state', 'remoteness').
    """
    id_set = set(id_cols)
    period_cols = [c for c in df.columns if c not in id_set and not pd.isna(c)]
    if not period_cols:
        return []

    melted = df.melt(
        id_vars=id_cols,
        value_vars=period_cols,
        var_name="_period_raw",
        value_name="value",
    )

    # Build period lookup for datetime columns
    period_lookup = {c: _format_period(c) for c in period_cols}
    melted["period"] = melted["_period_raw"].map(period_lookup)

    # Parse values: coerce to numeric, treating '.' and '-' as NaN
    melted["value"] = pd.to_numeric(
        melted["value"].replace({".": None, "-": None, "": None}),
        errors="coerce",
    )

    # Rename columns per col_map, drop intermediates
    out = melted.rename(columns=col_map)
    out["index_type"] = index_type

    # Ensure all expected output columns exist
    for key in ("anzsco_code", "anzsco_title", "geo_area", "skill_level"):
        if key not in out.columns:
            out[key] = ""

    # Convert string columns to str, fill NaN
    for col in ("anzsco_code", "anzsco_title", "geo_area", "skill_level"):
        out[col] = out[col].astype(str).str.strip().replace("nan", "")

    out["file_type"] = file_type
    out["geo_type"] = geo_type

    # Select output columns and convert to list of dicts
    result_cols = ["anzsco_code", "anzsco_title", "geo_area", "skill_level",
                   "period", "value", "index_type", "file_type", "geo_type"]
    records = out[result_cols].to_dict("records")

    # Replace NaN with None (to_dict preserves float nan)
    for rec in records:
        if rec["value"] is not None and pd.isna(rec["value"]):
            rec["value"] = None

    return records


def _parse_anzsco4_sheet(
    df: pd.DataFrame, index_type: str, file_type: str = "anzsco4_state",
    geo_type: str = "",
) -> list[dict]:
    """Parse ANZSCO4 sheet: ANZSCO_CODE, ANZSCO_TITLE, state, <periods>."""
    cols = list(df.columns)
    code_col, title_col, state_col = cols[0], cols[1], cols[2]
    id_cols = [code_col, title_col, state_col]

    # Filter out invalid rows
    df = df[df[code_col].astype(str).str.strip().ne("")]
    df = df[~df[code_col].astype(str).str.strip().str.lower().isin(["nan"])]

    return _melt_to_records(df, id_cols, index_type, {
        code_col: "anzsco_code",
        title_col: "anzsco_title",
        state_col: "geo_area",
    }, file_type=file_type, geo_type=geo_type)


def _parse_anzsco2_sheet(
    df: pd.DataFrame, index_type: str, file_type: str = "anzsco2_state",
    geo_type: str = "",
) -> list[dict]:
    """Parse ANZSCO2 sheet: Level, ANZSCO_CODE, Title, State, <periods>."""
    cols = list(df.columns)
    level_col, code_col, title_col, state_col = cols[0], cols[1], cols[2], cols[3]
    id_cols = [level_col, code_col, title_col, state_col]

    # Filter out rows with empty codes
    df = df[df[code_col].astype(str).str.strip().ne("")]
    df = df[~df[code_col].astype(str).str.strip().str.lower().isin(["nan"])]

    return _melt_to_records(df, id_cols, index_type, {
        code_col: "anzsco_code",
        title_col: "anzsco_title",
        state_col: "geo_area",
    }, file_type=file_type, geo_type=geo_type)


def _parse_skill_level_sheet(
    df: pd.DataFrame, index_type: str, file_type: str = "skill_level_state",
    geo_type: str = "",
) -> list[dict]:
    """Parse skill level sheet: Level, Title, State, Skill_level, <periods>."""
    cols = list(df.columns)
    level_col, title_col, state_col, skill_col = cols[0], cols[1], cols[2], cols[3]
    id_cols = [level_col, title_col, state_col, skill_col]

    # Filter out rows with empty titles
    df = df[df[title_col].astype(str).str.strip().ne("")]
    df = df[~df[title_col].astype(str).str.strip().str.lower().isin(["nan"])]

    return _melt_to_records(df, id_cols, index_type, {
        title_col: "anzsco_title",
        state_col: "geo_area",
        skill_col: "skill_level",
    }, file_type=file_type, geo_type=geo_type)


def _parse_anzsco4_remoteness_sheet(
    df: pd.DataFrame, index_type: str, file_type: str = "anzsco4_remoteness",
    geo_type: str = "",
) -> list[dict]:
    """Parse ANZSCO4 remoteness sheet: Level, ANZSCO_CODE, ANZSCO_TITLE, region, <periods>."""
    cols = list(df.columns)
    level_col, code_col, title_col, region_col = cols[0], cols[1], cols[2], cols[3]
    id_cols = [level_col, code_col, title_col, region_col]

    df = df[df[code_col].astype(str).str.strip().ne("")]
    df = df[~df[code_col].astype(str).str.strip().str.lower().isin(["nan"])]

    return _melt_to_records(df, id_cols, index_type, {
        code_col: "anzsco_code",
        title_col: "anzsco_title",
        region_col: "geo_area",
    }, file_type=file_type, geo_type=geo_type)


def _parse_anzsco2_gccsa_sheet(
    df: pd.DataFrame, index_type: str, file_type: str = "anzsco2_gccsa",
    geo_type: str = "",
) -> list[dict]:
    """Parse ANZSCO2 GCCSA sheet: Level, State, region_name, region_code,
    region_level, ANZSCO_CODE, ANZSCO_TITLE, <periods>.

    Stores region_name in the 'geo_area' field.
    """
    cols = list(df.columns)
    level_col = cols[0]       # Level
    state_col = cols[1]       # State
    rname_col = cols[2]       # region_name
    rcode_col = cols[3]       # region_code
    rlevel_col = cols[4]      # region_level
    code_col = cols[5]        # ANZSCO_CODE
    title_col = cols[6]       # ANZSCO_TITLE
    id_cols = [level_col, state_col, rname_col, rcode_col, rlevel_col,
               code_col, title_col]

    df = df[df[code_col].astype(str).str.strip().ne("")]
    df = df[~df[code_col].astype(str).str.strip().str.lower().isin(["nan"])]

    return _melt_to_records(df, id_cols, index_type, {
        code_col: "anzsco_code",
        title_col: "anzsco_title",
        rname_col: "geo_area",
    }, file_type=file_type, geo_type=geo_type)


def _parse_anzsco2_region_sheet(
    df: pd.DataFrame, index_type: str, file_type: str = "anzsco2_region",
    geo_type: str = "",
) -> list[dict]:
    """Parse ANZSCO2 IVI region sheet: Level, State, region, ANZSCO_CODE,
    ANZSCO_TITLE, <periods>.

    Stores region in the 'geo_area' field.
    """
    cols = list(df.columns)
    level_col, state_col, region_col = cols[0], cols[1], cols[2]
    code_col, title_col = cols[3], cols[4]
    id_cols = [level_col, state_col, region_col, code_col, title_col]

    df = df[df[code_col].astype(str).str.strip().ne("")]
    df = df[~df[code_col].astype(str).str.strip().str.lower().isin(["nan"])]

    return _melt_to_records(df, id_cols, index_type, {
        code_col: "anzsco_code",
        title_col: "anzsco_title",
        region_col: "geo_area",
    }, file_type=file_type, geo_type=geo_type)


# Dispatch table: file_type -> parser function
_PARSERS = {
    "anzsco4_state": _parse_anzsco4_sheet,
    "anzsco4_remoteness": _parse_anzsco4_remoteness_sheet,
    "anzsco2_state": _parse_anzsco2_sheet,
    "anzsco2_gccsa": _parse_anzsco2_gccsa_sheet,
    "anzsco2_region": _parse_anzsco2_region_sheet,
    "skill_level_state": _parse_skill_level_sheet,
    "skill_level_remoteness": _parse_skill_level_sheet,
    "skill_level_gccsa": _parse_skill_level_sheet,
    "skill_level_region": _parse_skill_level_sheet,
}


def parse_ivi_excel(filepath: Path) -> list[dict]:
    """Parse an IVI Excel workbook into a list of record dicts.

    Each dict has keys: anzsco_code, anzsco_title, geo_area, skill_level,
    period, value, index_type, file_type.
    """
    logger.info("Parsing IVI file: %s", filepath.name)

    file_type = _classify_file(filepath)
    if file_type is None:
        logger.warning("Unrecognized IVI file type: %s", filepath.name)
        return []

    parse_fn = _PARSERS.get(file_type)
    if parse_fn is None:
        logger.warning("No parser for IVI file type '%s'", file_type)
        return []

    geo_type = _FILE_TYPE_TO_GEO_TYPE.get(file_type, "")

    records: list[dict] = []
    try:
        with pd.ExcelFile(filepath) as xlsx:
            for sheet_name in xlsx.sheet_names:
                index_type = _classify_sheet(sheet_name)
                if index_type is None:
                    logger.debug("Skipping sheet: '%s'", sheet_name)
                    continue

                logger.info(
                    "Processing sheet '%s' -> file_type=%s, index_type=%s",
                    sheet_name, file_type, index_type,
                )
                df = pd.read_excel(
                    xlsx,
                    sheet_name=sheet_name,
                    header=0,
                    na_values=["-", ".."],
                )
                df = df.dropna(how="all")
                sheet_records = parse_fn(
                    df, index_type, file_type=file_type, geo_type=geo_type,
                )
                records.extend(sheet_records)

    except Exception as e:
        logger.error("Failed to parse IVI file %s: %s", filepath.name, e)
        raise

    logger.info("Parsed %d IVI records from %s", len(records), filepath.name)
    return records


def extract_ivi_notes(filepath: Path) -> dict | None:
    """Extract Notes sheet content from an IVI Excel workbook.

    Returns a dict with dataset, file_type, source_type, source_ref,
    note_text, note_tables, and content_hash. Returns None if no Notes
    sheet, unrecognized file type, or no content.
    """
    file_type = _classify_file(filepath)
    if file_type is None:
        return None

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
        # First row of the block is the header
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
        "dataset": "ivi",
        "file_type": file_type,
        "source_type": "excel_notes_sheet",
        "source_ref": filepath.name,
        "note_text": note_text,
        "note_tables": tables,
        "content_hash": content_hash,
    }
