"""Tests for IVI parser stub."""

from __future__ import annotations

from pathlib import Path

from labour_market_au.extraction.ivi_parser import parse_ivi_excel


def test_parse_ivi_returns_empty_list(tmp_path):
    """Stub parser should return an empty list for any input."""
    dummy = tmp_path / "dummy.xlsx"
    dummy.touch()
    result = parse_ivi_excel(dummy)
    assert result == []
