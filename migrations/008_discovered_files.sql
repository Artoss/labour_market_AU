-- Discovered files: URLs found by page monitor, available for download.
CREATE TABLE IF NOT EXISTS discovered_files (
    id              SERIAL PRIMARY KEY,
    page_url        TEXT NOT NULL,
    site            TEXT NOT NULL,
    dataset         TEXT NOT NULL,
    url             TEXT NOT NULL UNIQUE,
    filename        TEXT NOT NULL,
    parser_key      TEXT DEFAULT '',
    first_seen_at   TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ DEFAULT NOW(),
    removed_at      TIMESTAMPTZ,
    auto_download   BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_discovered_files_dataset ON discovered_files(dataset);
