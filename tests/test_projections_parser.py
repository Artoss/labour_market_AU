"""Tests for Employment Projections parser."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from labour_market_au.extraction.projections_parser import (
    _extract_years,
    _match_spec,
    parse_projections_excel,
)


# --- Helpers to build synthetic Excel files ---

# Main header row for tables with shares (Tables 1-4) -- new format
_MAIN_HEADER_WITH_SHARE = [
    "Baseline", "Projected", "Projected",
    "Share of Total Employment", "Share of Total Employment", "Share of Total Employment",
    "5-Year Change", "5-Year Change",
    "10-Year Change", "10-Year Change",
]

# Main header row for tables without shares (Tables 5-6) -- new format
_MAIN_HEADER_NO_SHARE = [
    "Baseline", "Projected", "Projected",
    "5-Year Change", "5-Year Change",
    "10-Year Change", "10-Year Change",
]

# Sub-header row for tables with shares (Tables 1-4)
# Columns after ID cols: 3 levels + 3 shares + 2 change(5yr) + 2 change(10yr) = 10
_SUBHEADER_WITH_SHARE = [
    "May 2025('000)", "Projected May 2030('000)", "Projected May 2035('000)",
    "Share May 2025", "Share May 2030", "Share May 2035",
    "5yr Level('000)", "5yr %",
    "10yr Level('000)", "10yr %",
]

# Sub-header row for tables without shares (Tables 5-6)
_SUBHEADER_NO_SHARE = [
    "May 2025('000)", "Projected May 2030('000)", "Projected May 2035('000)",
    "5yr Level('000)", "5yr %",
    "10yr Level('000)", "10yr %",
]


def _make_main_header_row(num_id_cols: int, has_share: bool) -> list:
    """Build the main header row (row 0 after skiprows=7 in new format)."""
    id_blanks = [""] * num_id_cols
    measures = _MAIN_HEADER_WITH_SHARE if has_share else _MAIN_HEADER_NO_SHARE
    return id_blanks + measures


def _make_header_row(num_id_cols: int, has_share: bool) -> list:
    """Build the sub-header row with years."""
    id_blanks = [""] * num_id_cols
    measures = _SUBHEADER_WITH_SHARE if has_share else _SUBHEADER_NO_SHARE
    return id_blanks + measures


def _pad_metadata(rows: list[list], num_cols: int) -> list[list]:
    """Prepend 7 blank metadata rows to match the real file format.

    The parser uses skiprows=7, so test data needs 7 leading rows.
    """
    blank = [""] * num_cols
    return [blank] * 7 + rows


def _write_table1_industry_division(path: Path) -> None:
    """Write a synthetic Table_1 Industry Division sheet."""
    main = _make_main_header_row(3, has_share=True)
    sub = _make_header_row(3, has_share=True)
    rows = [
        main,
        sub,
        [1, "A", "Agriculture", 100, 110, 120, 5.0, 5.5, 6.0, 10, 10.0, 20, 20.0],
        [1, "B", "Mining", 200, 220, 240, 10.0, 11.0, 12.0, 20, 10.0, 40, 20.0],
        [1, "", "Total", 300, 330, 360, 15.0, 16.5, 18.0, 30, 10.0, 60, 20.0],
    ]
    rows = _pad_metadata(rows, len(rows[0]))
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Table_1 Industry Division", index=False, header=False)


def _write_table2_major_occupation(path: Path) -> None:
    """Write a synthetic Table_2 Major Occupation sheet."""
    main = _make_main_header_row(3, has_share=True)
    sub = _make_header_row(3, has_share=True)
    rows = [
        main,
        sub,
        [1, "1", "Managers", 50, 55, 60, 2.5, 2.75, 3.0, 5, 10.0, 10, 20.0],
        [1, "2", "Professionals", 80, 88, 96, 4.0, 4.4, 4.8, 8, 10.0, 16, 20.0],
    ]
    rows = _pad_metadata(rows, len(rows[0]))
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Table_2 Major Occupation", index=False, header=False)


def _write_table3_skill_level(path: Path) -> None:
    """Write a synthetic Table_3 Skill Level sheet."""
    main = _make_main_header_row(1, has_share=True)
    sub = _make_header_row(1, has_share=True)
    rows = [
        main,
        sub,
        ["Skill Level 1", 400, 440, 480, 20.0, 22.0, 24.0, 40, 10.0, 80, 20.0],
        ["Skill Level 2", 300, 330, 360, 15.0, 16.5, 18.0, 30, 10.0, 60, 20.0],
        ["Total", 700, 770, 840, 35.0, 38.5, 42.0, 70, 10.0, 140, 20.0],
    ]
    rows = _pad_metadata(rows, len(rows[0]))
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Table_3 Skill Level", index=False, header=False)


def _write_table4_state(path: Path) -> None:
    """Write a synthetic Table_4 State & Territory sheet."""
    main = _make_main_header_row(1, has_share=True)
    sub = _make_header_row(1, has_share=True)
    rows = [
        main,
        sub,
        ["NSW", 500, 550, 600, 25.0, 27.5, 30.0, 50, 10.0, 100, 20.0],
        ["VIC", 400, 440, 480, 20.0, 22.0, 24.0, 40, 10.0, 80, 20.0],
        ["Australia", 900, 990, 1080, 45.0, 49.5, 54.0, 90, 10.0, 180, 20.0],
    ]
    rows = _pad_metadata(rows, len(rows[0]))
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Table_4 State & Territory", index=False, header=False)


def _write_table5_industry_group(path: Path) -> None:
    """Write a synthetic Table_5 Industry Group sheet."""
    main = _make_main_header_row(4, has_share=False)
    sub = _make_header_row(4, has_share=False)
    rows = [
        main,
        sub,
        [3, 0, "011", "Nursery and Floriculture", 10, 11, 12, 1, 10.0, 2, 20.0],
        [3, 0, "012", "Mushroom and Vegetable", 20, 22, 24, 2, 10.0, 4, 20.0],
    ]
    rows = _pad_metadata(rows, len(rows[0]))
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Table_5 Industry Group", index=False, header=False)


def _write_table6_occupation_unit(path: Path) -> None:
    """Write a synthetic Table_6 Occupation Unit Group sheet."""
    main = _make_main_header_row(5, has_share=False)
    sub = _make_header_row(5, has_share=False)
    rows = [
        main,
        sub,
        [4, 0, "1111", "Chief Executives", 1, 5, 5.5, 6, 0.5, 10.0, 1, 20.0],
        [4, 0, "1112", "General Managers", 1, 8, 8.8, 9.6, 0.8, 10.0, 1.6, 20.0],
    ]
    rows = _pad_metadata(rows, len(rows[0]))
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Table_6 Occupation Unit", index=False, header=False)


def _write_full_workbook(path: Path) -> None:
    """Write a synthetic workbook with all 6 tables (new two-row header format)."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        # Table 1
        main1 = _make_main_header_row(3, has_share=True)
        sub1 = _make_header_row(3, has_share=True)
        rows1 = _pad_metadata([
            main1,
            sub1,
            [1, "A", "Agriculture", 100, 110, 120, 5.0, 5.5, 6.0, 10, 10.0, 20, 20.0],
            [1, "B", "Mining", 200, 220, 240, 10.0, 11.0, 12.0, 20, 10.0, 40, 20.0],
        ], 13)
        pd.DataFrame(rows1).to_excel(
            writer, sheet_name="Table_1 Industry Division", index=False, header=False,
        )

        # Table 2
        main2 = _make_main_header_row(3, has_share=True)
        sub2 = _make_header_row(3, has_share=True)
        rows2 = _pad_metadata([
            main2,
            sub2,
            [1, "1", "Managers", 50, 55, 60, 2.5, 2.75, 3.0, 5, 10.0, 10, 20.0],
        ], 13)
        pd.DataFrame(rows2).to_excel(
            writer, sheet_name="Table_2 Major Occupation", index=False, header=False,
        )

        # Table 3
        main3 = _make_main_header_row(1, has_share=True)
        sub3 = _make_header_row(1, has_share=True)
        rows3 = _pad_metadata([
            main3,
            sub3,
            ["Skill Level 1", 400, 440, 480, 20.0, 22.0, 24.0, 40, 10.0, 80, 20.0],
        ], 11)
        pd.DataFrame(rows3).to_excel(
            writer, sheet_name="Table_3 Skill Level", index=False, header=False,
        )

        # Table 4
        main4 = _make_main_header_row(1, has_share=True)
        sub4 = _make_header_row(1, has_share=True)
        rows4 = _pad_metadata([
            main4,
            sub4,
            ["NSW", 500, 550, 600, 25.0, 27.5, 30.0, 50, 10.0, 100, 20.0],
        ], 11)
        pd.DataFrame(rows4).to_excel(
            writer, sheet_name="Table_4 State & Territory", index=False, header=False,
        )

        # Table 5
        main5 = _make_main_header_row(4, has_share=False)
        sub5 = _make_header_row(4, has_share=False)
        rows5 = _pad_metadata([
            main5,
            sub5,
            [3, 0, "011", "Nursery and Floriculture", 10, 11, 12, 1, 10.0, 2, 20.0],
        ], 11)
        pd.DataFrame(rows5).to_excel(
            writer, sheet_name="Table_5 Industry Group", index=False, header=False,
        )

        # Table 6
        main6 = _make_main_header_row(5, has_share=False)
        sub6 = _make_header_row(5, has_share=False)
        rows6 = _pad_metadata([
            main6,
            sub6,
            [4, 0, "1111", "Chief Executives", 1, 5, 5.5, 6, 0.5, 10.0, 1, 20.0],
        ], 12)
        pd.DataFrame(rows6).to_excel(
            writer, sheet_name="Table_6 Occupation Unit", index=False, header=False,
        )

        # Extra sheets that should be skipped (new format adds these)
        pd.DataFrame([["This is a notes sheet."]]).to_excel(
            writer, sheet_name="Notes", index=False, header=False,
        )
        pd.DataFrame([["Contents page"]]).to_excel(
            writer, sheet_name="Contents", index=False, header=False,
        )
        pd.DataFrame([["Data dictionary"]]).to_excel(
            writer, sheet_name="Data_Dictionary", index=False, header=False,
        )


