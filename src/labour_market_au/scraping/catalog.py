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
# Known downloadable files (updated as we discover them via page_monitor)
# These are seed entries -- page_monitor will discover additional URLs.
# ---------------------------------------------------------------------------

KNOWN_FILES: list[FileDataset] = [
    # SALM -- DEWR is the authoritative source
    FileDataset(
        site="dewr",
        dataset="salm",
        url="https://www.dewr.gov.au/download/17068/salm-smoothed-sa2-datafiles-asgs-2021-september-quarter-2025/41973/salm-smoothed-sa2-datafiles-asgs-2021-september-quarter-2025/xlsx",
        filename="salm-smoothed-sa2-datafile.xlsx",
        parser_key="salm",
        description="SALM Smoothed SA2 data (ASGS 2021)",
    ),
    FileDataset(
        site="dewr",
        dataset="salm",
        url="https://www.dewr.gov.au/download/17069/salm-smoothed-lga-datafiles-asgs-2025-september-quarter-2025/41975/salm-smoothed-lga-datafiles-asgs-2025-september-quarter-2025/xlsx",
        filename="salm-smoothed-lga-datafile.xlsx",
        parser_key="salm",
        description="SALM Smoothed LGA data (ASGS 2025)",
    ),
    # SALM unsmoothed -- DEWR
    FileDataset(
        site="dewr",
        dataset="salm",
        url="https://www.dewr.gov.au/download/17071/salm-unsmoothed-sa2-datafiles-asgs-2021-september-quarter-2025/41977/salm-unsmoothed-sa2-datafiles-asgs-2021-september-quarter-2025/xlsx",
        filename="salm-unsmoothed-sa2-datafile.xlsx",
        parser_key="salm",
        description="SALM Unsmoothed SA2 data (ASGS 2021)",
    ),
    FileDataset(
        site="dewr",
        dataset="salm",
        url="https://www.dewr.gov.au/download/17070/salm-unsmoothed-lga-datafiles-asgs-2025-september-quarter-2025/41979/salm-unsmoothed-lga-datafiles-asgs-2025-september-quarter-2025/xlsx",
        filename="salm-unsmoothed-lga-datafile.xlsx",
        parser_key="salm",
        description="SALM Unsmoothed LGA data (ASGS 2025)",
    ),
    # IVI -- Jobs and Skills Australia
    FileDataset(
        site="jsa",
        dataset="ivi",
        url="https://www.jobsandskills.gov.au/sites/default/files/2026-02/internet_vacancies_anzsco4_occupations_states_and_territories_-_january_2026.xlsx",
        filename="internet_vacancies_anzsco4_occupations_states_and_territories_-_january_2026.xlsx",
        parser_key="ivi",
        description="IVI ANZSCO4 occupations by state (3-month average)",
    ),
    FileDataset(
        site="jsa",
        dataset="ivi",
        url="https://www.jobsandskills.gov.au/sites/default/files/2026-02/internet_vacancies_anzsco2_occupations_states_and_territories_-_january_2026.xlsx",
        filename="internet_vacancies_anzsco2_occupations_states_and_territories_-_january_2026.xlsx",
        parser_key="ivi",
        description="IVI ANZSCO2 occupations by state (trend + SA)",
    ),
    FileDataset(
        site="jsa",
        dataset="ivi",
        url="https://www.jobsandskills.gov.au/sites/default/files/2026-02/internet_vacancies_anzsco_skill_level_states_and_territories_-_january_2026.xlsx",
        filename="internet_vacancies_anzsco_skill_level_states_and_territories_-_january_2026.xlsx",
        parser_key="ivi",
        description="IVI by ANZSCO skill level and state",
    ),
    # IVI geographic region variants -- Jobs and Skills Australia
    FileDataset(
        site="jsa",
        dataset="ivi",
        url="https://www.jobsandskills.gov.au/sites/default/files/2026-02/internet_vacancies_anzsco4_occupations_jsa_remoteness_and_northern_australia_classification_-_january_2026.xlsx",
        filename="internet_vacancies_anzsco4_occupations_jsa_remoteness_and_northern_australia_classification_-_january_2026.xlsx",
        parser_key="ivi",
        description="IVI ANZSCO4 occupations by JSA remoteness",
    ),
    FileDataset(
        site="jsa",
        dataset="ivi",
        url="https://www.jobsandskills.gov.au/sites/default/files/2026-02/internet_vacancies_anzsco2_occupations_gccsa_and_sa4_regions_-_january_2026.xlsx",
        filename="internet_vacancies_anzsco2_occupations_gccsa_and_sa4_regions_-_january_2026.xlsx",
        parser_key="ivi",
        description="IVI ANZSCO2 occupations by GCCSA/SA4 regions",
    ),
    FileDataset(
        site="jsa",
        dataset="ivi",
        url="https://www.jobsandskills.gov.au/sites/default/files/2026-02/internet_vacancies_anzsco2_occupations_ivi_regions_-_january_2026.xlsx",
        filename="internet_vacancies_anzsco2_occupations_ivi_regions_-_january_2026.xlsx",
        parser_key="ivi",
        description="IVI ANZSCO2 occupations by IVI regions",
    ),
    # Employment Projections -- Jobs and Skills Australia
    FileDataset(
        site="jsa",
        dataset="projections",
        url="https://www.jobsandskills.gov.au/sites/default/files/2025-11/employment_projections_-_may_2025_to_may_2035.xlsx",
        filename="employment_projections_-_may_2025_to_may_2035.xlsx",
        parser_key="projections",
        description="Employment Projections May 2025 to May 2035",
    ),
    # Total New Vacancies -- Jobs and Skills Australia
    # Methodology: https://www.jobsandskills.gov.au/sites/default/files/2025-02/TNV%20Technical%20Note.pdf
    FileDataset(
        site="jsa",
        dataset="total_vacancies",
        url="https://www.jobsandskills.gov.au/sites/default/files/2026-02/tnv_data_-_november_2025.xlsx",
        filename="tnv_data_-_november_2025.xlsx",
        parser_key="total_vacancies",
        description="Total New Vacancies (quarterly, Nov 2025)",
    ),
]

def get_files(
    sites: list[str] | None = None,
    datasets: list[str] | None = None,
    discovered: list[dict] | None = None,
) -> list[FileDataset]:
    """Get filtered list of downloadable files (catalog + discovered).

    Discovered files with a non-empty parser_key are merged in, deduplicating
    by URL against the catalog entries.
    """
    files = list(KNOWN_FILES)

    # Merge discovered files that have a parser_key assigned
    if discovered:
        known_urls = {f.url for f in files}
        for d in discovered:
            if d.get("url") in known_urls:
                continue
            parser_key = d.get("parser_key", "")
            if not parser_key:
                continue
            files.append(FileDataset(
                site=d["site"],
                dataset=d["dataset"],
                url=d["url"],
                filename=d["filename"],
                parser_key=parser_key,
                description="Auto-discovered",
            ))

    if sites:
        files = [f for f in files if f.site in sites]
    if datasets:
        files = [f for f in files if f.dataset in datasets]
    return files
