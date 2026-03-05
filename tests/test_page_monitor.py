"""Tests for page monitor."""

from __future__ import annotations

from labour_market_au.scraping.catalog import DataSource
from labour_market_au.scraping.page_monitor import (
    PageCheckResult,
    check_page,
    diff_page_check,
)


SAMPLE_HTML = """
<html>
<body>
<div class="field--type-text-long">
    <strong>Released: 10:30am Thursday, 19 December 2024</strong>
    <h2>September quarter 2024</h2>
    <p>Data available for download:</p>
    <a href="/sites/default/files/salm-smoothed-sa2-datafile.xlsx">SA2 data</a>
    <a href="https://example.com/other-file.xlsx">Other file</a>
    <a href="/documents/report.pdf">PDF report</a>
</div>
</body>
</html>
"""


def _make_source(**kwargs) -> DataSource:
    defaults = {
        "site": "jsa",
        "dataset": "salm",
        "page_url": "https://www.jobsandskills.gov.au/data/small-area-labour-markets",
        "update_frequency": "quarterly",
        "content_selector": "div.field--type-text-long",
        "date_selector": "div.field--type-text-long strong",
    }
    defaults.update(kwargs)
    return DataSource(**defaults)


def test_check_page_detects_change():
    source = _make_source()
    result = check_page(SAMPLE_HTML, source, known_hash=None)
    assert result.changed is True
    assert len(result.content_hash) == 64  # SHA256 hex


def test_check_page_no_change():
    source = _make_source()
    # First check to get the hash
    first = check_page(SAMPLE_HTML, source, known_hash=None)
    # Second check with same hash
    second = check_page(SAMPLE_HTML, source, known_hash=first.content_hash)
    assert second.changed is False


def test_check_page_extracts_links():
    source = _make_source()
    result = check_page(SAMPLE_HTML, source, known_hash=None)
    assert len(result.download_links) == 2  # .xlsx files only
    assert any("sa2-datafile.xlsx" in link for link in result.download_links)


def test_check_page_extracts_release_date():
    source = _make_source()
    result = check_page(SAMPLE_HTML, source, known_hash=None)
    assert result.last_updated_label is not None
    assert "December 2024" in result.last_updated_label


# --- diff_page_check tests ---


def _make_result(**kwargs) -> PageCheckResult:
    defaults = {
        "page_url": "https://example.com/page",
        "changed": False,
        "content_hash": "abc123",
        "download_links": [],
        "last_updated_label": None,
    }
    defaults.update(kwargs)
    return PageCheckResult(**defaults)


def test_diff_no_changes():
    current = _make_result(
        download_links=["https://example.com/a.xlsx"],
        last_updated_label="Jan 2025",
    )
    diff = diff_page_check(current, ["https://example.com/a.xlsx"], "Jan 2025")
    assert diff.content_changed is False
    assert diff.new_links == []
    assert diff.removed_links == []
    assert diff.release_date_changed is False


def test_diff_new_links():
    current = _make_result(
        download_links=["https://example.com/a.xlsx", "https://example.com/b.xlsx"],
    )
    diff = diff_page_check(current, ["https://example.com/a.xlsx"], None)
    assert diff.new_links == ["https://example.com/b.xlsx"]
    assert diff.removed_links == []


def test_diff_removed_links():
    current = _make_result(
        download_links=["https://example.com/a.xlsx"],
    )
    diff = diff_page_check(
        current,
        ["https://example.com/a.xlsx", "https://example.com/old.xlsx"],
        None,
    )
    assert diff.new_links == []
    assert diff.removed_links == ["https://example.com/old.xlsx"]


def test_diff_release_date_changed():
    current = _make_result(last_updated_label="Feb 2025")
    diff = diff_page_check(current, [], "Jan 2025")
    assert diff.release_date_changed is True
    assert diff.old_release_date == "Jan 2025"
    assert diff.new_release_date == "Feb 2025"


def test_diff_first_check_no_previous():
    current = _make_result(
        changed=True,
        download_links=["https://example.com/a.xlsx"],
        last_updated_label="Jan 2025",
    )
    diff = diff_page_check(current, None, None)
    assert diff.content_changed is True
    assert diff.new_links == ["https://example.com/a.xlsx"]
    assert diff.removed_links == []
    assert diff.release_date_changed is True