# --- Spec matching tests ---


def test_match_spec_table1():
    spec = _match_spec("Table_1 Industry Division")
    assert spec is not None
    assert spec.dimension_type == "industry_division"


def test_match_spec_table6():
    spec = _match_spec("Table_6 Occupation Unit Group")
    assert spec is not None
    assert spec.dimension_type == "occupation_unit_group"


def test_match_spec_notes():
    assert _match_spec("Notes") is None


def test_match_spec_unknown():
    assert _match_spec("Random Sheet") is None


# --- Year extraction tests ---


def test_extract_years():
    header = pd.Series(["", "", "", "May 2025('000)", "Projected May 2030('000)", "Projected May 2035('000)"])
    years = _extract_years(header, 3)
    assert years == [2025, 2030, 2035]


def test_extract_years_empty():
    header = pd.Series(["", "", "", "", ""])
    years = _extract_years(header, 3)
    assert years == []


# --- Table 1: Industry Division ---


def test_parse_industry_division(tmp_path):
    path = tmp_path / "projections.xlsx"
    _write_table1_industry_division(path)
    records = parse_projections_excel(path)

    assert len(records) > 0
    # 2 data rows x 10 measures = 20 records
    assert len(records) == 20

    # Check dimension_type
    assert all(r["dimension_type"] == "industry_division" for r in records)

    # Check industry codes
    codes = {r["industry_code"] for r in records}
    assert codes == {"A", "B"}

    # Check a specific record
    agri_levels = [r for r in records if r["industry_code"] == "A" and r["measure"] == "employment_level"]
    assert len(agri_levels) == 3  # base, mid, end
    years = {r["projection_year"] for r in agri_levels}
    assert years == {2025, 2030, 2035}


