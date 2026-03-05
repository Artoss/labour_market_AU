"""Tests for Total New Vacancies (TNV) parser."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from labour_market_au.extraction.tnv_parser import (
    extract_tnv_notes,
    parse_tnv_excel,
)


# --- Helpers to build synthetic Excel files ---

_REGION_PERIODS = [datetime(2019, 2, 1), datetime(2019, 5, 1), datetime(2019, 8, 1)]
_OCCUPATION_PERIODS = [datetime(2016, 2, 1), datetime(2016, 5, 1)]


def _write_region_sheet(writer: pd.ExcelWriter) -> None:
    """Write a synthetic Region sheet."""
    cols = ["Level", "Region_Name", "Jurisdiction", "State_Name"] + _REGION_PERIODS
    rows = [
        [0, "Australia", "National", "National", 1184000, 1066400, 1034700],
        [1, "New South Wales", "State", "New South Wales", 500000, 480000, 470000],
        [2, "Sydney - Inner", "SA4", "New South Wales", 100000, 95000, 92000],
        [3, "Sydney CBD", "SA4 sub", "New South Wales", 50000, 48000, 46000],
    ]
    df = pd.DataFrame(rows, columns=cols)
    df.to_excel(writer, sheet_name="Region", index=False)


def _write_occupation_sheet(writer: pd.ExcelWriter) -> None:
    """Write a synthetic Occupation sheet."""
    cols = ["ANZSCO Level", "ANZSCO Code", "Occupation Name"] + _OCCUPATION_PERIODS
    rows = [
        [1, 1, "Managers", 122900, 123400],
        [2, 11, "Chief Executives", 4200, 4200],
        [2, 12, "Farmers and Farm Managers", 500, "-"],
    ]
    df = pd.DataFrame(rows, columns=cols)
    df.to_excel(writer, sheet_name="Occupation", index=False)


def _write_notes_sheet(writer: pd.ExcelWriter) -> None:
    """Write a synthetic Notes sheet with prose and a concordance table."""
    rows = [
        ["TNV uses REOS survey data.", None, None],
        [None, None, None],
        ["Caveats", None, None],
        ["Use caution when interpreting.", None, None],
        [None, None, None],
        ["SA4 Name", "JSA Remoteness", "Northern Australia"],
        ["Capital Region", "Regional", "No"],
        ["Central Coast", "Major City", "No"],
        ["Coffs Harbour", "Regional", "No"],
    ]
    df = pd.DataFrame(rows)
    df.to_excel(writer, sheet_name="Notes", index=False, header=False)


def _write_full_workbook(path: Path) -> None:
    """Write a synthetic TNV workbook with all 3 sheets."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_notes_sheet(writer)
        _write_region_sheet(writer)
        _write_occupation_sheet(writer)


# --- Region sheet tests ---


def test_parse_region_sheet(tmp_path):
    path = tmp_path / "tnv.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_region_sheet(writer)

    records = parse_tnv_excel(path)
    # 4 rows x 3 periods = 12
    assert len(records) == 12
    assert all(r["dimension_type"] == "region" for r in records)
    assert all(r["anzsco_code"] == "" for r in records)


def test_parse_region_hierarchy_levels(tmp_path):
    path = tmp_path / "tnv.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_region_sheet(writer)

    records = parse_tnv_excel(path)
    levels = {r["level"] for r in records}
    assert levels == {0, 1, 2, 3}


def test_parse_geo_area_populated(tmp_path):
    path = tmp_path / "tnv.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_region_sheet(writer)
        _write_occupation_sheet(writer)

    records = parse_tnv_excel(path)
    region_recs = [r for r in records if r["dimension_type"] == "region"]
    occ_recs = [r for r in records if r["dimension_type"] == "occupation"]

    # Region records have geo_area from Region_Name (the actual area)
    assert all(r["geo_area"] != "" for r in region_recs)
    # Region records have parent_geo from State_Name
    assert any(r["parent_geo"] == "New South Wales" for r in region_recs)
    # Region records have geo_type derived from Jurisdiction
    geo_types = {r["geo_type"] for r in region_recs}
    assert "national" in geo_types
    assert "state" in geo_types
    assert "sa4" in geo_types
    # Occupation records have empty geo_area
    assert all(r["geo_area"] == "" for r in occ_recs)


# --- Occupation sheet tests ---


def test_parse_occupation_sheet(tmp_path):
    path = tmp_path / "tnv.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_occupation_sheet(writer)

    records = parse_tnv_excel(path)
    # 3 rows x 2 periods = 6
    assert len(records) == 6
    assert all(r["dimension_type"] == "occupation" for r in records)

    # ANZSCO codes are strings
    codes = {r["anzsco_code"] for r in records}
    assert codes == {"1", "11", "12"}
    assert all(isinstance(r["anzsco_code"], str) for r in records)


def test_parse_period_format(tmp_path):
    path = tmp_path / "tnv.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_region_sheet(writer)

    records = parse_tnv_excel(path)
    periods = {r["period"] for r in records}
    assert periods == {"Feb 2019", "May 2019", "Aug 2019"}


def test_parse_missing_values(tmp_path):
    """'-' values in occupation sheet should become None."""
    path = tmp_path / "tnv.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_occupation_sheet(writer)

    records = parse_tnv_excel(path)
    # "Farmers and Farm Managers" has '-' for May 2016
    farmer_may = [
        r for r in records
        if r["anzsco_code"] == "12" and r["period"] == "May 2016"
    ]
    assert len(farmer_may) == 1
    assert farmer_may[0]["value"] is None


# --- Full workbook ---


def test_parse_full_workbook(tmp_path):
    path = tmp_path / "tnv.xlsx"
    _write_full_workbook(path)

    records = parse_tnv_excel(path)
    # Region: 4 rows x 3 periods = 12
    # Occupation: 3 rows x 2 periods = 6
    assert len(records) == 18

    dim_types = {r["dimension_type"] for r in records}
    assert dim_types == {"region", "occupation"}


# --- Notes extraction tests ---


def test_extract_notes_prose_and_table(tmp_path):
    path = tmp_path / "tnv.xlsx"
    _write_full_workbook(path)

    note = extract_tnv_notes(path)
    assert note is not None
    assert note["dataset"] == "total_vacancies"
    assert note["file_type"] == ""
    assert note["source_type"] == "excel_notes_sheet"

    # Prose should contain introductory text
    assert "TNV" in note["note_text"] or "REOS" in note["note_text"]

    # Should have extracted the concordance table
    assert len(note["note_tables"]) >= 1
    table = note["note_tables"][0]
    assert "SA4 Name" in table["headers"]
    assert len(table["rows"]) >= 3


def test_extract_notes_no_sheet(tmp_path):
    """Workbook without Notes sheet returns None."""
    path = tmp_path / "tnv.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_region_sheet(writer)

    note = extract_tnv_notes(path)
    assert note is None


def test_extract_notes_content_hash(tmp_path):
    """Same content produces same hash."""
    path1 = tmp_path / "tnv1.xlsx"
    path2 = tmp_path / "tnv2.xlsx"
    _write_full_workbook(path1)
    _write_full_workbook(path2)

    note1 = extract_tnv_notes(path1)
    note2 = extract_tnv_notes(path2)
    assert note1 is not None and note2 is not None
    assert note1["content_hash"] == note2["content_hash"]
