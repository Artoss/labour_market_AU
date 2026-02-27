"""
HTML metadata extraction utilities.
Used by page_monitor to extract structured data from data source pages.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup


def extract_download_links(
    html: str,
    base_url: str,
    extensions: tuple[str, ...] = (".xlsx", ".xls", ".csv"),
) -> list[str]:
    """Extract all download links from HTML matching given extensions."""
    soup = BeautifulSoup(html, "lxml")
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


def extract_text_by_selector(html: str, css_selector: str) -> str | None:
    """Extract text from the first element matching a CSS selector."""
    soup = BeautifulSoup(html, "lxml")
    el = soup.select_one(css_selector)
    if el:
        return el.get_text(strip=True)
    return None


def extract_release_metadata(html: str) -> dict[str, str | None]:
    """Extract release date and next release from JSA/DEWR pages."""
    soup = BeautifulSoup(html, "lxml")

    release_date = None
    next_release = None

    # Try to find release date from strong tags in content area
    content_divs = soup.find_all("div", class_="field--type-text-long")
    for div in content_divs:
        strong = div.find("strong")
        if strong:
            text = strong.get_text(strip=True)
            if text and len(text) < 200:
                release_date = text
                break

    # Try to find next release
    for text_block in soup.find_all(string=re.compile(r"next\s+release", re.IGNORECASE)):
        parent = text_block.parent
        if parent:
            full_text = parent.get_text(strip=True)
            if len(full_text) < 300:
                next_release = full_text
                break

    return {
        "release_date": release_date,
        "next_release": next_release,
    }
