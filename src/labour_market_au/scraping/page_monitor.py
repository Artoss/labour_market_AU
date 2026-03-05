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
