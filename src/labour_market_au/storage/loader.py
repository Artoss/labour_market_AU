"""
Loader -- orchestrates parsing and loading for downloaded files.
"""

from __future__ import annotations

import logging
from pathlib import Path

from labour_market_au.scraping.client import DownloadResult
from labour_market_au.storage.database import Database

logger = logging.getLogger("labour_market_au.storage.loader")

# Map dataset keys to parser functions and DB upsert methods
DATASET_PARSERS = {
    "salm": ("labour_market_au.extraction.salm_parser", "parse_salm_excel"),
    "ivi": ("labour_market_au.extraction.ivi_parser", "parse_ivi_excel"),
    "projections": ("labour_market_au.extraction.projections_parser", "parse_projections_excel"),
    "total_vacancies": ("labour_market_au.extraction.tnv_parser", "parse_tnv_excel"),
    "rlmi": ("labour_market_au.extraction.rlmi_parser", "parse_rlmi_excel"),
    "labour_force_trending": ("labour_market_au.extraction.lft_parser", "parse_lft_excel"),
}

DATASET_UPSERT = {
    "salm": "upsert_salm_data",
    "ivi": "upsert_ivi_data",
    "projections": "upsert_projections_data",
    "total_vacancies": "upsert_total_vacancies_data",
    "rlmi": "upsert_rlmi_data",
    "labour_force_trending": "upsert_lft_data",
}


def _get_parser(dataset: str):
    """Lazy-import the parser function for a dataset."""
    import importlib

    if dataset not in DATASET_PARSERS:
        raise ValueError(f"No parser registered for dataset: {dataset}")

    module_path, func_name = DATASET_PARSERS[dataset]
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


def load_file(
    db: Database,
    run_id: int,
    download: DownloadResult,
) -> int:
    """Parse and load a single downloaded file into the database.

    Returns the number of records loaded.
    """
    dataset = download.dataset_key
    filepath = download.filepath
    logger.info("Parsing and loading %s (dataset=%s)", filepath.name, dataset)

    if dataset not in DATASET_PARSERS:
        logger.warning("No parser for dataset '%s', skipping %s", dataset, filepath.name)
        return 0

    # Parse file to list of dicts
    parse_fn = _get_parser(dataset)
    records = parse_fn(filepath)

    if not records:
        logger.warning("No records extracted from %s", filepath.name)
        return 0

    # Populate dimension tables and capture notes
    if dataset == "ivi":
        _populate_anzsco_dim(db, records)
        _store_notes(db, "ivi", filepath)
    elif dataset == "total_vacancies":
        _store_notes(db, "total_vacancies", filepath)
    elif dataset == "rlmi":
        _store_notes(db, "rlmi", filepath)
    elif dataset == "labour_force_trending":
        _store_notes(db, "labour_force_trending", filepath)

    # Upsert to database
    upsert_method = getattr(db, DATASET_UPSERT[dataset])
    count = upsert_method(records, run_id)

    # Record the file in scrape_files
    db.insert_scrape_file(
        run_id=run_id,
        site=download.site,
        dataset=dataset,
        filename=download.filename,
        url=download.url,
        file_hash=download.file_hash,
        file_size_bytes=download.file_size,
        records_loaded=count,
    )

    logger.info("Loaded %s: %d records", filepath.name, count)
    return count


def _populate_anzsco_dim(db: Database, records: list[dict]) -> None:
    """Extract unique ANZSCO code/title pairs from IVI records and upsert."""
    seen: dict[str, str] = {}
    for rec in records:
        code = rec.get("anzsco_code", "")
        title = rec.get("anzsco_title", "")
        if code and code not in seen:
            seen[code] = title

    if not seen:
        return

    anzsco_records = []
    for code, title in seen.items():
        # Determine ANZSCO level from code length
        code_clean = code.strip()
        anzsco_level = len(code_clean) if code_clean.isdigit() else 0
        parent_code = code_clean[:-1] if len(code_clean) > 1 and code_clean.isdigit() else ""
        anzsco_records.append({
            "anzsco_code": code_clean,
            "anzsco_title": title,
            "anzsco_level": anzsco_level,
            "parent_code": parent_code,
            "skill_level": "",
        })

    count = db.upsert_anzsco(anzsco_records)
    logger.info("Populated %d ANZSCO dimension records", count)


def _store_notes(db: Database, dataset: str, filepath: Path) -> None:
    """Extract and store notes from an Excel workbook."""
    if dataset == "ivi":
        from labour_market_au.extraction.ivi_parser import extract_ivi_notes

        note = extract_ivi_notes(filepath)
    elif dataset == "total_vacancies":
        from labour_market_au.extraction.tnv_parser import extract_tnv_notes

        note = extract_tnv_notes(filepath)
    elif dataset == "rlmi":
        from labour_market_au.extraction.rlmi_parser import extract_rlmi_notes

        note = extract_rlmi_notes(filepath)
    elif dataset == "labour_force_trending":
        from labour_market_au.extraction.lft_parser import extract_lft_notes

        note = extract_lft_notes(filepath)
    else:
        return

    if note is None:
        return

    try:
        db.upsert_dataset_note(note)
    except Exception:
        logger.warning("Failed to store notes from %s", filepath.name, exc_info=True)


def load_from_disk(
    db: Database,
    run_id: int,
    site: str,
    dataset: str,
    filename: str,
    url: str,
    filepath: Path,
) -> int:
    """Parse and load a file that already exists on disk."""
    from labour_market_au.scraping.client import DownloadClient

    if not filepath.exists():
        logger.warning("File not found: %s", filepath)
        return 0

    file_hash = DownloadClient.file_hash(filepath)
    file_size = filepath.stat().st_size

    result = DownloadResult(
        site=site,
        dataset_key=dataset,
        filename=filename,
        url=url,
        filepath=filepath,
        file_hash=file_hash,
        file_size=file_size,
    )
    return load_file(db, run_id, result)
