"""Tests for Labour Force Trending (LFT) parser."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from labour_market_au.extraction.lft_parser import (
    _classify_file,
    extract_lft_notes,
    parse_lft_excel,
)


# --- Helpers to build synthetic Excel files ---

_PERIODS = [
    datetime(2024, 2, 1),
    datetime(2024, 5, 1),
    datetime(2024, 8, 1),
    datetime(2024, 11, 1),
]


def _write_blank_header_rows(writer: pd.ExcelWriter, sheet_name: str) -> None:
    """LFT files have 7 blank/title rows before the header at row 7.
    When we use header=7 in read_excel, pandas handles this automatically.
    For synthetic files, we just write the data sheet directly with header=0.
    """
    pass  # header=7 in real files; synthetic files use header=0 via to_excel


def _write_national_industry_table2(writer: pd.ExcelWriter) -> None:
    """Write a synthetic national industry Table_2 sheet."""
    cols = [
        "ANZSIC Level", "NFD Indicator", "Code (Text)",
        "ANZSIC Title", "Industry 1 Digit Code",
    ] + _PERIODS
    rows = [
        [1, "N", "A", "Agriculture, Forestry and Fishing", "A", 420.3, 421.2, 422.0, 423.1],
        [2, "N", "01", "Agriculture", "A", 200.1, 201.0, 202.5, 203.0],
        [2, "Y", "A0", "Agriculture nfd", "A", 0.1, 0.1, 0.1, 0.1],
    ]
    df = pd.DataFrame(rows, columns=cols)
    df.to_excel(writer, sheet_name="Table_2", index=False)


def _write_national_occupation_table2(writer: pd.ExcelWriter) -> None:
    """Write a synthetic national occupation Table_2 sheet."""
    cols = [
        "ANZSCO Level", "NFD Indicator", "Code (Text)",
        "ANZSCO Title", "Skill Level",
    ] + _PERIODS
    rows = [
        [1, "N", "1", "Managers", "-", 847.4, 856.3, 864.9, 870.0],
        [2, "N", "11", "Chief Executives", "1", 100.0, 101.0, 102.0, 103.0],
        [2, "N", "12", "Farmers and Farm Managers", "1", 50.0, 51.0, "-", 53.0],
    ]
    df = pd.DataFrame(rows, columns=cols)
    df.to_excel(writer, sheet_name="Table_2", index=False)


def _write_state_industry_table2(writer: pd.ExcelWriter) -> None:
    """Write a synthetic state industry Table_2 sheet."""
    cols = [
        "State", "ANZSIC Level", "NFD Indicator", "Code (Text)",
        "ANZSIC Title", "Industry 1 Digit Code",
    ] + _PERIODS
    rows = [
        ["NSW", 1, "N", "A", "Agriculture", "A", 100.0, 101.0, 102.0, 103.0],
        ["NSW", 2, "N", "01", "Farming", "A", 50.0, 51.0, 52.0, 53.0],
        ["NSW", 3, "N", "011", "Nursery", "A", 10.0, 11.0, 12.0, 13.0],
        ["VIC", 1, "N", "A", "Agriculture", "A", 90.0, 91.0, 92.0, 93.0],
        ["VIC", 2, "N", "01", "Farming", "A", 45.0, 46.0, 47.0, 48.0],
        ["VIC", 3, "N", "011", "Nursery", "A", 9.0, 9.5, 10.0, 10.5],
    ]
    df = pd.DataFrame(rows, columns=cols)
    df.to_excel(writer, sheet_name="Table_2", index=False)


def _write_state_occupation_table2(writer: pd.ExcelWriter) -> None:
    """Write a synthetic state occupation Table_2 sheet."""
    cols = [
        "State", "ANZSCO Level", "NFD Indicator", "Code (Text)",
        "ANZSCO Title", "Skill Level",
    ] + _PERIODS
    rows = [
        ["NSW", 1, "N", "1", "Managers", "-", 200.0, 201.0, 202.0, 203.0],
        ["NSW", 2, "N", "11", "Chief Executives", "1", 50.0, 51.0, 52.0, 53.0],
        ["VIC", 1, "N", "1", "Managers", "-", 180.0, 181.0, 182.0, 183.0],
        ["VIC", 2, "N", "11", "Chief Executives", "1", 45.0, 46.0, 47.0, 48.0],
    ]
    df = pd.DataFrame(rows, columns=cols)
    df.to_excel(writer, sheet_name="Table_2", index=False)


def _write_contents_sheet(writer: pd.ExcelWriter) -> None:
    """Write a synthetic Contents sheet with prose metadata."""
    rows = [
        ["Labour Force Trending Data", None, None],
        ["Source: ABS Labour Force Survey", None, None],
        [None, None, None],
        ["Table", "Description", "Coverage"],
        ["Table_1", "Summary statistics", "Current quarter"],
        ["Table_2", "Quarterly timeseries", "Aug 1986 onwards"],
        ["Table_3", "Level 1 industries", "Aug 1986 onwards"],
    ]
    df = pd.DataFrame(rows)
    df.to_excel(writer, sheet_name="Contents", index=False, header=False)


def _write_table1_sheet(writer: pd.ExcelWriter) -> None:
    """Write a dummy Table_1 (summary) sheet -- should be skipped."""
    df = pd.DataFrame({"Summary": ["dummy"]})
    df.to_excel(writer, sheet_name="Table_1", index=False)


# --- File classification tests ---


def test_classify_file_national_industry():
    assert _classify_file("national_industry_trend_-_november_2025.xlsx") == "national_industry"


def test_classify_file_national_occupation():
    assert _classify_file("national_occupation_trend_-_november_2025.xlsx") == "national_occupation"


def test_classify_file_state_industry():
    assert _classify_file("state_industry_trend_-_november_2025.xlsx") == "state_industry"


def test_classify_file_state_occupation():
    assert _classify_file("state_occupation_trend_-_november_2025.xlsx") == "state_occupation"


def test_classify_file_unknown():
    assert _classify_file("random_file.xlsx") is None


# --- National industry tests ---


def test_national_industry_record_count(tmp_path):
    path = tmp_path / "national_industry_trend.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_national_industry_table2(writer)

    records = parse_lft_excel(path)
    # 3 rows x 4 periods = 12
    assert len(records) == 12


def test_national_industry_fields(tmp_path):
    path = tmp_path / "national_industry_trend.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_national_industry_table2(writer)

    records = parse_lft_excel(path)
    # Check first record
    r = [r for r in records if r["code"] == "A" and r["period"] == "Feb 2024"][0]
    assert r["file_type"] == "national_industry"
    assert r["level"] == 1
    assert r["title"] == "Agriculture, Forestry and Fishing"
    assert r["geo_area"] == ""
    assert r["geo_type"] == "national"
    assert r["parent_code"] == "A"
    assert abs(r["value"] - 420.3) < 0.01


def test_national_industry_nfd_included(tmp_path):
    path = tmp_path / "national_industry_trend.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_national_industry_table2(writer)

    records = parse_lft_excel(path)
    nfd_recs = [r for r in records if r["code"] == "A0"]
    assert len(nfd_recs) == 4  # 4 periods


# --- National occupation tests ---


def test_national_occupation_record_count(tmp_path):
    path = tmp_path / "national_occupation_trend.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_national_occupation_table2(writer)

    records = parse_lft_excel(path)
    # 3 rows x 4 periods = 12
    assert len(records) == 12


def test_national_occupation_skill_level(tmp_path):
    """parent_code populated from Skill Level column."""
    path = tmp_path / "national_occupation_trend.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_national_occupation_table2(writer)

    records = parse_lft_excel(path)
    r = [r for r in records if r["code"] == "11"][0]
    assert r["parent_code"] == "1"

    # Skill Level = '-' for top-level -> parent_code = ''
    r = [r for r in records if r["code"] == "1"][0]
    assert r["parent_code"] == ""


# --- State industry tests ---


def test_state_industry_record_count(tmp_path):
    path = tmp_path / "state_industry_trend.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_state_industry_table2(writer)

    records = parse_lft_excel(path)
    # 6 rows x 4 periods = 24
    assert len(records) == 24


def test_state_geo_area_populated(tmp_path):
    path = tmp_path / "state_industry_trend.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_state_industry_table2(writer)

    records = parse_lft_excel(path)
    geo_areas = {r["geo_area"] for r in records}
    assert geo_areas == {"NSW", "VIC"}
    assert all(r["geo_type"] == "state" for r in records)


# --- State occupation tests ---


def test_state_occupation_record_count(tmp_path):
    path = tmp_path / "state_occupation_trend.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_state_occupation_table2(writer)

    records = parse_lft_excel(path)
    # 4 rows x 4 periods = 16
    assert len(records) == 16


# --- Period and value tests ---


def test_period_format(tmp_path):
    path = tmp_path / "national_industry_trend.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_national_industry_table2(writer)

    records = parse_lft_excel(path)
    periods = {r["period"] for r in records}
    assert periods == {"Feb 2024", "May 2024", "Aug 2024", "Nov 2024"}


def test_missing_values(tmp_path):
    """'-' values should become None."""
    path = tmp_path / "national_occupation_trend.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_national_occupation_table2(writer)

    records = parse_lft_excel(path)
    farmer_aug = [
        r for r in records
        if r["code"] == "12" and r["period"] == "Aug 2024"
    ]
    assert len(farmer_aug) == 1
    assert farmer_aug[0]["value"] is None


# --- Full workbook tests ---


def test_full_workbook(tmp_path):
    """Parsing a workbook with Contents + Table_1 + Table_2 only processes Table_2."""
    path = tmp_path / "national_industry_trend.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_contents_sheet(writer)
        _write_table1_sheet(writer)
        _write_national_industry_table2(writer)

    records = parse_lft_excel(path)
    assert len(records) == 12
    assert all(r["file_type"] == "national_industry" for r in records)


# --- Notes extraction tests ---


def test_extract_notes(tmp_path):
    path = tmp_path / "national_industry_trend.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_contents_sheet(writer)
        _write_national_industry_table2(writer)

    note = extract_lft_notes(path)
    assert note is not None
    assert note["dataset"] == "labour_force_trending"
    assert note["file_type"] == "national_industry"
    assert note["source_type"] == "excel_contents_sheet"
    assert "Labour Force" in note["note_text"] or "ABS" in note["note_text"]


def test_extract_notes_content_hash(tmp_path):
    """Same content produces same hash."""
    path1 = tmp_path / "national_industry_trend_1.xlsx"
    path2 = tmp_path / "national_industry_trend_2.xlsx"
    for p in (path1, path2):
        with pd.ExcelWriter(p, engine="openpyxl") as writer:
            _write_contents_sheet(writer)
            _write_national_industry_table2(writer)

    note1 = extract_lft_notes(path1)
    note2 = extract_lft_notes(path2)
    assert note1 is not None and note2 is not None
    assert note1["content_hash"] == note2["content_hash"]


def test_extract_notes_no_contents_sheet(tmp_path):
    """Workbook without Contents sheet returns None."""
    path = tmp_path / "national_industry_trend.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_national_industry_table2(writer)

    note = extract_lft_notes(path)
    assert note is None


def test_unrecognized_file_returns_empty(tmp_path):
    """Unrecognized filename returns empty list."""
    path = tmp_path / "random_file.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_national_industry_table2(writer)

    records = parse_lft_excel(path)
    assert records == []
