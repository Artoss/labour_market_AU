-- 001_initial_schema.sql
-- Run tracking and file tracking tables

CREATE TABLE IF NOT EXISTS scrape_runs (
    id              SERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running',
    config_hash     TEXT,
    files_downloaded INTEGER DEFAULT 0,
    records_loaded  INTEGER DEFAULT 0,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS scrape_files (
    id              SERIAL PRIMARY KEY,
    scrape_run_id   INTEGER REFERENCES scrape_runs(id),
    site            TEXT NOT NULL,
    dataset         TEXT NOT NULL,
    filename        TEXT NOT NULL,
    url             TEXT,
    file_hash       TEXT,
    file_size_bytes INTEGER DEFAULT 0,
    downloaded_at   TIMESTAMPTZ DEFAULT NOW(),
    records_loaded  INTEGER DEFAULT 0,
    skipped         BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_scrape_files_filename
    ON scrape_files(filename);
CREATE INDEX IF NOT EXISTS idx_scrape_files_run
    ON scrape_files(scrape_run_id);
