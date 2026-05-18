"""
Page monitor -- detects changes on data source web pages via content hashing.
Extracts metadata (release dates, download links) from HTML.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from bs4 import BeautifulSoup

from labour_market_au.scraping.catalog import DataSource

logger = logging.getLogger("labour_market_au.scraping.page_monitor")


class PageCheckResult:
    """Result of checking a monitored page."""

    def __init__(
        self,
        page_url: str,
        changed: bool,
        content_hash: str,
        download_links: list[str],
        last_updated_label: str | None = None,
        next_release_label: str | None = None,
        error: str | None = None,
    ):
        self.page_url = page_url
        self.changed = changed
        self.content_hash = content_hash
        self.download_links = download_links
        self.last_updated_label = last_updated_label
        self.next_release_label = next_release_label
        self.error = error


def check_page(
    html: str,
    source: DataSource,
    known_hash: str | None = None,
) -> PageCheckResult:
    """Parse HTML, extract content hash and metadata, compare with known hash."""
    soup = BeautifulSoup(html, "lxml")

    # Extract content area for hashing
    content_text = _extract_content_text(soup, source.content_selector)
    content_hash = hashlib.sha256(content_text.encode()).hexdigest()

    changed = known_hash is None or content_hash != known_hash

    # Extract download links
    download_links = _extract_download_links(soup, source.page_url)

    # Extract metadata
    last_updated = _extract_release_date(soup, source.date_selector)
    next_release = _extract_next_release(soup)

    logger.info(
        "Page %s: hash=%s changed=%s links=%d",
        source.page_url, content_hash[:12], changed, len(download_links),
    )

    return PageCheckResult(
        page_url=source.page_url,
        changed=changed,
        content_hash=content_hash,
        download_links=download_links,
        last_updated_label=last_updated,
        next_release_label=next_release,
    )


def _extract_content_text(soup: BeautifulSoup, selector: str) -> str:
    """Extract and normalize text from the content area."""
    if selector:
        elements = soup.select(selector)
        if elements:
            text = " ".join(el.get_text(strip=True) for el in elements)
        else:
            text = soup.get_text(strip=True)
    else:
        text = soup.get_text(strip=True)
    # Normalize whitespace for stable hashing
    return re.sub(r"\s+", " ", text).strip()


def _extract_download_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    """Extract all download links (Excel, CSV) from the page."""
    base_url = "/".join(page_url.split("/")[:3])
    extensions = (".xlsx", ".xls", ".csv")
    links = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if any(href.lower().endswith(ext) for ext in extensions):
            if href.startswith("http"):
                links.append(href)
            elif href.startswith("/"):
                links.append(base_url + href)
            else:
                links.append(base_url + "/" + href)
    return sorted(set(links))


def _extract_release_date(soup: BeautifulSoup, selector: str) -> str | None:
    """Try to extract the release/update date from the page."""
    if not selector:
        return None
    elements = soup.select(selector)
    for el in elements:
        text = el.get_text(strip=True)
        if text and len(text) < 200:
            return text
    return None


def _extract_next_release(soup: BeautifulSoup) -> str | None:
    """Try to find a 'next release' date on the page."""
    for text_block in soup.find_all(string=re.compile(r"next\s+release", re.IGNORECASE)):
        parent = text_block.parent
        if parent:
            full_text = parent.get_text(strip=True)
            if len(full_text) < 300:
                return full_text
    return None


def _filename_from_url(url: str) -> str:
    """Extract filename from a download URL."""
    path = PurePosixPath(url.split("?")[0].split("#")[0])
    return path.name


@dataclass
class PageChangeSummary:
    """Summary of changes between two page checks."""

    content_changed: bool
    new_links: list[str] = field(default_factory=list)
    removed_links: list[str] = field(default_factory=list)
    release_date_changed: bool = False
    old_release_date: str | None = None
    new_release_date: str | None = None


def extract_future_releases(
    soup: BeautifulSoup,
    dataset: str,
    site: str,
    source_url: str,
) -> list[dict]:
    """Extract future release dates from a page's HTML.

    Finds <table> elements near "Future release dates" headings and parses
    them into structured records for the publication_calendar table.

    Returns list of dicts with keys:
        dataset, site, data_period, release_date, release_date_parsed, source_url
    """
    from dateutil import parser as dateutil_parser

    results: list[dict] = []

    # Find headings that mention future release dates
    headings = soup.find_all(
        string=re.compile(r"future\s+release\s+date", re.IGNORECASE),
    )

    for heading_text in headings:
        # Walk up to the parent element, then find the next table
        parent = heading_text.parent
        if parent is None:
            continue

        # Look for a table in the siblings after this heading
        table = None
        for sibling in parent.find_all_next():
            if sibling.name == "table":
                table = sibling
                break
            # Stop if we hit another heading (went too far)
            if sibling.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                break

        if table is None:
            continue

        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # Parse header row to find column indices
        headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]

        # Try to identify data_period and release_date columns
        period_idx = None
        date_idx = None
        for i, h in enumerate(headers):
            if "data" in h or "period" in h or "reference" in h or "month" in h:
                period_idx = i
            elif "release" in h or "date" in h or "publish" in h:
                date_idx = i

        # Fallback: assume first col = period, second = release date
        if period_idx is None and date_idx is None and len(headers) >= 2:
            period_idx = 0
            date_idx = 1

        if period_idx is None or date_idx is None:
            continue

        # Parse data rows
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all(["th", "td"])]
            if len(cells) <= max(period_idx, date_idx):
                continue

            data_period = cells[period_idx]
            release_date = cells[date_idx]

            if not data_period or not release_date:
                continue

            # Try to parse the release date
            release_date_parsed = None
            try:
                parsed = dateutil_parser.parse(release_date, dayfirst=True, fuzzy=True)
                release_date_parsed = parsed.date()
            except (ValueError, OverflowError):
                pass

            results.append({
                "dataset": dataset,
                "site": site,
                "data_period": data_period,
                "release_date": release_date,
                "release_date_parsed": release_date_parsed,
                "source_url": source_url,
            })

    logger.info(
        "Extracted %d future release entries from %s/%s",
        len(results), site, dataset,
    )
    return results


def diff_page_check(
    current: PageCheckResult,
    previous_links: list[str] | None,
    previous_release_label: str | None,
) -> PageChangeSummary:
    """Compare current check result with previous state to produce a diff."""
    prev_set = set(previous_links) if previous_links else set()
    curr_set = set(current.download_links)

    new_links = sorted(curr_set - prev_set)
    removed_links = sorted(prev_set - curr_set)

    release_changed = (
        current.last_updated_label != previous_release_label
        and current.last_updated_label is not None
    )

    return PageChangeSummary(
        content_changed=current.changed,
        new_links=new_links,
        removed_links=removed_links,
        release_date_changed=release_changed,
        old_release_date=previous_release_label if release_changed else None,
        new_release_date=current.last_updated_label if release_changed else None,
    )
