"""Tests for IVI parser."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from labour_market_au.extraction.ivi_parser import (
    _classify_file,
    _classify_sheet,
    _format_period,
    extract_ivi_notes,
    parse_ivi_excel,
)


# --- File classification tests ---


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("internet_vacancies_anzsco4_occupations_states_and_territories_-_january_2026.xlsx", "anzsco4_state"),
        ("internet_vacancies_anzsco4_occupations_jsa_remoteness_and_northern_australia_classification_-_january_2026.xlsx", "anzsco4_remoteness"),
        ("internet_vacancies_anzsco2_occupations_states_and_territories_-_january_2026.xlsx", "anzsco2_state"),
        ("internet_vacancies_anzsco2_occupations_gccsa_and_sa4_regions_-_january_2026.xlsx", "anzsco2_gccsa"),
        ("internet_vacancies_anzsco2_occupations_ivi_regions_-_january_2026.xlsx", "anzsco2_region"),
        ("internet_vacancies_anzsco_skill_level_states_and_territories_-_january_2026.xlsx", "skill_level_state"),
        ("internet_vacancies_anzsco_skill_level_jsa_remoteness_-_january_2026.xlsx", "skill_level_remoteness"),
        ("internet_vacancies_anzsco_skill_level_gccsa_and_sa4_regions_-_january_2026.xlsx", "skill_level_gccsa"),
        ("internet_vacancies_anzsco_skill_level_ivi_regions_-_january_2026.xlsx", "skill_level_region"),
        ("internet_vacancies_skill_level_remoteness_-_january_2026.xlsx", "skill_level_remoteness"),
        ("internet_vacancies_skill_level_gccsa_-_january_2026.xlsx", "skill_level_gccsa"),
        ("internet_vacancies_skill_level_region_-_january_2026.xlsx", "skill_level_region"),
        ("unknown_file.xlsx", None),
    ],
)
def test_classify_file(filename, expected, tmp_path):
    fp = tmp_path / filename
    assert _classify_file(fp) == expected


# --- Sheet classification tests ---


@pytest.mark.parametrize(
    "sheet_name, expected",
    [
        ("Trend", "trend"),
        ("Trend Index", "trend_index"),
        ("Seasonally Adjusted", "seasonally_adjusted"),
        ("Seasonally Adjusted Index", "seasonally_adjusted_index"),
        ("4 digit 3 month average", "three_month_average"),
        ("Averaged", "averaged"),
        ("Indexed", "indexed"),
        ("JSA Remoteness", "jsa_remoteness"),
        ("JSA Northern Australia", "jsa_northern_australia"),
        ("Notes", None),
        ("Concordance", None),
        ("random sheet", None),
    ],
)
def test_classify_sheet(sheet_name, expected):
    assert _classify_sheet(sheet_name) == expected


# --- Period formatting ---


def test_format_period_datetime():
    dt = pd.Timestamp("2025-03-01")
    assert _format_period(dt) == "Mar 2025"


def test_format_period_string():
    assert _format_period("Jan 2020") == "Jan 2020"


# --- Parsing with synthetic Excel files ---


def _write_anzsco4_excel(path: Path) -> None:
    """Write a synthetic ANZSCO4 IVI Excel file."""
    data = {
        "ANZSCO_CODE": ["0", "1111", "1112"],
        "ANZSCO_TITLE": ["Australia Total", "Chief Executives", "General Managers"],
        "state": ["AUST", "AUST", "AUST"],
        pd.Timestamp("2024-01-01"): [100.0, 10.5, 20.3],
        pd.Timestamp("2024-02-01"): [105.0, 11.0, 21.0],
    }
    df = pd.DataFrame(data)
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"Notes": ["test"]}).to_excel(writer, sheet_name="Notes", index=False)
        df.to_excel(writer, sheet_name="4 digit 3 month average", index=False)


def _write_anzsco2_excel(path: Path) -> None:
    """Write a synthetic ANZSCO2 IVI Excel file."""
    data = {
        "Level": [1, 2, 3],
        "ANZSCO_CODE": ["0", "1", "11"],
        "Title": ["AUSTRALIAN TOTAL", "MANAGERS", "Chief Executives"],
        "State": ["AUST", "AUST", "AUST"],
        pd.Timestamp("2024-01-01"): [200.0, 50.0, 10.0],
        pd.Timestamp("2024-02-01"): [210.0, 52.0, 11.0],
    }
    df = pd.DataFrame(data)
    with pd.ExcelWriter(path) as writer:
        df.to_excel(writer, sheet_name="Trend", index=False)
        df.to_excel(writer, sheet_name="Seasonally Adjusted", index=False)


def _write_skill_level_excel(path: Path) -> None:
    """Write a synthetic skill level IVI Excel file."""
    data = {
        "Level": [0, 2, 2],
        "Title": ["AUSTRALIAN TOTAL", "Australia skill level 1", "Australia skill level 2"],
        "State": ["AUST", "AUST", "AUST"],
        "Skill_level": [0, 1, 2],
        pd.Timestamp("2024-01-01"): [300.0, 100.0, 80.0],
        pd.Timestamp("2024-02-01"): [310.0, 105.0, 82.0],
    }
    df = pd.DataFrame(data)
    with pd.ExcelWriter(path) as writer:
        df.to_excel(writer, sheet_name="Trend", index=False)
        df.to_excel(writer, sheet_name="Trend Index", index=False)


def test_parse_anzsco4(tmp_path):
    fp = tmp_path / "internet_vacancies_anzsco4_occupations_states_and_territories_-_test.xlsx"
    _write_anzsco4_excel(fp)
    records = parse_ivi_excel(fp)
    assert len(records) == 6  # 3 rows * 2 periods * 1 sheet
    assert records[0]["index_type"] == "three_month_average"
    assert all(r["file_type"] == "anzsco4_state" for r in records)
    assert all(r["geo_type"] == "state" for r in records)
    codes = {r["anzsco_code"] for r in records}
    assert "1111" in codes
    assert "1112" in codes


def test_parse_anzsco2(tmp_path):
    fp = tmp_path / "internet_vacancies_anzsco2_occupations_states_and_territories_-_test.xlsx"
    _write_anzsco2_excel(fp)
    records = parse_ivi_excel(fp)
    # 3 rows * 2 periods * 2 sheets
    assert len(records) == 12
    assert all(r["file_type"] == "anzsco2_state" for r in records)
    assert all(r["geo_type"] == "state" for r in records)
    types = {r["index_type"] for r in records}
    assert "trend" in types
    assert "seasonally_adjusted" in types


def test_parse_skill_level(tmp_path):
    fp = tmp_path / "internet_vacancies_anzsco_skill_level_states_and_territories_-_test.xlsx"
    _write_skill_level_excel(fp)
    records = parse_ivi_excel(fp)
    # 3 rows * 2 periods * 2 sheets
    assert len(records) == 12
    assert all(r["file_type"] == "skill_level_state" for r in records)
    assert all(r["geo_type"] == "state" for r in records)
    assert all(r["anzsco_code"] == "" for r in records)
    skills = {r["skill_level"] for r in records}
    assert "1" in skills
    assert "2" in skills


def test_parse_period_format(tmp_path):
    fp = tmp_path / "internet_vacancies_anzsco4_occupations_states_and_territories_-_test.xlsx"
    _write_anzsco4_excel(fp)
    records = parse_ivi_excel(fp)
    periods = {r["period"] for r in records}
    assert "Jan 2024" in periods
    assert "Feb 2024" in periods


def test_parse_values(tmp_path):
    fp = tmp_path / "internet_vacancies_anzsco4_occupations_states_and_territories_-_test.xlsx"
    _write_anzsco4_excel(fp)
    records = parse_ivi_excel(fp)
    vals = [r["value"] for r in records if r["anzsco_code"] == "1111"]
    assert 10.5 in vals
    assert 11.0 in vals


def test_parse_unrecognized_file(tmp_path):
    fp = tmp_path / "unknown_file.xlsx"
    pd.DataFrame({"x": [1]}).to_excel(fp, index=False)
    records = parse_ivi_excel(fp)
    assert records == []


def test_parse_missing_values(tmp_path):
    """Test that missing values (NaN, '.') are handled as None."""
    data = {
        "ANZSCO_CODE": ["1111", "1112"],
        "ANZSCO_TITLE": ["Job A", "Job B"],
        "state": ["AUST", "AUST"],
        pd.Timestamp("2024-01-01"): [10.0, float("nan")],
    }
    df = pd.DataFrame(data)
    fp = tmp_path / "internet_vacancies_anzsco4_occupations_states_and_territories_-_test2.xlsx"
    with pd.ExcelWriter(fp) as writer:
        df.to_excel(writer, sheet_name="4 digit 3 month average", index=False)

    records = parse_ivi_excel(fp)
    vals = {r["anzsco_code"]: r["value"] for r in records}
    assert vals["1111"] == 10.0
    assert vals["1112"] is None


def test_parse_dot_code_preserved(tmp_path):
    """Test that ANZSCO_CODE='.' occupations (e.g. Legislators) are preserved."""
    data = {
        "ANZSCO_CODE": ["0", "1111", "."],
        "ANZSCO_TITLE": ["Australia Total", "Chief Executives", "Legislators"],
        "state": ["AUST", "AUST", "AUST"],
        pd.Timestamp("2024-01-01"): [100.0, 10.5, 5.0],
    }
    df = pd.DataFrame(data)
    fp = tmp_path / "internet_vacancies_anzsco4_occupations_states_and_territories_-_dottest.xlsx"
    with pd.ExcelWriter(fp) as writer:
        df.to_excel(writer, sheet_name="4 digit 3 month average", index=False)

    records = parse_ivi_excel(fp)
    codes = {r["anzsco_code"] for r in records}
    assert "." in codes
    dot_rec = [r for r in records if r["anzsco_code"] == "."][0]
    assert dot_rec["anzsco_title"] == "Legislators"
    assert dot_rec["value"] == 5.0


# --- Geographic region variant tests ---


def _write_anzsco4_remoteness_excel(path: Path) -> None:
    """Write a synthetic ANZSCO4 remoteness Excel file.

    Cols: Level, ANZSCO_CODE, ANZSCO_TITLE, JSA Remoteness, <periods>
    Sheets: Notes, JSA Remoteness, JSA Northern Australia, Concordance
    """
    data = {
        "Level": [0, 1, 2],
        "ANZSCO_CODE": ["0", "1", "11"],
        "ANZSCO_TITLE": ["Total", "MANAGERS", "Chief Executives"],
        "JSA Remoteness": ["Regional", "Regional", "Major City"],
        pd.Timestamp("2024-01-01"): [100.0, 50.0, 10.0],
        pd.Timestamp("2024-02-01"): [105.0, 52.0, 11.0],
    }
    na_data = {
        "Level": [0],
        "ANZSCO_CODE": ["0"],
        "ANZSCO_TITLE": ["Total"],
        "Northern Australia": ["Northern Australia"],
        pd.Timestamp("2024-01-01"): [30.0],
        pd.Timestamp("2024-02-01"): [32.0],
    }
    conc = {"SA4 Code": [101], "SA4 Name": ["Capital Region"],
            "JSA Remoteness": ["Regional"], "Northern Australia (proxy)": ["No"]}
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"Notes": ["test"]}).to_excel(writer, sheet_name="Notes", index=False)
        pd.DataFrame(data).to_excel(writer, sheet_name="JSA Remoteness", index=False)
        pd.DataFrame(na_data).to_excel(writer, sheet_name="JSA Northern Australia", index=False)
        pd.DataFrame(conc).to_excel(writer, sheet_name="Concordance", index=False)


def _write_anzsco2_gccsa_excel(path: Path) -> None:
    """Write a synthetic ANZSCO2 GCCSA Excel file.

    Cols: Level, State, region_name, region_code, region_level, ANZSCO_CODE, ANZSCO_TITLE, <periods>
    Sheet: Averaged
    """
    data = {
        "Level": [1, 2],
        "State": ["NSW", "NSW"],
        "region_name": ["Greater Sydney", "Greater Sydney"],
        "region_code": ["1GSYD", "1GSYD"],
        "region_level": ["GCCSA", "GCCSA"],
        "ANZSCO_CODE": ["0", "1"],
        "ANZSCO_TITLE": ["Greater Sydney TOTAL", "MANAGERS"],
        pd.Timestamp("2024-01-01"): [500.0, 80.0],
        pd.Timestamp("2024-02-01"): [510.0, 82.0],
    }
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"Notes": ["test"]}).to_excel(writer, sheet_name="Notes", index=False)
        pd.DataFrame(data).to_excel(writer, sheet_name="Averaged", index=False)


def _write_anzsco2_region_excel(path: Path) -> None:
    """Write a synthetic ANZSCO2 IVI region Excel file.

    Cols: Level, State, region, ANZSCO_CODE, ANZSCO_TITLE, <periods>
    Sheets: Averaged, Indexed
    """
    data = {
        "Level": [1, 2],
        "State": ["NSW", "NSW"],
        "region": ["Blue Mountains", "Blue Mountains"],
        "ANZSCO_CODE": ["0", "1"],
        "ANZSCO_TITLE": ["Blue Mountains TOTAL", "MANAGERS"],
        pd.Timestamp("2024-01-01"): [200.0, 40.0],
        pd.Timestamp("2024-02-01"): [210.0, 42.0],
    }
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"Notes": ["test"]}).to_excel(writer, sheet_name="Notes", index=False)
        pd.DataFrame(data).to_excel(writer, sheet_name="Averaged", index=False)
        pd.DataFrame(data).to_excel(writer, sheet_name="Indexed", index=False)


def test_parse_anzsco4_remoteness(tmp_path):
    """Test ANZSCO4 remoteness: two data sheets, concordance skipped."""
    fp = tmp_path / "internet_vacancies_anzsco4_occupations_jsa_remoteness_and_northern_australia_classification_-_test.xlsx"
    _write_anzsco4_remoteness_excel(fp)
    records = parse_ivi_excel(fp)
    # JSA Remoteness: 3 rows * 2 periods = 6, JSA Northern Australia: 1 row * 2 periods = 2
    assert len(records) == 8
    assert all(r["file_type"] == "anzsco4_remoteness" for r in records)
    assert all(r["geo_type"] == "remoteness" for r in records)
    index_types = {r["index_type"] for r in records}
    assert "jsa_remoteness" in index_types
    assert "jsa_northern_australia" in index_types
    regions = {r["geo_area"] for r in records}
    assert "Regional" in regions
    assert "Northern Australia" in regions


def test_parse_anzsco2_gccsa(tmp_path):
    """Test ANZSCO2 GCCSA: single Averaged sheet."""
    fp = tmp_path / "internet_vacancies_anzsco2_occupations_gccsa_and_sa4_regions_-_test.xlsx"
    _write_anzsco2_gccsa_excel(fp)
    records = parse_ivi_excel(fp)
    # 2 rows * 2 periods * 1 sheet
    assert len(records) == 4
    assert all(r["file_type"] == "anzsco2_gccsa" for r in records)
    assert all(r["geo_type"] == "gccsa" for r in records)
    assert all(r["index_type"] == "averaged" for r in records)
    assert all(r["geo_area"] == "Greater Sydney" for r in records)
    codes = {r["anzsco_code"] for r in records}
    assert "0" in codes
    assert "1" in codes


def test_parse_anzsco2_region(tmp_path):
    """Test ANZSCO2 IVI regions: Averaged + Indexed sheets."""
    fp = tmp_path / "internet_vacancies_anzsco2_occupations_ivi_regions_-_test.xlsx"
    _write_anzsco2_region_excel(fp)
    records = parse_ivi_excel(fp)
    # 2 rows * 2 periods * 2 sheets
    assert len(records) == 8
    assert all(r["file_type"] == "anzsco2_region" for r in records)
    assert all(r["geo_type"] == "ivi_region" for r in records)
    index_types = {r["index_type"] for r in records}
    assert "averaged" in index_types
    assert "indexed" in index_types
    assert all(r["geo_area"] == "Blue Mountains" for r in records)


# --- Notes extraction tests ---


def test_extract_notes_text_only(tmp_path):
    """Notes sheet with prose text only."""
    fp = tmp_path / "internet_vacancies_anzsco4_occupations_states_and_territories_-_notes.xlsx"
    notes_df = pd.DataFrame({0: [
        "Data is seasonally adjusted.",
        "Source: Jobs and Skills Australia.",
    ]})
    data = {
        "ANZSCO_CODE": ["1111"],
        "ANZSCO_TITLE": ["Chief Executives"],
        "state": ["AUST"],
        pd.Timestamp("2024-01-01"): [10.0],
    }
    with pd.ExcelWriter(fp) as writer:
        notes_df.to_excel(writer, sheet_name="Notes", index=False, header=False)
        pd.DataFrame(data).to_excel(writer, sheet_name="4 digit 3 month average", index=False)

    result = extract_ivi_notes(fp)
    assert result is not None
    assert result["dataset"] == "ivi"
    assert result["file_type"] == "anzsco4_state"
    assert result["source_type"] == "excel_notes_sheet"
    assert "seasonally adjusted" in result["note_text"]
    assert result["note_tables"] == []
    assert len(result["content_hash"]) == 64


def test_extract_notes_with_table(tmp_path):
    """Notes sheet with prose + a multi-column table."""
    fp = tmp_path / "internet_vacancies_anzsco4_occupations_jsa_remoteness_and_northern_australia_classification_-_notes.xlsx"
    # Build a sheet: 2 prose rows, then a 4-row table (header + 3 data rows)
    rows = [
        ["This is a note about methodology.", None, None],
        ["Published monthly.", None, None],
        ["SA4 Name", "JSA Remoteness", "Northern Australia"],
        ["Capital Region", "Regional", "No"],
        ["Sydney", "Major City", "No"],
        ["Darwin", "Remote", "Yes"],
    ]
    notes_df = pd.DataFrame(rows)
    data = {
        "Level": [0],
        "ANZSCO_CODE": ["0"],
        "ANZSCO_TITLE": ["Total"],
        "JSA Remoteness": ["Regional"],
        pd.Timestamp("2024-01-01"): [100.0],
    }
    with pd.ExcelWriter(fp) as writer:
        notes_df.to_excel(writer, sheet_name="Notes", index=False, header=False)
        pd.DataFrame(data).to_excel(writer, sheet_name="JSA Remoteness", index=False)

    result = extract_ivi_notes(fp)
    assert result is not None
    assert "methodology" in result["note_text"]
    assert "Published monthly" in result["note_text"]
    assert len(result["note_tables"]) == 1
    tbl = result["note_tables"][0]
    assert tbl["headers"] == ["SA4 Name", "JSA Remoteness", "Northern Australia"]
    assert len(tbl["rows"]) == 3
    assert tbl["rows"][0][0] == "Capital Region"


def test_extract_notes_no_sheet(tmp_path):
    """Workbook without a Notes sheet returns None."""
    fp = tmp_path / "internet_vacancies_anzsco4_occupations_states_and_territories_-_nosheet.xlsx"
    data = {
        "ANZSCO_CODE": ["1111"],
        "ANZSCO_TITLE": ["Chief Executives"],
        "state": ["AUST"],
        pd.Timestamp("2024-01-01"): [10.0],
    }
    with pd.ExcelWriter(fp) as writer:
        pd.DataFrame(data).to_excel(writer, sheet_name="4 digit 3 month average", index=False)

    assert extract_ivi_notes(fp) is None


def test_extract_notes_empty_sheet(tmp_path):
    """Notes sheet with only NaN/blank cells returns None."""
    fp = tmp_path / "internet_vacancies_anzsco4_occupations_states_and_territories_-_empty.xlsx"
    empty_df = pd.DataFrame({0: [None, None, None]})
    data = {
        "ANZSCO_CODE": ["1111"],
        "ANZSCO_TITLE": ["Chief Executives"],
        "state": ["AUST"],
        pd.Timestamp("2024-01-01"): [10.0],
    }
    with pd.ExcelWriter(fp) as writer:
        empty_df.to_excel(writer, sheet_name="Notes", index=False, header=False)
        pd.DataFrame(data).to_excel(writer, sheet_name="4 digit 3 month average", index=False)

    assert extract_ivi_notes(fp) is None


def test_extract_notes_unrecognized_file(tmp_path):
    """Unrecognized filename returns None."""
    fp = tmp_path / "unknown_file.xlsx"
    pd.DataFrame({"Notes": ["test"]}).to_excel(fp, index=False)
    assert extract_ivi_notes(fp) is None


def test_extract_notes_content_hash(tmp_path):
    """Same content -> same hash; different content -> different hash."""
    fp1 = tmp_path / "internet_vacancies_anzsco4_occupations_states_and_territories_-_hash1.xlsx"
    fp2 = tmp_path / "internet_vacancies_anzsco2_occupations_states_and_territories_-_hash2.xlsx"
    notes1 = pd.DataFrame({0: ["Same note text."]})
    notes2 = pd.DataFrame({0: ["Different note text."]})
    data4 = {
        "ANZSCO_CODE": ["1111"], "ANZSCO_TITLE": ["A"], "state": ["X"],
        pd.Timestamp("2024-01-01"): [1.0],
    }
    data2 = {
        "Level": [1], "ANZSCO_CODE": ["1"], "Title": ["A"], "State": ["X"],
        pd.Timestamp("2024-01-01"): [1.0],
    }

    with pd.ExcelWriter(fp1) as writer:
        notes1.to_excel(writer, sheet_name="Notes", index=False, header=False)
        pd.DataFrame(data4).to_excel(writer, sheet_name="4 digit 3 month average", index=False)
    with pd.ExcelWriter(fp2) as writer:
        notes2.to_excel(writer, sheet_name="Notes", index=False, header=False)
        pd.DataFrame(data2).to_excel(writer, sheet_name="Trend", index=False)

    r1 = extract_ivi_notes(fp1)
    r2 = extract_ivi_notes(fp2)
    assert r1 is not None and r2 is not None
    assert r1["content_hash"] != r2["content_hash"]

    # Same content in a different file -> same hash
    fp3 = tmp_path / "internet_vacancies_anzsco2_occupations_ivi_regions_-_hash3.xlsx"
    with pd.ExcelWriter(fp3) as writer:
        notes1.to_excel(writer, sheet_name="Notes", index=False, header=False)
        pd.DataFrame({
            "Level": [1], "State": ["X"], "region": ["R"],
            "ANZSCO_CODE": ["1"], "ANZSCO_TITLE": ["A"],
            pd.Timestamp("2024-01-01"): [1.0],
        }).to_excel(writer, sheet_name="Averaged", index=False)
    r3 = extract_ivi_notes(fp3)
    assert r3 is not None
    assert r1["content_hash"] == r3["content_hash"]
