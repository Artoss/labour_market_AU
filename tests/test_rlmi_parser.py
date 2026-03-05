"""Tests for RLMI (Regional Labour Market Indicator) parser."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from labour_market_au.extraction.rlmi_parser import (
    _INDICATOR_MEASURES,
    _RATING_TEXT_TO_VALUE,
    _RATING_VALUE_TO_TEXT,
    extract_rlmi_notes,
    parse_rlmi_excel,
)


# --- Helpers to build synthetic Excel files ---

# Per-indicator reference periods for the snapshot sheet
_SNAPSHOT_INDICATOR_PERIODS = [
    datetime(2025, 12, 1),  # working_age_employment_rate
    datetime(2025, 12, 1),  # unemployment_rate
    datetime(2025, 12, 1),  # prop_jobseeker_income_support
    datetime(2025, 12, 1),  # prop_jobseeker_2plus_years
    datetime(2025, 11, 1),  # job_vacancy_rate
    datetime(2025, 2, 1),   # job_matching_efficiency_rate
    datetime(2025, 12, 1),  # underemployment_rate
    datetime(2025, 12, 1),  # vacancy_fill_rate
    datetime(2023, 6, 1),   # annual_median_income_growth_rate
    datetime(2021, 8, 1),   # skill_underutilisation_rate
]

_TIMESERIES_PERIODS = [
    datetime(2024, 3, 1),
    datetime(2024, 6, 1),
    datetime(2024, 9, 1),
    datetime(2024, 12, 1),
]


def _write_snapshot_sheet(writer: pd.ExcelWriter, *, include_aggregates: bool = True) -> None:
    """Write a synthetic snapshot sheet."""
    ncols = 14  # SA4 Code, Name, Rating, 10 indicators, 1 empty trailing col
    # Rows 0-5: empty/title
    rows = []
    for _ in range(6):
        rows.append([None] * ncols)
    # Row 6: headers
    headers = [
        "SA4 Code", "Statistical Area Level 4 (SA4)", "Rating",
        "Working Age Employment Rate (%)", "Unemployment Rate (%)",
        "Prop JobSeeker (%)", "Prop JobSeeker 2+ years (%)",
        "Job Vacancy Rate (%)", "Job Matching Efficiency Rate (%)",
        "Underemployment Rate (%)", "Vacancy Fill Rate (%)",
        "Annual Median Income Growth Rate (%)", "Skill Underutilisation Rate (%)",
        None,
    ]
    rows.append(headers)
    # Row 7: reference periods
    period_row = [None, None, None] + _SNAPSHOT_INDICATOR_PERIODS + [None]
    rows.append(period_row)
    # Row 8: annotations
    rows.append([None] * ncols)
    # Row 9+: data rows
    data_rows = [
        [102, "Central Coast", "Average", 76.9, 3.9, 6.6, 2.4, 2.9, 79.5, 5.1, 69.9, 8.7, 21.1, None],
        [115, "Sydney - Baulkham Hills", "Strong", 79.8, 3.3, 2.0, 0.5, 2.9, 89.7, 5.1, 69.9, 7.2, 25.3, None],
        [701, "Darwin", "Above average", 81.6, 3.2, 5.7, 1.9, 4.8, 63.9, 4.0, 72.2, 2.6, 27.1, None],
    ]
    rows.extend(data_rows)

    if include_aggregates:
        # Northern Australia (no SA4 code, with footnote marker)
        rows.append([None, "Northern Australia4", "Below average", 77.3, 4.3, 10.1, 3.6, 4.8, 63.0, 5.3, 59.0, 3.0, 21.7, None])
        # National Average (no rating)
        rows.append([None, "National Average1", None, 77.2, 3.9, 6.5, 2.3, 3.7, 74.0, 5.7, 68.7, 5.1, 24.5, None])
        # Footnote rows
        rows.append(["1 The 'National Average' represents...", None, None, None, None, None, None, None, None, None, None, None, None, None])
        rows.append(["4 Northern Australia comprises...", None, None, None, None, None, None, None, None, None, None, None, None, None])

    df = pd.DataFrame(rows)
    df.to_excel(writer, sheet_name="December 2025", index=False, header=False)


def _write_timeseries_sheet(writer: pd.ExcelWriter) -> None:
    """Write a synthetic Historical Timeseries sheet."""
    ncols = 2 + len(_TIMESERIES_PERIODS)
    rows = []
    # Rows 0-5: empty/title
    for _ in range(6):
        rows.append([None] * ncols)
    # Row 6: headers
    rows.append(["SA4 Code", "Statistical Area Level 4 (SA4)"] + _TIMESERIES_PERIODS)
    # Row 7+: data
    data_rows = [
        [102, "Central Coast", 3, 3, 3, 3],
        [115, "Sydney - Baulkham Hills", 1, 1, 1, 1],
        [701, "Darwin", 2, 2, 2, 2],
        [None, "Northern Australia1", 4, 4, 4, 4],
    ]
    rows.extend(data_rows)
    # Footnote
    rows.append(["1 Northern Australia comprises...", None, None, None, None, None])

    df = pd.DataFrame(rows)
    df.to_excel(writer, sheet_name="Historical Timeseries", index=False, header=False)


def _write_contents_sheet(writer: pd.ExcelWriter) -> None:
    """Write a synthetic Contents sheet with prose."""
    rows = [
        [None, None, None, None],
        [None, None, None, None],
        [None, None, None, None],
        [None, None, None, None],
        ["Regional Labour Market Indicator (RLMI)", None, None, None],
        [None, None, None, None],
        [None, None, None, None],
        [None, "Contents", None, None],
        [None, None, None, None],
        [None, "Table_1", "Labour Market Rating by SA4", None],
        [None, "Table_2", "Historical Timeseries", None],
        [None, None, None, None],
        [None, None, "The RLMI provides an overview of local labour market conditions.", None],
    ]
    df = pd.DataFrame(rows)
    df.to_excel(writer, sheet_name="Contents", index=False, header=False)


def _write_full_workbook(path: Path, *, include_aggregates: bool = True) -> None:
    """Write a synthetic RLMI workbook with all 3 sheets."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_contents_sheet(writer)
        _write_snapshot_sheet(writer, include_aggregates=include_aggregates)
        _write_timeseries_sheet(writer)


