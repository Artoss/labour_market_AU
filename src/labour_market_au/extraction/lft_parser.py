"""
Labour Force Trending (LFT) Excel parser.

Parses LFT workbooks (4 file types) into long-format records.
Only Table_2 (timeseries) is parsed; Table_1 (summary) and Table_3 (subset)
are skipped.

File types:
  national_industry   -- ANZSIC industry at national level
  national_occupation -- ANZSCO occupation at national level
  state_industry      -- ANZSIC industry by state/territory
  state_occupation    -- ANZSCO occupation by state/territory

Layout (Table_2, header at row 7):
  National industry:   ANZSIC Level, NFD Indicator, Code (Text), ANZSIC Title, Industry 1 Digit Code, <periods>
  National occupation: ANZSCO Level, NFD Indicator, Code (Text), ANZSCO Title, Skill Level, <periods>
  State industry:      State, ANZSIC Level, NFD Indicator, Code (Text), ANZSIC Title, Industry 1 Digit Code, <periods>
  State occupation:    State, ANZSCO Level, NFD Indicator, Code (Text), ANZSCO Title, Skill Level, <periods>
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger("labour_market_au.extraction.lft_parser")

_FILE_TYPE_PATTERNS: list[tuple[str, str]] = [
    (r"national_industry", "national_industry"),
    (r"national_occupation", "national_occupation"),
    (r"state_industry", "state_industry"),
    (r"state_occupation", "state_occupation"),
]


def _classify_file(filename: str) -> str | None:
    """Classify an LFT file by filename into a file type key."""
    lower = filename.lower()
    for pattern, file_type in _FILE_TYPE_PATTERNS:
        if re.search(pattern, lower):
            return file_type
    return None


def _format_period(col) -> str:
    """Format a period column (datetime or string) to 'Mon YYYY'."""
    if hasattr(col, "strftime"):
        return col.strftime("%b %Y")
    return str(col).strip()


def _find_header_row(xlsx: pd.ExcelFile, sheet_name: str) -> int:
    """Find the header row in a Table_2 sheet by looking for 'Code (Text)'."""
    df_raw = pd.read_excel(xlsx, sheet_name=sheet_name, header=None, nrows=15)
    for idx in range(len(df_raw)):
        row_values = [str(v).strip() for v in df_raw.iloc[idx] if pd.notna(v)]
        if any("Code" in v for v in row_values):
            return idx
    return 7  # default for real LFT files


def _parse_timeseries_sheet(df: pd.DataFrame, file_type: str) -> list[dict]:
    """Parse a Table_2 timeseries sheet into long-format records.

    Uses pandas melt for vectorized wide-to-long conversion.
    """
    cols = list(df.columns)
    is_state = file_type.startswith("state_")
    is_occupation = file_type.endswith("_occupation")

    # Determine ID columns based on file_type
    if is_state:
        # State, Level, NFD, Code, Title, ParentCode
        state_col = cols[0]
        level_col = cols[1]
        nfd_col = cols[2]
        code_col = cols[3]
        title_col = cols[4]
        parent_col = cols[5]
        id_cols = cols[:6]
    else:
        # Level, NFD, Code, Title, ParentCode
        level_col = cols[0]
        nfd_col = cols[1]
        code_col = cols[2]
        title_col = cols[3]
        parent_col = cols[4]
        id_cols = cols[:5]
        state_col = None

    # Period columns are everything after id columns
    period_cols = [c for c in cols[len(id_cols):] if not pd.isna(c)]
    if not period_cols:
        return []

    # Filter out rows with empty codes
    df = df[df[code_col].astype(str).str.strip().ne("")]
    df = df[~df[code_col].astype(str).str.strip().str.lower().isin(["nan"])]
    df = df.dropna(how="all")

    if df.empty:
        return []

    # Melt wide to long
    melted = df.melt(
        id_vars=id_cols,
        value_vars=period_cols,
        var_name="_period_raw",
        value_name="value",
    )

    # Format periods
    period_lookup = {c: _format_period(c) for c in period_cols}
    melted["period"] = melted["_period_raw"].map(period_lookup)

    # Coerce values to numeric ('-' -> NaN)
    melted["value"] = pd.to_numeric(
        melted["value"].replace({"-": None, "": None, ".": None}),
        errors="coerce",
    )

    # Build output columns
    melted["file_type"] = file_type
    melted["code"] = melted[code_col].astype(str).str.strip()
    melted["title"] = melted[title_col].astype(str).str.strip()
    melted["level"] = pd.to_numeric(melted[level_col], errors="coerce").fillna(0).astype(int)
    melted["parent_code"] = melted[parent_col].astype(str).str.strip().replace({"-": "", "nan": ""})

    if is_state:
        melted["geo_area"] = melted[state_col].astype(str).str.strip()
        melted["geo_type"] = "state"
    else:
        melted["geo_area"] = ""
        melted["geo_type"] = "national"

    # Select output columns
    result_cols = [
        "file_type", "level", "code", "title", "geo_area", "geo_type",
        "parent_code", "period", "value",
    ]
    records = melted[result_cols].to_dict("records")

    # Replace NaN values with None
    for rec in records:
        if rec["value"] is not None and pd.isna(rec["value"]):
            rec["value"] = None

    return records


def parse_lft_excel(filepath: Path) -> list[dict]:
    """Parse an LFT Excel workbook into a list of record dicts.

    Only processes Table_2 (timeseries). Skips Contents, Table_1, Table_3.
    """
    logger.info("Parsing LFT file: %s", filepath.name)

    file_type = _classify_file(filepath.name)
    if file_type is None:
        logger.warning("Unrecognized LFT file type: %s", filepath.name)
        return []

    records: list[dict] = []
    try:
        with pd.ExcelFile(filepath) as xlsx:
            sheet_map = {s.lower(): s for s in xlsx.sheet_names}

            if "table_2" not in sheet_map:
                logger.warning("No Table_2 sheet in %s", filepath.name)
                return []

            header_row = _find_header_row(xlsx, sheet_map["table_2"])
            df = pd.read_excel(
                xlsx,
                sheet_name=sheet_map["table_2"],
                header=header_row,
            )
            df = df.dropna(how="all")
            records = _parse_timeseries_sheet(df, file_type)

    except Exception as e:
        logger.error("Failed to parse LFT file %s: %s", filepath.name, e)
        raise

    logger.info("Parsed %d LFT records from %s", len(records), filepath.name)
    return records


def extract_lft_notes(filepath: Path) -> dict | None:
    """Extract Contents sheet from an LFT workbook as notes.

    Returns a dict suitable for dataset_notes upsert, or None.
    """
    file_type = _classify_file(filepath.name)
    if file_type is None:
        return None

    try:
        with pd.ExcelFile(filepath) as xlsx:
            sheet_map = {s.lower(): s for s in xlsx.sheet_names}
            if "contents" not in sheet_map:
                return None

            df = pd.read_excel(
                xlsx,
                sheet_name=sheet_map["contents"],
                header=None,
            )
    except Exception as e:
        logger.error("Failed to read Contents sheet from %s: %s", filepath.name, e)
        return None

    if df.empty or df.isna().all().all():
        return None

    # Classify rows by fill count
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

    # Collect prose
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
        "dataset": "labour_force_trending",
        "file_type": file_type,
        "source_type": "excel_contents_sheet",
        "source_ref": filepath.name,
        "note_text": note_text,
        "note_tables": tables,
        "content_hash": content_hash,
    }
