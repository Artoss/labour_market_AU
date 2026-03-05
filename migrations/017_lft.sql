-- Labour Force Trending (LFT) data table
CREATE TABLE IF NOT EXISTS lft_data (
    id              SERIAL PRIMARY KEY,
    file_type       TEXT NOT NULL,
    level           INTEGER NOT NULL,
    code            TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    geo_area        TEXT NOT NULL DEFAULT '',
    geo_type        TEXT NOT NULL DEFAULT '',
    parent_code     TEXT NOT NULL DEFAULT '',
    period          TEXT NOT NULL,
    value           DOUBLE PRECISION,
    scrape_run_id   INTEGER REFERENCES scrape_runs(id),
    loaded_at       TIMESTAMPTZ DEFAULT NOW()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_lft_key') THEN
        CREATE UNIQUE INDEX uq_lft_key ON lft_data (file_type, code, geo_area, period);
    END IF;
END $$;