# --- Snapshot sheet tests ---


def test_snapshot_record_count(tmp_path):
    """3 SA4 rows -> 3 ratings + 30 indicators = 33 records."""
    path = tmp_path / "rlmi.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_snapshot_sheet(writer, include_aggregates=False)

    records = parse_rlmi_excel(path)
    # 3 rows x (1 rating + 10 indicators) = 33
    assert len(records) == 33
    assert all(r["data_source"] == "snapshot" for r in records)


def test_snapshot_rating_extraction(tmp_path):
    path = tmp_path / "rlmi.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_snapshot_sheet(writer, include_aggregates=False)

    records = parse_rlmi_excel(path)
    ratings = [r for r in records if r["measure"] == "overall_rating"]
    assert len(ratings) == 3

    strong = [r for r in ratings if r["rating_text"] == "Strong"]
    assert len(strong) == 1
    assert strong[0]["rating_value"] == 1
    assert strong[0]["sa4_code"] == "115"
    assert strong[0]["value"] is None


def test_snapshot_indicator_values(tmp_path):
    path = tmp_path / "rlmi.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_snapshot_sheet(writer, include_aggregates=False)

    records = parse_rlmi_excel(path)
    # Central Coast unemployment_rate
    unemp = [r for r in records if r["sa4_code"] == "102" and r["measure"] == "unemployment_rate"]
    assert len(unemp) == 1
    assert unemp[0]["value"] == pytest.approx(3.9)
    assert unemp[0]["rating_value"] is None
    assert unemp[0]["rating_text"] == ""


def test_snapshot_per_indicator_periods(tmp_path):
    path = tmp_path / "rlmi.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_snapshot_sheet(writer, include_aggregates=False)

    records = parse_rlmi_excel(path)
    # job_vacancy_rate should have Nov 2025 period
    jvr = [r for r in records if r["measure"] == "job_vacancy_rate"]
    assert all(r["period"] == "Nov 2025" for r in jvr)

    # annual_median_income_growth_rate should have Jun 2023
    income = [r for r in records if r["measure"] == "annual_median_income_growth_rate"]
    assert all(r["period"] == "Jun 2023" for r in income)


def test_snapshot_aggregates(tmp_path):
    path = tmp_path / "rlmi.xlsx"
    _write_full_workbook(path, include_aggregates=True)

    records = parse_rlmi_excel(path)
    snap = [r for r in records if r["data_source"] == "snapshot"]
    aggregates = [r for r in snap if r["geo_type"] == "aggregate"]
    assert len(aggregates) > 0

    # Northern Australia should have rating
    nth_aus = [r for r in aggregates if "Northern Australia" in r["sa4_name"] and r["measure"] == "overall_rating"]
    assert len(nth_aus) == 1
    assert nth_aus[0]["rating_text"] == "Below average"
    assert nth_aus[0]["sa4_code"] == ""

    # National Average has no rating (None in col 2)
    nat_avg = [r for r in aggregates if "National Average" in r["sa4_name"]]
    nat_ratings = [r for r in nat_avg if r["measure"] == "overall_rating"]
    assert len(nat_ratings) == 0  # no rating for National Average


def test_snapshot_sa4_code_formatting(tmp_path):
    path = tmp_path / "rlmi.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_snapshot_sheet(writer, include_aggregates=False)

    records = parse_rlmi_excel(path)
    codes = {r["sa4_code"] for r in records if r["sa4_code"]}
    assert all(isinstance(c, str) for c in codes)
    assert "102" in codes
    assert "701" in codes


