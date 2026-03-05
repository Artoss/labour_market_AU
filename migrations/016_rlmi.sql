-- RLMI (Regional Labour Market Indicator) table
CREATE TABLE IF NOT EXISTS rlmi_data (
    id              SERIAL PRIMARY KEY,
    data_source     TEXT NOT NULL,
    sa4_code        TEXT NOT NULL DEFAULT '',
    sa4_name        TEXT NOT NULL DEFAULT '',
    geo_type        TEXT NOT NULL DEFAULT '',
    measure         TEXT NOT NULL,
    period          TEXT NOT NULL,
    value           DOUBLE PRECISION,
    rating_value    INTEGER,
    rating_text     TEXT NOT NULL DEFAULT '',
    scrape_run_id   INTEGER REFERENCES scrape_runs(id),
    loaded_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Unique index (idempotent)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_rlmi_key') THEN
        CREATE UNIQUE INDEX uq_rlmi_key ON rlmi_data (sa4_code, measure, period);
    END IF;
END $$;
