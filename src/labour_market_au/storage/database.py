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
                        (geo_code, geo_name, geo_level, measure, period,
                         value, smoothed, scrape_run_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (geo_code, geo_level, measure, period)
                    DO UPDATE SET
                        geo_name = EXCLUDED.geo_name,
                        value = EXCLUDED.value,
                        smoothed = EXCLUDED.smoothed,
                        scrape_run_id = EXCLUDED.scrape_run_id,
                        loaded_at = NOW()
                    """,
                    (
                        rec["geo_code"],
                        rec["geo_name"],
                        rec["geo_level"],
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
        """Bulk upsert IVI records. Returns count of rows upserted."""
        if not records:
            return 0
        count = 0
        with self.cursor() as cur:
            for rec in records:
                cur.execute(
                    """
                    INSERT INTO ivi_data
                        (anzsco_code, anzsco_title, state, skill_level,
                         period, value, index_type, scrape_run_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (anzsco_code, state, skill_level, period, index_type)
                    DO UPDATE SET
                        anzsco_title = EXCLUDED.anzsco_title,
                        value = EXCLUDED.value,
                        scrape_run_id = EXCLUDED.scrape_run_id,
                        loaded_at = NOW()
                    """,
                    (
                        rec["anzsco_code"],
                        rec.get("anzsco_title", ""),
                        rec.get("state", ""),
                        rec.get("skill_level", ""),
                        rec["period"],
                        rec.get("value"),
                        rec.get("index_type", "level"),
                        run_id,
                    ),
                )
                count += 1
        logger.info("Upserted %d IVI records for run #%d", count, run_id)
        return count

    # --- Projections Data ---

    def upsert_projections_data(self, records: list[dict], run_id: int) -> int:
        """Bulk upsert Employment Projections records."""
        if not records:
            return 0
        count = 0
        with self.cursor() as cur:
            for rec in records:
                cur.execute(
                    """
                    INSERT INTO projections_data
                        (anzsco_code, occupation_name, industry_code,
                         industry_name, state, measure, base_year,
                         projection_year, value, scrape_run_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (anzsco_code, industry_code, state, measure,
                                 base_year, projection_year)
                    DO UPDATE SET
                        occupation_name = EXCLUDED.occupation_name,
                        industry_name = EXCLUDED.industry_name,
                        value = EXCLUDED.value,
                        scrape_run_id = EXCLUDED.scrape_run_id,
                        loaded_at = NOW()
                    """,
                    (
                        rec["anzsco_code"],
                        rec.get("occupation_name", ""),
                        rec.get("industry_code", ""),
                        rec.get("industry_name", ""),
                        rec.get("state", ""),
                        rec["measure"],
                        rec["base_year"],
                        rec["projection_year"],
                        rec.get("value"),
                        run_id,
                    ),
                )
                count += 1
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
                        (geo_code, geo_name, geo_level, state, parent_geo_code)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (geo_code, geo_level)
                    DO UPDATE SET
                        geo_name = EXCLUDED.geo_name,
                        state = EXCLUDED.state,
                        parent_geo_code = EXCLUDED.parent_geo_code
                    """,
                    (
                        rec["geo_code"],
                        rec["geo_name"],
                        rec["geo_level"],
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
        count = 0
        with self.cursor() as cur:
            for rec in records:
                cur.execute(
                    """
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
                    """,
                    (
                        rec["anzsco_code"],
                        rec.get("anzsco_title", ""),
                        rec.get("anzsco_level", 0),
                        rec.get("parent_code", ""),
                        rec.get("skill_level", ""),
                    ),
                )
                count += 1
        logger.info("Upserted %d ANZSCO records", count)
        return count

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

    def get_monitored_pages(self) -> list[dict]:
        """Get all monitored page records."""
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM monitored_pages ORDER BY site, dataset"
            )
            return cur.fetchall()

    # --- Stats ---

    def get_dataset_stats(self) -> dict:
        """Get record counts per dataset table."""
        stats = {}
        for table in ("salm_data", "ivi_data", "projections_data"):
            with self.cursor() as cur:
                try:
                    cur.execute(f"SELECT COUNT(*) as cnt FROM {table}")  # noqa: S608
                    row = cur.fetchone()
                    stats[table] = row["cnt"] if row else 0
                except psycopg.errors.UndefinedTable:
                    stats[table] = 0
                    self._conn.rollback()  # type: ignore[union-attr]
        return stats
