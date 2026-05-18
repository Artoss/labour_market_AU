"""Prefect-orchestrated daily JSA/DEWR monitoring + auto-load pipeline.

Usage:
    python -m labour_market_au.prefect_flow              # One-shot run
    python -m labour_market_au.prefect_flow --serve       # Cron scheduler (daily 8am AEST)
"""
from __future__ import annotations

import argparse
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import date

from dotenv import load_dotenv

load_dotenv()

from prefect import flow, task  # noqa: E402

log = logging.getLogger("labour_market_au.prefect_flow")


# ---------------------------------------------------------------------------
# Prefect API readiness check
# ---------------------------------------------------------------------------

def _wait_for_prefect_api(max_retries: int = 10, initial_delay: float = 2.0) -> None:
    """Wait for Prefect API with exponential backoff.

    No-op if PREFECT_API_URL is not set (local ephemeral mode).
    """
    api_url = os.environ.get("PREFECT_API_URL", "")
    if not api_url:
        print("PREFECT_API_URL not set, using local/ephemeral Prefect.")
        return

    health_url = api_url.rstrip("/").rsplit("/api", 1)[0] + "/api/health"
    print(f"Waiting for Prefect API at {health_url} ...")

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(health_url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    print("Prefect API is healthy.")
                    return
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            if attempt == max_retries - 1:
                raise RuntimeError(
                    f"Prefect API not reachable after {max_retries} attempts"
                ) from exc
            delay = min(initial_delay * (2 ** attempt), 60.0)
            print(
                f"Prefect API not ready (attempt {attempt + 1}/{max_retries}),"
                f" retrying in {delay:.0f}s..."
            )
            time.sleep(delay)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@task(name="refresh_calendar")
def task_refresh_calendar() -> int:
    """Fetch JSA/DEWR pages and parse future release tables into publication_calendar.

    Returns the number of calendar entries upserted.
    """
    import json

    from bs4 import BeautifulSoup

    from labour_market_au.config import load_config
    from labour_market_au.scraping.catalog import DataSource
    from labour_market_au.scraping.client import DownloadClient
    from labour_market_au.scraping.page_monitor import extract_future_releases
    from labour_market_au.storage.database import Database

    config = load_config("config.yaml")
    sources = [DataSource(**page.model_dump()) for page in config.monitor_pages]

    client = DownloadClient(config.http, config.downloads.base_dir)
    db = Database(config.database)
    total = 0
    try:
        db.connect()
        db.ensure_schema("migrations")

        for source in sources:
            try:
                html = client.fetch_page(source.page_url)
                soup = BeautifulSoup(html, "lxml")
                releases = extract_future_releases(
                    soup, source.dataset, source.site, source.page_url,
                )
                if releases:
                    count = db.upsert_publication_calendar(releases)
                    total += count
                    log.info(
                        "Refreshed %d calendar entries for %s/%s",
                        count, source.site, source.dataset,
                    )
            except Exception as exc:
                log.warning(
                    "Failed to refresh calendar for %s/%s: %s",
                    source.site, source.dataset, exc,
                )
    finally:
        client.close()
        db.close()

    print(f"Calendar refresh: {total} entries upserted")
    return total


@task(name="check_due_releases")
def task_check_due_releases(as_of: date | None = None) -> list[dict]:
    """Query publication_calendar for releases due today or earlier.

    Returns list of due release dicts.
    """
    from labour_market_au.config import load_config
    from labour_market_au.storage.database import Database

    if as_of is None:
        as_of = date.today()

    config = load_config("config.yaml")
    db = Database(config.database)
    try:
        db.connect()
        db.ensure_schema("migrations")
        due = db.get_due_releases(as_of)
    finally:
        db.close()

    if due:
        print(f"Found {len(due)} due release(s):")
        for r in due:
            print(f"  {r['dataset']}: {r['data_period']} (release: {r['release_date']})")
    else:
        print("No releases due.")

    return due


@task(name="monitor_and_load", retries=1, retry_delay_seconds=120)
def task_monitor_and_load(dataset: str) -> dict:
    """Run the full monitor -> download -> load pipeline for a single dataset.

    Returns summary dict with records loaded and run_id.
    """
    import json
    from pathlib import Path

    from labour_market_au.config import load_config
    from labour_market_au.notify import notify_pipeline_failure, notify_pipeline_success
    from labour_market_au.scraping.catalog import DataSource, get_files
    from labour_market_au.scraping.client import DownloadClient
    from labour_market_au.scraping.page_monitor import (
        _filename_from_url,
        check_page,
    )
    from labour_market_au.storage.database import Database
    from labour_market_au.storage.loader import load_from_disk
    from labour_market_au.utils.logging import setup_logging

    config = load_config("config.yaml")
    setup_logging(config.logging)

    dataset_site_map = {
        "salm": "dewr",
        "ivi": "jsa",
        "projections": "jsa",
        "total_vacancies": "jsa",
        "rlmi": "jsa",
        "labour_force_trending": "jsa",
    }

    client = DownloadClient(config.http, config.downloads.base_dir)
    db = Database(config.database)
    try:
        db.connect()
        db.ensure_schema("migrations")

        # 1. Monitor the relevant page(s)
        sources = [
            DataSource(**p.model_dump())
            for p in config.monitor_pages
            if p.dataset == dataset
        ]
        for source in sources:
            try:
                known_hash = db.get_page_hash(source.page_url)
                html = client.fetch_page(source.page_url)
                result = check_page(html, source, known_hash)

                db.upsert_monitored_page({
                    "page_url": source.page_url,
                    "site": source.site,
                    "dataset": source.dataset,
                    "content_hash": result.content_hash,
                    "last_updated_label": result.last_updated_label,
                    "next_release_label": result.next_release_label,
                    "download_links": json.dumps(result.download_links),
                })
                db.log_page_check(
                    page_url=source.page_url,
                    content_hash=result.content_hash,
                    changed=result.changed,
                    links_found=len(result.download_links),
                )

                # Auto-discover download links
                from labour_market_au.main import _infer_parser_key

                for link_url in result.download_links:
                    fname = _filename_from_url(link_url)
                    db.upsert_discovered_file({
                        "page_url": source.page_url,
                        "site": source.site,
                        "dataset": source.dataset,
                        "url": link_url,
                        "filename": fname,
                        "parser_key": _infer_parser_key(fname, source.dataset),
                    })
                db.mark_removed_files(source.page_url, result.download_links)

            except Exception as exc:
                log.warning("Monitor error for %s: %s", source.page_url, exc)

        # 2. Download files for this dataset
        discovered = db.get_discovered_files(dataset=dataset)
        files = get_files(
            sites=config.scope.sites,
            datasets=[dataset],
            discovered=discovered,
        )
        known_hashes = db.get_known_hashes()
        download_results = client.download_catalog_files(files, known_hashes=known_hashes)

        # 3. Parse and load
        run_id = db.start_run(run_mode="automate", config_hash=config.config_hash())
        total_records = 0
        files_loaded = 0

        site = dataset_site_map.get(dataset, "jsa")
        data_dir = Path(config.downloads.base_dir)
        ds_dir = data_dir / site / dataset

        if ds_dir.exists():
            for filepath in sorted(ds_dir.glob("*.xls*")):
                try:
                    count = load_from_disk(
                        db, run_id,
                        site=site,
                        dataset=dataset,
                        filename=filepath.name,
                        url="",
                        filepath=filepath,
                    )
                    if count > 0:
                        files_loaded += 1
                        total_records += count
                except Exception as exc:
                    log.error("Load error for %s: %s", filepath.name, exc, exc_info=True)

        db.finish_run(
            run_id,
            status="completed",
            files_downloaded=files_loaded,
            records_loaded=total_records,
        )

        notify_pipeline_success(dataset, total_records)

        return {
            "dataset": dataset,
            "run_id": run_id,
            "files_loaded": files_loaded,
            "records": total_records,
        }

    except Exception as exc:
        notify_pipeline_failure(exc, dataset=dataset)
        raise
    finally:
        client.close()
        db.close()


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------

def _on_crashed(flow, flow_run, state):
    """Called by Prefect when a flow run process dies."""
    from labour_market_au.notify import notify_pipeline_failure

    notify_pipeline_failure(
        RuntimeError(state.message or "Flow run crashed unexpectedly"),
        dataset="(all)",
    )


@flow(name="jsa-monitor", log_prints=True, on_crashed=[_on_crashed])
def jsa_monitor_flow() -> None:
    """Daily pipeline: refresh calendar, check for due releases, load if any.

    1. Refresh publication_calendar from JSA/DEWR pages
    2. Check for releases due today or earlier
    3. For each due release: monitor page -> download -> parse -> load
    4. Mark releases as processed
    5. If nothing due: quiet exit
    """
    from labour_market_au.config import load_config
    from labour_market_au.notify import notify_pipeline_failure, notify_release_detected
    from labour_market_au.storage.database import Database

    current_step = "refresh_calendar"
    try:
        # 1. Refresh calendar
        task_refresh_calendar()

        # 2. Check for due releases
        current_step = "check_due_releases"
        due_releases = task_check_due_releases()

        if not due_releases:
            print("No releases due today. Exiting.")
            return

        # 3. Process each due release
        config = load_config("config.yaml")
        processed_datasets: set[str] = set()

        for release in due_releases:
            ds = release["dataset"]
            data_period = release["data_period"]

            # Skip if we already processed this dataset in this run
            if ds in processed_datasets:
                log.info("Already processed %s this run, skipping %s", ds, data_period)
                continue

            current_step = f"load_{ds}"
            print(f"Processing due release: {ds} ({data_period})")
            notify_release_detected(ds, data_period)

            summary = task_monitor_and_load(ds)

            # Mark release as processed
            if summary["records"] > 0:
                db = Database(config.database)
                try:
                    db.connect()
                    db.mark_release_processed(ds, data_period, summary["run_id"])
                finally:
                    db.close()

            processed_datasets.add(ds)

            print(
                f"Completed {ds}: {summary['records']:,} records "
                f"from {summary['files_loaded']} files (run #{summary['run_id']})"
            )

    except Exception as exc:
        notify_pipeline_failure(exc, dataset=current_step)
        log.error("Pipeline failed at step '%s': %s", current_step, exc)
        raise


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="JSA/DEWR Labour Market monitor pipeline (Prefect-orchestrated)."
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start Prefect scheduler (cron: daily 8am AEST). Otherwise runs once.",
    )
    args = parser.parse_args()

    try:
        _wait_for_prefect_api()

        if args.serve:
            jsa_monitor_flow.serve(
                name="jsa-monitor",
                cron="0 22 * * *",  # 8am AEST = 10pm UTC previous day
            )
        else:
            jsa_monitor_flow()
    except Exception as exc:
        log.error("Startup crash: %s", exc)
        from labour_market_au.notify import notify_pipeline_failure
        notify_pipeline_failure(exc, dataset="startup")
        raise
