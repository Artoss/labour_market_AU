"""
Australian Labour Market Data Scraper -- CLI entry point and orchestrator.

Usage:
    uv run labour-market-au migrate       # Apply database migrations
    uv run labour-market-au monitor       # Check pages for changes
    uv run labour-market-au download      # Download data files
    uv run labour-market-au load          # Parse and load to PostgreSQL
    uv run labour-market-au run           # Full pipeline
    uv run labour-market-au status        # Show run history and stats
    uv run labour-market-au export        # Export data to CSV/JSON
    uv run labour-market-au list          # List all data sources
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import click

from labour_market_au.config import AppConfig, load_config
from labour_market_au.utils.logging import setup_logging

logger = logging.getLogger("labour_market_au.main")


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
@click.option("--mode", type=click.Choice(["full", "incremental"]), help="Override run mode")
@click.pass_context
def cli(ctx, config_path, mode):
    """Australian Labour Market Data Scraper - IVI, SALM, Projections from JSA/DEWR."""
    ctx.ensure_object(dict)
    config = load_config(config_path)
    setup_logging(config.logging)

    if mode:
        config.run_mode = mode

    ctx.obj["config"] = config

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

@cli.command()
@click.pass_context
def migrate(ctx):
    """Apply database migrations."""
    config: AppConfig = ctx.obj["config"]
    _run_migrate(config)


@cli.command()
@click.pass_context
def monitor(ctx):
    """Check data source pages for changes and new downloads."""
    config: AppConfig = ctx.obj["config"]
    _run_monitor(config)


@cli.command()
@click.option("--dataset", "-d", multiple=True, help="Filter by dataset (salm, ivi, projections)")
@click.pass_context
def download(ctx, dataset):
    """Download data files from configured sources."""
    config: AppConfig = ctx.obj["config"]
    datasets = list(dataset) if dataset else None
    _run_download(config, datasets=datasets)


@cli.command()
@click.option("--dataset", "-d", multiple=True, help="Filter by dataset")
@click.option("--dry-run", is_flag=True, help="Show summary without loading")
@click.pass_context
def load(ctx, dataset, dry_run):
    """Parse downloaded files and load to PostgreSQL."""
    config: AppConfig = ctx.obj["config"]
    datasets = list(dataset) if dataset else None
    _run_load(config, datasets=datasets, dry_run=dry_run)


@cli.command()
@click.option("--dataset", "-d", multiple=True, help="Filter by dataset")
@click.pass_context
def run(ctx, dataset):
    """Full pipeline: monitor -> download -> parse -> load."""
    config: AppConfig = ctx.obj["config"]
    datasets = list(dataset) if dataset else None
    _run_full_pipeline(config, datasets=datasets)


@cli.command()
@click.pass_context
def status(ctx):
    """Show run history, page monitor status, and record counts."""
    config: AppConfig = ctx.obj["config"]
    _run_status(config)


@cli.command(name="export")
@click.option("--dataset", "-d", multiple=True, help="Filter by dataset")
@click.option("--format", "fmt", type=click.Choice(["csv", "json"]), default="csv")
@click.pass_context
def export_cmd(ctx, dataset, fmt):
    """Export data to CSV or JSON."""
    config: AppConfig = ctx.obj["config"]
    datasets = list(dataset) if dataset else None
    _run_export(config, datasets=datasets, fmt=fmt)


@cli.command(name="list")
@click.pass_context
def list_cmd(ctx):
    """List all data sources in the catalog."""
    config: AppConfig = ctx.obj["config"]
    _run_list(config)


# ---------------------------------------------------------------------------
# Implementation functions
# ---------------------------------------------------------------------------

def _run_migrate(config: AppConfig) -> None:
    """Run database migrations."""
    from labour_market_au.storage.database import Database

    db = Database(config.database)
    try:
        db.connect()
        db.ensure_schema("migrations")
        click.echo("Migrations applied successfully")
    finally:
        db.close()


def _run_monitor(config: AppConfig) -> None:
    """Check pages for changes and report."""
    from labour_market_au.scraping.catalog import get_sources
    from labour_market_au.scraping.client import DownloadClient
    from labour_market_au.scraping.page_monitor import check_page
    from labour_market_au.storage.database import Database

    sources = get_sources(
        sites=config.scope.sites,
        datasets=config.scope.datasets,
    )

    client = DownloadClient(config.http, config.downloads.base_dir)
    db = Database(config.database)
    try:
        db.connect()
        db.ensure_schema("migrations")

        click.echo(f"Checking {len(sources)} data source pages...")
        for source in sources:
            try:
                known_hash = db.get_page_hash(source.page_url)
                html = client.fetch_page(source.page_url)
                result = check_page(html, source, known_hash)

                status_str = "CHANGED" if result.changed else "unchanged"
                click.echo(
                    f"  [{status_str}] {source.site}/{source.dataset} "
                    f"- {len(result.download_links)} download links"
                )
                if result.last_updated_label:
                    click.echo(f"           Release: {result.last_updated_label}")
                if result.download_links:
                    for link in result.download_links[:5]:
                        click.echo(f"           -> {link}")
                    if len(result.download_links) > 5:
                        click.echo(f"           ... and {len(result.download_links) - 5} more")

                # Store results
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

            except Exception as e:
                click.echo(f"  [ERROR] {source.site}/{source.dataset}: {e}")
                logger.error("Monitor error for %s: %s", source.page_url, e, exc_info=True)

    finally:
        client.close()
        db.close()


def _run_download(config: AppConfig, datasets: list[str] | None = None) -> None:
    """Download files from catalog."""
    from labour_market_au.scraping.catalog import get_files
    from labour_market_au.scraping.client import DownloadClient
    from labour_market_au.storage.database import Database

    effective_datasets = datasets or config.scope.datasets
    files = get_files(
        sites=config.scope.sites,
        datasets=effective_datasets,
    )

    if not files:
        click.echo("No files in catalog for the selected scope. Run 'monitor' first to discover downloads.")
        return

    client = DownloadClient(config.http, config.downloads.base_dir)
    db = Database(config.database)
    try:
        db.connect()
        db.ensure_schema("migrations")

        # Get known hashes for incremental mode
        known_hashes: dict[str, str] = {}
        if config.run_mode == "incremental":
            known_hashes = db.get_known_hashes()

        click.echo(f"Downloading {len(files)} files...")
        results = client.download_catalog_files(files, known_hashes=known_hashes)

        downloaded = sum(1 for r in results if not r.skipped)
        skipped = sum(1 for r in results if r.skipped)
        click.echo(f"Downloaded: {downloaded}, Skipped: {skipped}")
        for r in results:
            status_str = "SKIP" if r.skipped else "OK"
            click.echo(f"  [{status_str}] {r.filename} ({r.file_size:,} bytes)")

    finally:
        client.close()
        db.close()


def _run_load(
    config: AppConfig,
    datasets: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    """Parse and load downloaded files to PostgreSQL."""
    from labour_market_au.storage.database import Database
    from labour_market_au.storage.loader import load_from_disk

    effective_datasets = datasets or config.scope.datasets
    data_dir = Path(config.downloads.base_dir)

    db = Database(config.database)
    try:
        db.connect()
        db.ensure_schema("migrations")

        if dry_run:
            click.echo("Dry run - scanning for files...")
            for ds in effective_datasets:
                ds_dir = data_dir / ds
                if ds_dir.exists():
                    files = list(ds_dir.glob("*.xls*"))
                    click.echo(f"  {ds}: {len(files)} files")
                    for f in files:
                        click.echo(f"    {f.name} ({f.stat().st_size:,} bytes)")
                else:
                    click.echo(f"  {ds}: no data directory")
            return

        run_id = db.start_run(run_mode=config.run_mode, config_hash=config.config_hash())

        total_records = 0
        files_loaded = 0

        for ds in effective_datasets:
            ds_dir = data_dir / ds
            if not ds_dir.exists():
                continue
            for filepath in sorted(ds_dir.glob("*.xls*")):
                try:
                    count = load_from_disk(
                        db, run_id,
                        site="dewr",  # TODO: infer from catalog
                        dataset=ds,
                        filename=filepath.name,
                        url="",
                        filepath=filepath,
                    )
                    if count > 0:
                        files_loaded += 1
                        total_records += count
                        click.echo(f"  [OK] {filepath.name}: {count:,} records")
                    else:
                        click.echo(f"  [EMPTY] {filepath.name}")
                except Exception as e:
                    click.echo(f"  [ERROR] {filepath.name}: {e}")
                    logger.error("Load error for %s: %s", filepath.name, e, exc_info=True)

        db.finish_run(
            run_id,
            status="completed",
            files_downloaded=files_loaded,
            records_loaded=total_records,
        )
        click.echo(f"\nLoaded {total_records:,} records from {files_loaded} files (run #{run_id})")

    finally:
        db.close()


def _run_full_pipeline(config: AppConfig, datasets: list[str] | None = None) -> None:
    """Full pipeline: monitor -> download -> parse -> load."""
    from labour_market_au.scraping.catalog import get_files, get_sources
    from labour_market_au.scraping.client import DownloadClient
    from labour_market_au.scraping.page_monitor import check_page
    from labour_market_au.storage.database import Database
    from labour_market_au.storage.loader import load_file

    effective_datasets = datasets or config.scope.datasets

    db = Database(config.database)
    client = DownloadClient(config.http, config.downloads.base_dir)
    try:
        db.connect()
        db.ensure_schema("migrations")
        run_id = db.start_run(run_mode=config.run_mode, config_hash=config.config_hash())

        # 1. Monitor pages
        click.echo("=== Monitoring pages ===")
        sources = get_sources(sites=config.scope.sites, datasets=effective_datasets)
        for source in sources:
            try:
                known_hash = db.get_page_hash(source.page_url)
                html = client.fetch_page(source.page_url)
                result = check_page(html, source, known_hash)
                status_str = "CHANGED" if result.changed else "ok"
                click.echo(f"  [{status_str}] {source.site}/{source.dataset}")
                db.upsert_monitored_page({
                    "page_url": source.page_url,
                    "site": source.site,
                    "dataset": source.dataset,
                    "content_hash": result.content_hash,
                    "last_updated_label": result.last_updated_label,
                    "next_release_label": result.next_release_label,
                    "download_links": json.dumps(result.download_links),
                })
            except Exception as e:
                click.echo(f"  [ERROR] {source.site}/{source.dataset}: {e}")

        # 2. Download
        click.echo("\n=== Downloading files ===")
        files = get_files(sites=config.scope.sites, datasets=effective_datasets)
        known_hashes: dict[str, str] = {}
        if config.run_mode == "incremental":
            known_hashes = db.get_known_hashes()

        download_results = client.download_catalog_files(files, known_hashes=known_hashes)

        # 3. Parse and load
        click.echo("\n=== Loading data ===")
        total_records = 0
        files_loaded = 0
        for result in download_results:
            if result.skipped:
                click.echo(f"  [SKIP] {result.filename}")
                continue
            try:
                count = load_file(db, run_id, result)
                total_records += count
                files_loaded += 1
                click.echo(f"  [OK] {result.filename}: {count:,} records")
            except Exception as e:
                logger.error("Failed to load %s: %s", result.filename, e, exc_info=True)
                click.echo(f"  [ERROR] {result.filename}: {e}")

        db.finish_run(
            run_id,
            status="completed",
            files_downloaded=files_loaded,
            records_loaded=total_records,
        )
        click.echo(
            f"\nPipeline complete: {files_loaded} files, "
            f"{total_records:,} records (run #{run_id})"
        )

    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)
        click.echo(f"Pipeline failed: {e}")
        raise
    finally:
        client.close()
        db.close()


def _run_status(config: AppConfig) -> None:
    """Show run history and stats."""
    from labour_market_au.storage.database import Database

    db = Database(config.database)
    try:
        db.connect()

        # Run history
        runs = db.get_run_history(limit=10)
        if not runs:
            click.echo("No scrape runs found. Run 'migrate' first, then 'run'.")
            return

        click.echo("=== Recent Runs ===")
        click.echo(f"{'ID':<6} {'Status':<12} {'Started':<22} {'Files':<8} {'Records':<12} {'Notes'}")
        click.echo("-" * 80)
        for r in runs:
            started = str(r.get("started_at", ""))[:19]
            click.echo(
                f"{r['id']:<6} {r.get('status', ''):<12} {started:<22} "
                f"{r.get('files_downloaded', 0)!s:<8} "
                f"{r.get('records_loaded', 0)!s:<12} "
                f"{r.get('notes', '') or ''}"
            )

        # Dataset stats
        stats = db.get_dataset_stats()
        if any(v > 0 for v in stats.values()):
            click.echo("\n=== Record Counts ===")
            for table, count in stats.items():
                click.echo(f"  {table}: {count:,}")

        # Monitored pages
        try:
            pages = db.get_monitored_pages()
            if pages:
                click.echo("\n=== Monitored Pages ===")
                for p in pages:
                    last_check = str(p.get("last_checked_at", ""))[:19]
                    last_change = str(p.get("last_changed_at", ""))[:19]
                    click.echo(
                        f"  {p['site']}/{p['dataset']}: "
                        f"checked={last_check} changed={last_change}"
                    )
        except Exception:
            pass  # Table may not exist yet

    finally:
        db.close()


def _run_export(
    config: AppConfig,
    datasets: list[str] | None = None,
    fmt: str = "csv",
) -> None:
    """Export data to CSV or JSON."""
    import pandas as pd

    from labour_market_au.storage.database import Database

    effective_datasets = datasets or config.scope.datasets
    db = Database(config.database)
    try:
        db.connect()

        out_dir = Path(config.export.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") if config.export.timestamp_files else ""

        for ds in effective_datasets:
            table = f"{ds}_data"
            try:
                with db.cursor() as cur:
                    cur.execute(f"SELECT * FROM {table} ORDER BY 1, 2")  # noqa: S608
                    rows = cur.fetchall()
            except Exception:
                click.echo(f"  {ds}: no data table or empty")
                continue

            if not rows:
                click.echo(f"  {ds}: no data")
                continue

            df = pd.DataFrame(rows)
            base = f"{ds}_{timestamp}" if timestamp else ds

            if fmt == "csv":
                filepath = out_dir / f"{base}.csv"
                df.to_csv(filepath, index=False)
            else:
                filepath = out_dir / f"{base}.json"
                df.to_json(filepath, orient="records", indent=2, default_handler=str)

            click.echo(f"  Exported {len(df):,} rows to {filepath}")

    finally:
        db.close()


def _run_list(config: AppConfig) -> None:
    """List all data sources and known files."""
    from labour_market_au.scraping.catalog import get_files, get_sources

    sources = get_sources(
        sites=config.scope.sites,
        datasets=config.scope.datasets,
    )

    click.echo("=== Data Sources (monitored pages) ===")
    click.echo(f"{'Site':<8} {'Dataset':<18} {'Frequency':<12} {'URL'}")
    click.echo("-" * 90)
    for s in sources:
        click.echo(f"{s.site:<8} {s.dataset:<18} {s.update_frequency:<12} {s.page_url}")

    files = get_files(
        sites=config.scope.sites,
        datasets=config.scope.datasets,
    )
    if files:
        click.echo(f"\n=== Known Files ({len(files)}) ===")
        click.echo(f"{'Site':<8} {'Dataset':<12} {'Description':<35} {'Filename'}")
        click.echo("-" * 90)
        for f in files:
            click.echo(f"{f.site:<8} {f.dataset:<12} {f.description:<35} {f.filename}")
