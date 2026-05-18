"""Sync JSA/DEWR release entries to the shared statistic_publication_calendar.

Writes to the `scraping` database using the unified schema defined in
Scraper_0015_ABS_MASTER/ABS_calendar/Research/statistic_publication_calendar_CREATE_20250416.sql.

Optional -- only runs if calendar_database is configured in config.yaml.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from labour_market_au.scraping.catalog import DATASET_PUBLICATION_MAP

logger = logging.getLogger("labour_market_au.storage.calendar_sync")

# Standard conventions across all 3 projects
PUBLISHER_MAP = {
    "jsa": ("JSA", "Jobs and Skills Australia"),
    "dewr": ("DEWR", "Department of Employment and Workplace Relations"),
}

CALENDAR_SOURCE = "JSA_website"


def sync_to_unified_calendar(
    releases: list[dict],
    calendar_db_params: dict,
) -> int:
    """Write local publication_calendar entries to the shared unified schema.

    Args:
        releases: list of dicts from publication_calendar table
        calendar_db_params: connection params for the scraping DB
            (pg_host, pg_port, pg_database, pg_user, pg_password)

    Returns:
        Number of rows upserted.
    """
    if not releases:
        return 0

    conn = psycopg.connect(
        host=calendar_db_params.get("pg_host", "localhost"),
        port=calendar_db_params.get("pg_port", 5432),
        dbname=calendar_db_params.get("pg_database", "scraping"),
        user=calendar_db_params.get("pg_user", "postgres"),
        password=calendar_db_params.get("pg_password", ""),
        row_factory=dict_row,
        autocommit=False,
    )

    sql = """
        INSERT INTO statistic_publication_calendar
            (publisher_short_name, publisher_full_name, title, subtitle,
             publication_datetime_utc, publication_frequency,
             reference_period_text, country, geographic_extent,
             release_date_confidence, calendar_source,
             download_timestamp_utc, hyperlink)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """

    count = 0
    try:
        with conn.cursor() as cur:
            for rel in releases:
                dataset = rel["dataset"]
                site = rel.get("site", "jsa")

                pub_meta = DATASET_PUBLICATION_MAP.get(dataset, {})
                publisher_short, publisher_full = PUBLISHER_MAP.get(
                    site, ("JSA", "Jobs and Skills Australia")
                )

                # Build publication_datetime_utc from release_date_parsed
                pub_datetime = None
                if rel.get("release_date_parsed"):
                    parsed = rel["release_date_parsed"]
                    if hasattr(parsed, "date"):
                        pub_datetime = datetime(
                            parsed.year, parsed.month, parsed.day,
                            0, 0, 0, tzinfo=timezone.utc,
                        )
                    else:
                        pub_datetime = datetime(
                            parsed.year, parsed.month, parsed.day,
                            0, 0, 0, tzinfo=timezone.utc,
                        )

                cur.execute(sql, (
                    publisher_short,
                    publisher_full,
                    pub_meta.get("title", dataset),
                    rel.get("data_period", ""),
                    pub_datetime,
                    pub_meta.get("frequency", ""),
                    rel.get("data_period", ""),
                    "AU",
                    "Australia",
                    "published",
                    CALENDAR_SOURCE,
                    datetime.now(timezone.utc),
                    rel.get("source_url", ""),
                ))
                count += 1

            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    logger.info("Synced %d entries to unified publication calendar", count)
    return count
