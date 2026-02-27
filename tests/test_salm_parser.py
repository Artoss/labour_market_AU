"""Tests for SALM parser."""

from __future__ import annotations

import pandas as pd
import pytest

from labour_market_au.extraction.salm_parser import _classify_sheet


def test_classify_sheet_sa2_rate():
    result = _classify_sheet("Smoothed unemployment rate (SA2)")
    assert result == ("unemployment_rate", "sa2")


def test_classify_sheet_lga_persons():
    result = _classify_sheet("Smoothed unemployed persons (LGA)")
    assert result == ("unemployed_persons", "lga")


def test_classify_sheet_sa2_force():
    result = _classify_sheet("Smoothed labour force (SA2)")
    assert result == ("labour_force", "sa2")


def test_classify_sheet_unknown():
    result = _classify_sheet("Notes")
    assert result is None


def test_classify_sheet_case_insensitive():
    result = _classify_sheet("SMOOTHED UNEMPLOYMENT RATE (SA2)")
    assert result == ("unemployment_rate", "sa2")