# --- Table 2: Major Occupation ---


def test_parse_major_occupation(tmp_path):
    path = tmp_path / "projections.xlsx"
    _write_table2_major_occupation(path)
    records = parse_projections_excel(path)

    # 2 rows x 10 measures = 20
    assert len(records) == 20
    assert all(r["dimension_type"] == "major_occupation" for r in records)
    codes = {r["anzsco_code"] for r in records}
    assert codes == {"1", "2"}


# --- Table 3: Skill Level ---


def test_parse_skill_level(tmp_path):
    path = tmp_path / "projections.xlsx"
    _write_table3_skill_level(path)
    records = parse_projections_excel(path)

    # 2 data rows (Total excluded) x 10 measures = 20
    assert len(records) == 20
    assert all(r["dimension_type"] == "skill_level" for r in records)

    # Verify skill level number extraction
    codes = {r["anzsco_code"] for r in records}
    assert codes == {"1", "2"}

    # Verify occupation_name is set
    names = {r["occupation_name"] for r in records}
    assert "Skill Level 1" in names
    assert "Skill Level 2" in names


# --- Table 4: State & Territory ---


def test_parse_state_territory(tmp_path):
    path = tmp_path / "projections.xlsx"
    _write_table4_state(path)
    records = parse_projections_excel(path)

    # 2 data rows (Australia excluded) x 10 measures = 20
    assert len(records) == 20
    assert all(r["dimension_type"] == "state_territory" for r in records)

    states = {r["geo_area"] for r in records}
    assert states == {"NSW", "VIC"}
    assert all(r["geo_type"] == "state" for r in records)


# --- Table 5: Industry Group ---


def test_parse_industry_group(tmp_path):
    path = tmp_path / "projections.xlsx"
    _write_table5_industry_group(path)
    records = parse_projections_excel(path)

    # 2 rows x 7 measures = 14
    assert len(records) == 14
    assert all(r["dimension_type"] == "industry_group" for r in records)

    # Numeric codes lose leading zeros in synthetic Excel (real file stores as text)
    codes = {r["industry_code"] for r in records}
    assert codes == {"11", "12"}

    # No shares
    measures = {r["measure"] for r in records}
    assert "employment_share" not in measures


