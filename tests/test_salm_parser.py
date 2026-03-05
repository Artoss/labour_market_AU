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


# New format (2025+) sheet names
def test_classify_sheet_new_sa2_rate():
    assert _classify_sheet("Smoothed SA2 unemployment rate") == ("unemployment_rate", "sa2")


def test_classify_sheet_new_sa2_unemployed():
    assert _classify_sheet("Smoothed SA2 unemployment") == ("unemployed_persons", "sa2")


def test_classify_sheet_new_sa2_force():
    assert _classify_sheet("Smoothed SA2 labour force") == ("labour_force", "sa2")


def test_classify_sheet_new_lga_rates():
    assert _classify_sheet("Smoothed LGA unemployment rates") == ("unemployment_rate", "lga")


def test_classify_sheet_new_lga_unemployed():
    assert _classify_sheet("Smoothed LGA unemployment") == ("unemployed_persons", "lga")


def test_classify_sheet_new_lga_force():
    assert _classify_sheet("Smoothed LGA labour force") == ("labour_force", "lga")


# Unsmoothed sheet names
def test_classify_sheet_unsmoothed_sa2_rate():
    assert _classify_sheet("Unsmoothed SA2 unemployment rate") == ("unemployment_rate", "sa2")


def test_classify_sheet_unsmoothed_sa2_unemployed():
    assert _classify_sheet("Unsmoothed SA2 unemployment") == ("unemployed_persons", "sa2")


def test_classify_sheet_unsmoothed_sa2_force():
    assert _classify_sheet("Unsmoothed SA2 labour force") == ("labour_force", "sa2")


def test_classify_sheet_unsmoothed_lga_rate():
    assert _classify_sheet("Unsmoothed LGA unemployment rates") == ("unemployment_rate", "lga")


def test_classify_sheet_unsmoothed_lga_unemployed():
    assert _classify_sheet("Unsmoothed LGA unemployment") == ("unemployed_persons", "lga")


def test_classify_sheet_unsmoothed_lga_force():
    assert _classify_sheet("Unsmoothed LGA labour force") == ("labour_force", "lga")
