"""
Dataset registry -- defines all data sources, page URLs, and file locations.
Adding a new dataset = adding catalog entries here + a parser module.
"""

from __future__ import annotations

from pydantic import BaseModel


class DataSource(BaseModel):
    """A monitored web page that publishes downloadable datasets."""
    site: str  # jsa | dewr
    dataset: str  # salm | ivi | projections | total_vacancies
    page_url: str
    update_frequency: str  # monthly | quarterly | annual
    file_extensions: list[str] = ["xlsx", "xls"]
    content_selector: str = ""  # CSS selector for content area
    date_selector: str = ""  # CSS selector for release date


class FileDataset(BaseModel):
    """A specific downloadable file within a data source."""
    site: str
    dataset: str
    url: str
    filename: str
    parser_key: str  # maps to DATASET_PARSERS in loader.py
    description: str = ""


# ---------------------------------------------------------------------------
# JSA (Jobs and Skills Australia) sources
# ---------------------------------------------------------------------------

JSA_SOURCES: list[DataSource] = [
    DataSource(
        site="jsa",
        dataset="ivi",
        page_url="https://www.jobsandskills.gov.au/data/internet-vacancy-index",
        update_frequency="monthly",
        content_selector="div.field--type-text-long",
        date_selector="div.field--type-text-long strong",
    ),
    DataSource(
        site="jsa",
        dataset="projections",
        page_url="https://www.jobsandskills.gov.au/data/employment-projections",
        update_frequency="annual",
        content_selector="div.field--type-text-long",
    ),
    DataSource(
        site="jsa",
        dataset="total_vacancies",
        page_url="https://www.jobsandskills.gov.au/data/total-new-vacancies",
        update_frequency="monthly",
        content_selector="div.field--type-text-long",
    ),
    DataSource(
        site="jsa",
        dataset="salm",
        page_url="https://www.jobsandskills.gov.au/data/small-area-labour-markets",
        update_frequency="quarterly",
        content_selector="div.field--type-text-long",
        date_selector="div.field--type-text-long strong",
    ),
]

# ---------------------------------------------------------------------------
# DEWR (Department of Employment and Workplace Relations) sources
# ---------------------------------------------------------------------------

DEWR_SOURCES: list[DataSource] = [
    DataSource(
        site="dewr",
        dataset="salm",
        page_url="https://www.dewr.gov.au/employment-research/small-area-labour-markets",
        update_frequency="quarterly",
        content_selector="div.field--type-text-long",
    ),
]

# ---------------------------------------------------------------------------
# Known downloadable files (updated as we discover them via page_monitor)
# These are seed entries -- page_monitor will discover additional URLs.
# ---------------------------------------------------------------------------

KNOWN_FILES: list[FileDataset] = [
    # SALM -- DEWR is the authoritative source
    FileDataset(
        site="dewr",
        dataset="salm",
        url="https://www.dewr.gov.au/sites/default/files/documents/salm-smoothed-sa2-datafile.xlsx",
        filename="salm-smoothed-sa2-datafile.xlsx",
        parser_key="salm",
        description="SALM Smoothed SA2 data",
    ),
    FileDataset(
        site="dewr",
        dataset="salm",
        url="https://www.dewr.gov.au/sites/default/files/documents/salm-smoothed-lga-datafile.xlsx",
        filename="salm-smoothed-lga-datafile.xlsx",
        parser_key="salm",
        description="SALM Smoothed LGA data",
    ),
]

# All sources combined
ALL_SOURCES: list[DataSource] = JSA_SOURCES + DEWR_SOURCES


def get_sources(
    sites: list[str] | None = None,
    datasets: list[str] | None = None,
) -> list[DataSource]:
    """Get filtered list of data sources."""
    sources = ALL_SOURCES
    if sites:
        sources = [s for s in sources if s.site in sites]
    if datasets:
        sources = [s for s in sources if s.dataset in datasets]
    return sources


def get_files(
    sites: list[str] | None = None,
    datasets: list[str] | None = None,
) -> list[FileDataset]:
    """Get filtered list of known downloadable files."""
    files = KNOWN_FILES
    if sites:
        files = [f for f in files if f.site in sites]
    if datasets:
        files = [f for f in files if f.dataset in datasets]
    return files
