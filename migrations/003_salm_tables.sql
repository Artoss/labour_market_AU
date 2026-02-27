-- 003_salm_tables.sql
-- Small Area Labour Markets data tables

CREATE TABLE IF NOT EXISTS dim_geography (
    id              SERIAL PRIMARY KEY,
    geo_code        TEXT NOT NULL,
    geo_name        TEXT NOT NULL,
    geo_level       TEXT NOT NULL,  -- sa2, lga, sa4, state
    state           TEXT DEFAULT '',
    parent_geo_code TEXT DEFAULT '',
    UNIQUE (geo_code, geo_level)
);

CREATE INDEX IF NOT EXISTS idx_dim_geography_level
    ON dim_geography(geo_level);

CREATE TABLE IF NOT EXISTS salm_data (
    id              SERIAL PRIMARY KEY,
    geo_code        TEXT NOT NULL,
    geo_name        TEXT NOT NULL,
    geo_level       TEXT NOT NULL,
    measure         TEXT NOT NULL,  -- unemployment_rate, unemployed_persons, labour_force
    period          TEXT NOT NULL,  -- e.g. "Jun 2024"
    value           DOUBLE PRECISION,
    smoothed        BOOLEAN DEFAULT TRUE,
    scrape_run_id   INTEGER REFERENCES scrape_runs(id),
    loaded_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (geo_code, geo_level, measure, period)
);

CREATE INDEX IF NOT EXISTS idx_salm_data_geo
    ON salm_data(geo_code, geo_level);
CREATE INDEX IF NOT EXISTS idx_salm_data_period
    ON salm_data(period);
CREATE INDEX IF NOT EXISTS idx_salm_data_measure
    ON salm_data(measure);
