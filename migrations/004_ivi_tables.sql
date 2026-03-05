-- 004_ivi_tables.sql
-- Internet Vacancy Index data tables

CREATE TABLE IF NOT EXISTS dim_anzsco (
    id              SERIAL PRIMARY KEY,
    anzsco_code     TEXT NOT NULL UNIQUE,
    anzsco_title    TEXT DEFAULT '',
    anzsco_level    INTEGER DEFAULT 0,  -- 1=major, 2=sub-major, etc.
    parent_code     TEXT DEFAULT '',
    skill_level     TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ivi_data (
    id              SERIAL PRIMARY KEY,
    anzsco_code     TEXT NOT NULL,
    anzsco_title    TEXT DEFAULT '',
    geo_area        TEXT DEFAULT '',
    skill_level     TEXT DEFAULT '',
    period          TEXT NOT NULL,  -- e.g. "Jan 2024"
    value           DOUBLE PRECISION,
    index_type      TEXT DEFAULT 'level',  -- level, index
    scrape_run_id   INTEGER REFERENCES scrape_runs(id),
    loaded_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (anzsco_code, geo_area, skill_level, period, index_type)
);

CREATE INDEX IF NOT EXISTS idx_ivi_data_anzsco
    ON ivi_data(anzsco_code);
CREATE INDEX IF NOT EXISTS idx_ivi_data_period
    ON ivi_data(period);
CREATE INDEX IF NOT EXISTS idx_ivi_data_geo_area
    ON ivi_data(geo_area);
