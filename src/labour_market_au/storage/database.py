"""
PostgreSQL storage layer.
Handles connections, migrations, and CRUD operations.
Uses psycopg 3 with dict_row factory.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import psycopg
from psycopg.rows import dict_row

from labour_market_au.config import DatabaseConfig

logger = logging.getLogger("labour_market_au.storage.database")


class Database:
    """PostgreSQL database interface for the labour market scraper."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._conn: psycopg.Connection | None = None

    # --- Connection Management ---

    def connect(self) -> None:
        logger.info(
            "Connecting to PostgreSQL at %s:%s/%s",
            self.config.pg_host,
            self.config.pg_port,
            self.config.pg_database,
        )
        self._conn = psycopg.connect(
            **self.config.connection_params,
            row_factory=dict_row,
            autocommit=False,
        )
        logger.info("Connected successfully")

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("Database connection closed")

    @contextmanager
    def cursor(self) -> Generator[psycopg.Cursor, None, None]:
        assert self._conn is not None, "Database not connected"
        with self._conn.cursor() as cur:
            try:
                yield cur
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    # --- Schema / Migrations ---

    def run_migration(self, migration_path: str | Path) -> None:
        path = Path(migration_path)
        sql = path.read_text(encoding="utf-8")
        logger.info("Running migration: %s", path.name)
        with self.cursor() as cur:
            cur.execute(psycopg.sql.SQL(sql))

    def ensure_schema(self, migrations_dir: str | Path = "migrations") -> None:
        mdir = Path(migrations_dir)
        if not mdir.exists():
            logger.warning("Migrations directory not found: %s", mdir)
            return
        for mf in sorted(mdir.glob("*.sql")):
            self.run_migration(mf)
        logger.info("All migrations applied")

    # --- Scrape Runs ---

    def start_run(self, run_mode: str, config_hash: str) -> int:
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scrape_runs (status, config_hash, notes)
                VALUES ('running', %s, %s)
                RETURNING id
                """,
                (config_hash, run_mode),
            )
            row = cur.fetchone()
            assert row is not None
            run_id = row["id"]
            logger.info("Started scrape run #%d (mode=%s)", run_id, run_mode)
            return run_id

    def finish_run(
        self,
        run_id: int,
        status: str = "completed",
        files_downloaded: int = 0,
        records_loaded: int = 0,
        notes: str | None = None,
    ) -> None:
        with self.cursor() as cur:
            cur.execute(
                """
                UPDATE scrape_runs
                SET completed_at = NOW(),
                    status = %s,
                    files_downloaded = %s,
                    records_loaded = %s,
                    notes = COALESCE(%s, notes)
                WHERE id = %s
                """,
                (status, files_downloaded, records_loaded, notes, run_id),
            )
        logger.info("Finished scrape run #%d (status=%s)", run_id, status)

    def get_run_history(self, limit: int = 10) -> list[dict]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT %s",
                (limit,),
            )
            return cur.fetchall()

    # --- Scrape Files ---

    def insert_scrape_file(
        self,
        run_id: int,
        site: str,
        dataset: str,
        filename: str,
        url: str,
        file_hash: str,
        file_size_bytes: int,
        records_loaded: int = 0,
        skipped: bool = False,
    ) -> int:
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scrape_files
                    (scrape_run_id, site, dataset, filename, url,
                     file_hash, file_size_bytes, records_loaded, skipped)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (run_id, site, dataset, filename, url,
                 file_hash, file_size_bytes, records_loaded, skipped),
            )
            row = cur.fetchone()
            assert row is not None
            return row["id"]

    def get_file_hash(self, filename: str) -> str | None:
        """Get the most recent file hash for incremental mode."""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT file_hash FROM scrape_files
                WHERE filename = %s AND NOT skipped
                ORDER BY downloaded_at DESC
                LIMIT 1
                """,
                (filename,),
            )
            row = cur.fetchone()
            return row["file_hash"] if row else None

    def get_known_hashes(self) -> dict[str, str]:
        """Get all known file hashes for incremental mode."""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (filename) filename, file_hash
                FROM scrape_files
                WHERE NOT skipped
                ORDER BY filename, downloaded_at DESC
                """
            )
            return {row["filename"]: row["file_hash"] for row in cur.fetchall()}

    # --- SALM Data ---

    def upsert_salm_data(self, records: list[dict], run_id: int) -> int:
        """Bulk upsert SALM records. Returns count of rows upserted."""
        if not records:
            return 0
        count = 0
        with self.cursor() as cur:
            for rec in records:
                cur.execute(
                    """
                    INSERT INTO salm_data
                        (geo_code, geo_name, geo_type, measure, period,
                         value, smoothed, scrape_run_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (geo_code, geo_type, measure, period, smoothed)
                    DO UPDATE SET
                        geo_name = EXCLUDED.geo_name,
                        value = EXCLUDED.value,
                        scrape_run_id = EXCLUDED.scrape_run_id,
                        loaded_at = NOW()
                    """,
                    (
                        rec["geo_code"],
                        rec["geo_name"],
                        rec["geo_type"],
                        rec["measure"],
                        rec["period"],
                        rec.get("value"),
                        rec.get("smoothed", True),
                        run_id,
                    ),
                )
                count += 1
        logger.info("Upserted %d SALM records for run #%d", count, run_id)
        return count

    # --- IVI Data ---

    def upsert_ivi_data(self, records: list[dict], run_id: int) -> int:
        """Bulk upsert IVI records using executemany. Returns count."""
        if not records:
            return 0

        sql = """
            INSERT INTO ivi_data
                (anzsco_code, anzsco_title, geo_area, skill_level,
                 period, value, index_type, file_type, geo_type, scrape_run_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (anzsco_code, geo_area, skill_level, period, index_type, file_type)
            DO UPDATE SET
                anzsco_title = EXCLUDED.anzsco_title,
                value = EXCLUDED.value,
                geo_type = EXCLUDED.geo_type,
                scrape_run_id = EXCLUDED.scrape_run_id,
                loaded_at = NOW()
        """

        params = [
            (
                rec["anzsco_code"],
                rec.get("anzsco_title", ""),
                rec.get("geo_area", ""),
                rec.get("skill_level", ""),
                rec["period"],
                rec.get("value"),
                rec.get("index_type", "level"),
                rec.get("file_type", ""),
                rec.get("geo_type", ""),
                run_id,
            )
            for rec in records
        ]

        batch_size = 10000
        count = 0
        for i in range(0, len(params), batch_size):
            batch = params[i : i + batch_size]
            with self.cursor() as cur:
                cur.executemany(sql, batch)
            count += len(batch)
            if count % 50000 == 0 or count == len(params):
                logger.info("IVI upsert progress: %d / %d", count, len(params))

        logger.info("Upserted %d IVI records for run #%d", count, run_id)
        return count

    # --- Projections Data ---

    def upsert_projections_data(self, records: list[dict], run_id: int) -> int:
        """Bulk upsert Employment Projections records using executemany."""
        if not records:
            return 0

        sql = """
            INSERT INTO projections_data
                (dimension_type, anzsco_code, occupation_name, industry_code,
                 industry_name, geo_area, geo_type, measure, base_year,
                 projection_year, value, scrape_run_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (dimension_type, anzsco_code, industry_code, geo_area,
                         measure, base_year, projection_year)
            DO UPDATE SET
                occupation_name = EXCLUDED.occupation_name,
                industry_name = EXCLUDED.industry_name,
                geo_type = EXCLUDED.geo_type,
                value = EXCLUDED.value,
                scrape_run_id = EXCLUDED.scrape_run_id,
                loaded_at = NOW()
        """

        params = [
            (
                rec.get("dimension_type", ""),
                rec.get("anzsco_code", ""),
                rec.get("occupation_name", ""),
                rec.get("industry_code", ""),
                rec.get("industry_name", ""),
                rec.get("geo_area", ""),
                rec.get("geo_type", ""),
                rec["measure"],
                rec["base_year"],
                rec["projection_year"],
                rec.get("value"),
                run_id,
            )
            for rec in records
        ]

        batch_size = 10000
        count = 0
        for i in range(0, len(params), batch_size):
            batch = params[i : i + batch_size]
            with self.cursor() as cur:
                cur.executemany(sql, batch)
            count += len(batch)

        logger.info("Upserted %d projections records for run #%d", count, run_id)
        return count

    # --- Geography ---

    def upsert_geography(self, records: list[dict]) -> int:
        """Upsert geography dimension records."""
        if not records:
            return 0
        count = 0
        with self.cursor() as cur:
            for rec in records:
                cur.execute(
                    """
                    INSERT INTO dim_geography
                        (geo_code, geo_name, geo_type, state, parent_geo_code)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (geo_code, geo_type)
                    DO UPDATE SET
                        geo_name = EXCLUDED.geo_name,
                        state = EXCLUDED.state,
                        parent_geo_code = EXCLUDED.parent_geo_code
                    """,
                    (
                        rec["geo_code"],
                        rec["geo_name"],
                        rec["geo_type"],
                        rec.get("state", ""),
                        rec.get("parent_geo_code", ""),
                    ),
                )
                count += 1
        logger.info("Upserted %d geography records", count)
        return count

    # --- ANZSCO ---

    def upsert_anzsco(self, records: list[dict]) -> int:
        """Upsert ANZSCO dimension records."""
        if not records:
            return 0

        sql = """
            INSERT INTO dim_anzsco
                (anzsco_code, anzsco_title, anzsco_level,
                 parent_code, skill_level)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (anzsco_code)
            DO UPDATE SET
                anzsco_title = EXCLUDED.anzsco_title,
                anzsco_level = EXCLUDED.anzsco_level,
                parent_code = EXCLUDED.parent_code,
                skill_level = EXCLUDED.skill_level
        """
        params = [
            (
                rec["anzsco_code"],
                rec.get("anzsco_title", ""),
                rec.get("anzsco_level", 0),
                rec.get("parent_code", ""),
                rec.get("skill_level", ""),
            )
            for rec in records
        ]

        with self.cursor() as cur:
            cur.executemany(sql, params)
        logger.info("Upserted %d ANZSCO records", len(params))
        return len(params)

    # --- Page Monitoring ---

    def get_page_hash(self, page_url: str) -> str | None:
        """Get stored content hash for a monitored page."""
        with self.cursor() as cur:
            cur.execute(
                "SELECT content_hash FROM monitored_pages WHERE page_url = %s",
                (page_url,),
            )
            row = cur.fetchone()
            return row["content_hash"] if row else None

    def upsert_monitored_page(self, page_data: dict) -> None:
        """Upsert a monitored page record."""
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO monitored_pages
                    (page_url, site, dataset, content_hash, last_checked_at,
                     last_changed_at, last_updated_label, next_release_label,
                     download_links)
                VALUES (%s, %s, %s, %s, NOW(), NOW(), %s, %s, %s::jsonb)
                ON CONFLICT (page_url)
                DO UPDATE SET
                    content_hash = EXCLUDED.content_hash,
                    last_checked_at = NOW(),
                    last_changed_at = CASE
                        WHEN monitored_pages.content_hash != EXCLUDED.content_hash
                        THEN NOW()
                        ELSE monitored_pages.last_changed_at
                    END,
                    last_updated_label = COALESCE(
                        EXCLUDED.last_updated_label,
                        monitored_pages.last_updated_label
                    ),
                    next_release_label = COALESCE(
                        EXCLUDED.next_release_label,
                        monitored_pages.next_release_label
                    ),
                    download_links = EXCLUDED.download_links
                """,
                (
                    page_data["page_url"],
                    page_data["site"],
                    page_data["dataset"],
                    page_data["content_hash"],
                    page_data.get("last_updated_label"),
                    page_data.get("next_release_label"),
                    page_data.get("download_links", "[]"),
                ),
            )

    def log_page_check(self, page_url: str, content_hash: str,
                       changed: bool, links_found: int,
                       error: str | None = None) -> None:
        """Log a page monitoring check."""
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO page_check_log
                    (page_url, checked_at, content_hash, changed,
                     download_links_found, error)
                VALUES (%s, NOW(), %s, %s, %s, %s)
                """,
                (page_url, content_hash, changed, links_found, error),
            )

    def get_monitored_page(self, page_url: str) -> dict | None:
        """Get full state for a single monitored page."""
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM monitored_pages WHERE page_url = %s",
                (page_url,),
            )
            return cur.fetchone()

    def get_monitored_pages(self) -> list[dict]:
        """Get all monitored page records."""
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM monitored_pages ORDER BY site, dataset"
            )
            return cur.fetchall()

    # --- Discovered Files ---

    def upsert_discovered_file(self, file_data: dict) -> None:
        """Upsert a discovered file URL from page monitoring."""
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO discovered_files
                    (page_url, site, dataset, url, filename, parser_key)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (url)
                DO UPDATE SET
                    last_seen_at = NOW(),
                    removed_at = NULL,
                    page_url = EXCLUDED.page_url,
                    site = EXCLUDED.site,
                    dataset = EXCLUDED.dataset,
                    filename = EXCLUDED.filename
                """,
                (
                    file_data["page_url"],
                    file_data["site"],
                    file_data["dataset"],
                    file_data["url"],
                    file_data["filename"],
                    file_data.get("parser_key", ""),
                ),
            )

    def mark_removed_files(self, page_url: str, current_urls: list[str]) -> None:
        """Mark discovered files as removed if no longer present on page."""
        if not current_urls:
            # All files removed from this page
            with self.cursor() as cur:
                cur.execute(
                    """
                    UPDATE discovered_files
                    SET removed_at = NOW()
                    WHERE page_url = %s AND removed_at IS NULL
                    """,
                    (page_url,),
                )
            return
        with self.cursor() as cur:
            cur.execute(
                """
                UPDATE discovered_files
                SET removed_at = NOW()
                WHERE page_url = %s
                  AND removed_at IS NULL
                  AND url != ALL(%s)
                """,
                (page_url, current_urls),
            )

    def get_discovered_files(self, dataset: str | None = None) -> list[dict]:
        """Get active (non-removed) discovered files, optionally filtered by dataset."""
        with self.cursor() as cur:
            if dataset:
                cur.execute(
                    """
                    SELECT * FROM discovered_files
                    WHERE removed_at IS NULL AND dataset = %s
                    ORDER BY dataset, filename
                    """,
                    (dataset,),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM discovered_files
                    WHERE removed_at IS NULL
                    ORDER BY dataset, filename
                    """
                )
            return cur.fetchall()

    # --- Dataset Notes ---

    def upsert_dataset_note(self, note: dict) -> None:
        """Upsert a dataset note. Only updates updated_at when content changes."""
        from psycopg.types.json import Json

        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dataset_notes
                    (dataset, file_type, source_type, source_ref,
                     note_text, note_tables, content_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (dataset, file_type, source_type)
                DO UPDATE SET
                    source_ref = EXCLUDED.source_ref,
                    note_text = EXCLUDED.note_text,
                    note_tables = EXCLUDED.note_tables,
                    content_hash = EXCLUDED.content_hash,
                    updated_at = CASE
                        WHEN dataset_notes.content_hash != EXCLUDED.content_hash
                        THEN NOW()
                        ELSE dataset_notes.updated_at
                    END
                """,
                (
                    note["dataset"],
                    note["file_type"],
                    note["source_type"],
                    note.get("source_ref", ""),
                    note.get("note_text", ""),
                    Json(note.get("note_tables", [])),
                    note["content_hash"],
                ),
            )
        logger.info(
            "Upserted dataset note: %s/%s/%s",
            note["dataset"], note["file_type"], note["source_type"],
        )

    def get_dataset_notes(self, dataset: str | None = None) -> list[dict]:
        """Query dataset notes, optionally filtered by dataset."""
        with self.cursor() as cur:
            if dataset:
                cur.execute(
                    """
                    SELECT * FROM dataset_notes
                    WHERE dataset = %s
                    ORDER BY dataset, file_type
                    """,
                    (dataset,),
                )
            else:
                cur.execute(
                    "SELECT * FROM dataset_notes ORDER BY dataset, file_type"
                )
            return cur.fetchall()

    # --- Total Vacancies Data ---

    def upsert_total_vacancies_data(self, records: list[dict], run_id: int) -> int:
        """Bulk upsert Total New Vacancies records using executemany."""
        if not records:
            return 0

        sql = """
            INSERT INTO total_vacancies_data
                (dimension_type, level, anzsco_code, anzsco_title,
                 geo_type, geo_area, parent_geo,
                 period, value, scrape_run_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (dimension_type, anzsco_code, geo_area, geo_type, parent_geo, period)
            DO UPDATE SET
                level = EXCLUDED.level,
                anzsco_title = EXCLUDED.anzsco_title,
                value = EXCLUDED.value,
                scrape_run_id = EXCLUDED.scrape_run_id,
                loaded_at = NOW()
        """

        params = [
            (
                rec["dimension_type"],
                rec["level"],
                rec.get("anzsco_code", ""),
                rec.get("anzsco_title", ""),
                rec.get("geo_type", ""),
                rec.get("geo_area", ""),
                rec.get("parent_geo", ""),
                rec["period"],
                rec.get("value"),
                run_id,
            )
            for rec in records
        ]

        batch_size = 10000
        count = 0
        for i in range(0, len(params), batch_size):
            batch = params[i : i + batch_size]
            with self.cursor() as cur:
                cur.executemany(sql, batch)
            count += len(batch)

        logger.info("Upserted %d total vacancies records for run #%d", count, run_id)
        return count

    # --- RLMI Data ---

    def upsert_rlmi_data(self, records: list[dict], run_id: int) -> int:
        """Bulk upsert RLMI records using executemany."""
        if not records:
            return 0

        sql = """
            INSERT INTO rlmi_data
                (data_source, sa4_code, sa4_name, geo_type, measure,
                 period, value, rating_value, rating_text, scrape_run_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (sa4_code, measure, period)
            DO UPDATE SET
                data_source = EXCLUDED.data_source,
                sa4_name = EXCLUDED.sa4_name,
                geo_type = EXCLUDED.geo_type,
                value = EXCLUDED.value,
                rating_value = EXCLUDED.rating_value,
                rating_text = EXCLUDED.rating_text,
                scrape_run_id = EXCLUDED.scrape_run_id,
                loaded_at = NOW()
        """

        params = [
            (
                rec["data_source"],
                rec.get("sa4_code", ""),
                rec.get("sa4_name", ""),
                rec.get("geo_type", ""),
                rec["measure"],
                rec["period"],
                rec.get("value"),
                rec.get("rating_value"),
                rec.get("rating_text", ""),
                run_id,
            )
            for rec in records
        ]

        batch_size = 10000
        count = 0
        for i in range(0, len(params), batch_size):
            batch = params[i : i + batch_size]
            with self.cursor() as cur:
                cur.executemany(sql, batch)
            count += len(batch)

        logger.info("Upserted %d RLMI records for run #%d", count, run_id)
        return count

    # --- LFT Data ---

    def upsert_lft_data(self, records: list[dict], run_id: int) -> int:
        """Bulk upsert Labour Force Trending records using executemany."""
        if not records:
            return 0

        sql = """
            INSERT INTO lft_data
                (file_type, level, code, title, geo_area, geo_type,
                 parent_code, period, value, scrape_run_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (file_type, code, geo_area, period)
            DO UPDATE SET
                level = EXCLUDED.level,
                title = EXCLUDED.title,
                geo_type = EXCLUDED.geo_type,
                parent_code = EXCLUDED.parent_code,
                value = EXCLUDED.value,
                scrape_run_id = EXCLUDED.scrape_run_id,
                loaded_at = NOW()
        """

        params = [
            (
                rec["file_type"],
                rec["level"],
                rec["code"],
                rec.get("title", ""),
                rec.get("geo_area", ""),
                rec.get("geo_type", ""),
                rec.get("parent_code", ""),
                rec["period"],
                rec.get("value"),
                run_id,
            )
            for rec in records
        ]

        batch_size = 10000
        count = 0
        for i in range(0, len(params), batch_size):
            batch = params[i : i + batch_size]
            with self.cursor() as cur:
                cur.executemany(sql, batch)
            count += len(batch)
            if count % 100000 == 0 or count == len(params):
                logger.info("LFT upsert progress: %d / %d", count, len(params))

        logger.info("Upserted %d LFT records for run #%d", count, run_id)
        return count

    # --- Publication Calendar ---

    def get_due_releases(self, as_of_date) -> list[dict]:
        """Return unprocessed calendar rows where release_date_parsed <= as_of_date."""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM publication_calendar
                WHERE release_date_parsed <= %s
                  AND processed_at IS NULL
                ORDER BY release_date_parsed
                """,
                (as_of_date,),
            )
            return cur.fetchall()

    def upsert_publication_calendar(self, rows: list[dict]) -> int:
        """Batch upsert future release entries. Returns count of rows upserted."""
        if not rows:
            return 0

        sql = """
            INSERT INTO publication_calendar
                (dataset, site, data_period, release_date,
                 release_date_parsed, source_url)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (dataset, site, data_period)
            DO UPDATE SET
                release_date = EXCLUDED.release_date,
                release_date_parsed = EXCLUDED.release_date_parsed,
                source_url = EXCLUDED.source_url,
                scraped_at = NOW()
        """

        count = 0
        with self.cursor() as cur:
            for row in rows:
                cur.execute(sql, (
                    row["dataset"],
                    row["site"],
                    row["data_period"],
                    row["release_date"],
                    row.get("release_date_parsed"),
                    row["source_url"],
                ))
                count += 1

        logger.info("Upserted %d publication calendar entries", count)
        return count

    def mark_release_processed(
        self, dataset: str, data_period: str, scrape_run_id: int,
    ) -> None:
        """Mark a calendar release as processed with a link to the scrape run."""
        with self.cursor() as cur:
            cur.execute(
                """
                UPDATE publication_calendar
                SET processed_at = NOW(),
                    scrape_run_id = %s
                WHERE dataset = %s AND data_period = %s
                """,
                (scrape_run_id, dataset, data_period),
            )
        logger.info(
            "Marked release processed: %s / %s (run #%d)",
            dataset, data_period, scrape_run_id,
        )

    # --- Stats ---

    def get_dataset_stats(self) -> dict:
        """Get record counts per dataset table."""
        stats = {}
        for table in ("salm_data", "ivi_data", "projections_data", "total_vacancies_data", "rlmi_data", "lft_data"):
            with self.cursor() as cur:
                try:
                    cur.execute(f"SELECT COUNT(*) as cnt FROM {table}")  # noqa: S608
                    row = cur.fetchone()
                    stats[table] = row["cnt"] if row else 0
                except psycopg.errors.UndefinedTable:
                    stats[table] = 0
                    self._conn.rollback()  # type: ignore[union-attr]
        return stats