def test_snapshot_footnote_skipping(tmp_path):
    """Footnote rows should not produce records."""
    path = tmp_path / "rlmi.xlsx"
    _write_full_workbook(path, include_aggregates=True)

    records = parse_rlmi_excel(path)
    snap = [r for r in records if r["data_source"] == "snapshot"]
    # No record should have footnote text as sa4_name
    for r in snap:
        assert "represents" not in r["sa4_name"].lower()
        assert "comprises" not in r["sa4_name"].lower()


def test_snapshot_missing_values(tmp_path):
    """Missing indicator values should be None."""
    ncols = 14
    rows = []
    for _ in range(6):
        rows.append([None] * ncols)
    headers = ["SA4 Code", "SA4 Name", "Rating"] + [f"Ind{i}" for i in range(10)] + [None]
    rows.append(headers)
    # Row 7: periods
    rows.append([None, None, None] + [datetime(2025, 12, 1)] * 10 + [None])
    rows.append([None] * ncols)
    # Data row with None indicator
    rows.append([999, "Test SA4", "Average", None, 3.5, None, None, None, None, None, None, None, None, None])

    path = tmp_path / "rlmi.xlsx"
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="March 2026", index=False, header=False)

    records = parse_rlmi_excel(path)
    indicators = [r for r in records if r["measure"] != "overall_rating"]
    none_vals = [r for r in indicators if r["value"] is None]
    assert len(none_vals) >= 1


# --- Timeseries sheet tests ---


def test_timeseries_record_count(tmp_path):
    """4 rows x 4 periods = 16 records."""
    path = tmp_path / "rlmi.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_timeseries_sheet(writer)

    records = parse_rlmi_excel(path)
    assert len(records) == 16
    assert all(r["data_source"] == "timeseries" for r in records)
    assert all(r["measure"] == "overall_rating" for r in records)


def test_timeseries_rating_values_mapped(tmp_path):
    path = tmp_path / "rlmi.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_timeseries_sheet(writer)

    records = parse_rlmi_excel(path)
    # Darwin = rating 2 = "Above average"
    darwin = [r for r in records if r["sa4_code"] == "701"]
    assert all(r["rating_value"] == 2 for r in darwin)
    assert all(r["rating_text"] == "Above average" for r in darwin)
    assert all(r["value"] is None for r in darwin)


def test_timeseries_period_format(tmp_path):
    path = tmp_path / "rlmi.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_timeseries_sheet(writer)

    records = parse_rlmi_excel(path)
    periods = {r["period"] for r in records}
    assert periods == {"Mar 2024", "Jun 2024", "Sep 2024", "Dec 2024"}


def test_timeseries_aggregate_handling(tmp_path):
    path = tmp_path / "rlmi.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_timeseries_sheet(writer)

    records = parse_rlmi_excel(path)
    aggs = [r for r in records if r["geo_type"] == "aggregate"]
    assert len(aggs) == 4  # Northern Australia x 4 periods
    assert all(r["sa4_code"] == "" for r in aggs)
    assert all("Northern Australia" in r["sa4_name"] for r in aggs)


# --- Full workbook tests ---


def test_full_workbook_combined(tmp_path):
    path = tmp_path / "rlmi.xlsx"
    _write_full_workbook(path)

    records = parse_rlmi_excel(path)
    sources = {r["data_source"] for r in records}
    assert sources == {"snapshot", "timeseries"}

    snap = [r for r in records if r["data_source"] == "snapshot"]
    ts = [r for r in records if r["data_source"] == "timeseries"]
    assert len(snap) > 0
    assert len(ts) > 0


def test_full_workbook_all_measures(tmp_path):
    path = tmp_path / "rlmi.xlsx"
    _write_full_workbook(path)

    records = parse_rlmi_excel(path)
    snap = [r for r in records if r["data_source"] == "snapshot"]
    measures = {r["measure"] for r in snap}
    expected = {"overall_rating"} | set(_INDICATOR_MEASURES)
    assert measures == expected


# --- Notes extraction tests ---


def test_extract_notes(tmp_path):
    path = tmp_path / "rlmi.xlsx"
    _write_full_workbook(path)

    note = extract_rlmi_notes(path)
    assert note is not None
    assert note["dataset"] == "rlmi"
    assert note["source_type"] == "excel_contents_sheet"
    assert "RLMI" in note["note_text"] or "labour market" in note["note_text"].lower()


def test_extract_notes_content_hash(tmp_path):
    path1 = tmp_path / "rlmi1.xlsx"
    path2 = tmp_path / "rlmi2.xlsx"
    _write_full_workbook(path1)
    _write_full_workbook(path2)

    note1 = extract_rlmi_notes(path1)
    note2 = extract_rlmi_notes(path2)
    assert note1 is not None and note2 is not None
    assert note1["content_hash"] == note2["content_hash"]


def test_extract_notes_no_contents_sheet(tmp_path):
    path = tmp_path / "rlmi.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_snapshot_sheet(writer, include_aggregates=False)

    note = extract_rlmi_notes(path)
    assert note is None