# --- Table 6: Occupation Unit Group ---


def test_parse_occupation_unit_group(tmp_path):
    path = tmp_path / "projections.xlsx"
    _write_table6_occupation_unit(path)
    records = parse_projections_excel(path)

    # 2 rows x 7 measures = 14
    assert len(records) == 14
    assert all(r["dimension_type"] == "occupation_unit_group" for r in records)

    codes = {r["anzsco_code"] for r in records}
    assert codes == {"1111", "1112"}


# --- Total row skipping ---


def test_parse_skips_total_rows(tmp_path):
    path = tmp_path / "projections.xlsx"
    _write_table1_industry_division(path)
    records = parse_projections_excel(path)

    # "Total" row should be excluded, only A and B remain
    names = {r["industry_name"] for r in records}
    assert "Total" not in names
    assert "Agriculture" in names
    assert "Mining" in names


def test_parse_skips_australia_total(tmp_path):
    path = tmp_path / "projections.xlsx"
    _write_table4_state(path)
    records = parse_projections_excel(path)

    states = {r["geo_area"] for r in records}
    assert "Australia" not in states


# --- Full workbook ---


def test_parse_full_workbook(tmp_path):
    path = tmp_path / "projections.xlsx"
    _write_full_workbook(path)
    records = parse_projections_excel(path)

    # Table 1: 2 rows x 10 = 20
    # Table 2: 1 row x 10 = 10
    # Table 3: 1 row x 10 = 10
    # Table 4: 1 row x 10 = 10
    # Table 5: 1 row x 7 = 7
    # Table 6: 1 row x 7 = 7
    # Total: 64
    assert len(records) == 64

    # Check all dimension types present
    dim_types = {r["dimension_type"] for r in records}
    assert dim_types == {
        "industry_division",
        "major_occupation",
        "skill_level",
        "state_territory",
        "industry_group",
        "occupation_unit_group",
    }


# --- Missing values ---


def test_parse_missing_values(tmp_path):
    """Verify NaN values become None in output."""
    main = _make_main_header_row(3, has_share=True)
    sub = _make_header_row(3, has_share=True)
    rows = _pad_metadata([
        main,
        sub,
        [1, "A", "Agriculture", 100, None, 120, 5.0, None, 6.0, 10, None, 20, None],
    ], 13)
    df = pd.DataFrame(rows)
    path = tmp_path / "projections.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Table_1 Industry", index=False, header=False)

    records = parse_projections_excel(path)
    assert len(records) == 10

    # Check that None values exist for the NaN inputs
    none_records = [r for r in records if r["value"] is None]
    assert len(none_records) >= 3  # At least 3 None values from our input


# --- Measure types ---


def test_measure_types_with_share(tmp_path):
    """Verify all expected measure types for tables with shares."""
    path = tmp_path / "projections.xlsx"
    _write_table1_industry_division(path)
    records = parse_projections_excel(path)

    measures = {r["measure"] for r in records}
    expected = {
        "employment_level", "employment_share",
        "growth_level_5yr", "growth_rate_5yr",
        "growth_level_10yr", "growth_rate_10yr",
    }
    assert measures == expected


def test_measure_types_without_share(tmp_path):
    """Verify measure types for tables without shares."""
    path = tmp_path / "projections.xlsx"
    _write_table5_industry_group(path)
    records = parse_projections_excel(path)

    measures = {r["measure"] for r in records}
    expected = {
        "employment_level",
        "growth_level_5yr", "growth_rate_5yr",
        "growth_level_10yr", "growth_rate_10yr",
    }
    assert measures == expected


# --- Backward compatibility: old single-header format ---


def _write_table1_old_format(path: Path) -> None:
    """Write Table_1 with the OLD single sub-header format (no main header row)."""
    sub = _make_header_row(3, has_share=True)
    rows = [
        sub,  # sub-header directly as row 0 (old format)
        [1, "A", "Agriculture", 100, 110, 120, 5.0, 5.5, 6.0, 10, 10.0, 20, 20.0],
        [1, "B", "Mining", 200, 220, 240, 10.0, 11.0, 12.0, 20, 10.0, 40, 20.0],
    ]
    rows = _pad_metadata(rows, len(rows[0]))
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Table_1 Industry Division", index=False, header=False)


def test_backward_compat_old_single_header(tmp_path):
    """Parser still works with old format where row 0 is the sub-header with years."""
    path = tmp_path / "projections_old.xlsx"
    _write_table1_old_format(path)
    records = parse_projections_excel(path)

    # 2 data rows x 10 measures = 20 records
    assert len(records) == 20
    assert all(r["dimension_type"] == "industry_division" for r in records)
    codes = {r["industry_code"] for r in records}
    assert codes == {"A", "B"}
