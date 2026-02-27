-- 002_page_monitoring.sql
-- HTML change detection for data source pages

CREATE TABLE IF NOT EXISTS monitored_pages (
    id                  SERIAL PRIMARY KEY,
    page_url            TEXT NOT NULL UNIQUE,
    site                TEXT NOT NULL,
    dataset             TEXT NOT NULL,
    content_hash        TEXT,
    last_checked_at     TIMESTAMPTZ,
    last_changed_at     TIMESTAMPTZ,
    last_updated_label  TEXT,
    next_release_label  TEXT,
    download_links      JSONB DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS page_check_log (
    id                  SERIAL PRIMARY KEY,
    page_url            TEXT NOT NULL,
    checked_at          TIMESTAMPTZ DEFAULT NOW(),
    content_hash        TEXT,
    changed             BOOLEAN DEFAULT FALSE,
    download_links_found INTEGER DEFAULT 0,
    error               TEXT
);

CREATE INDEX IF NOT EXISTS idx_page_check_log_url
    ON page_check_log(page_url);
