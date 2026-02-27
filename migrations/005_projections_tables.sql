-- 005_projections_tables.sql
-- Employment Projections data tables

CREATE TABLE IF NOT EXISTS projections_data (
    id                  SERIAL PRIMARY KEY,
    anzsco_code         TEXT NOT NULL,
    occupation_name     TEXT DEFAULT '',
    industry_code       TEXT DEFAULT '',
    industry_name       TEXT DEFAULT '',
    state               TEXT DEFAULT '',
    measure             TEXT NOT NULL,  -- employment_level, growth_rate, growth_number
    base_year           INTEGER NOT NULL,
    projection_year     INTEGER NOT NULL,
    value               DOUBLE PRECISION,
    scrape_run_id       INTEGER REFERENCES scrape_runs(id),
    loaded_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (anzsco_code, industry_code, state, measure, base_year, projection_year)
);

CREATE INDEX IF NOT EXISTS idx_projections_anzsco
    ON projections_data(anzsco_code);
CREATE INDEX IF NOT EXISTS idx_projections_measure
    ON projections_data(measure);
