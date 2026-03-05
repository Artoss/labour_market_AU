-- 005_projections_tables.sql
-- Employment Projections data tables

-- For fresh DBs, creates with final column name (geo_area).
-- For existing DBs, CREATE TABLE IF NOT EXISTS is a no-op;
-- migration 015 handles the rename state -> geo_area.

CREATE TABLE IF NOT EXISTS projections_data (
    id                  SERIAL PRIMARY KEY,
    anzsco_code         TEXT NOT NULL,
    occupation_name     TEXT DEFAULT '',
    industry_code       TEXT DEFAULT '',
    industry_name       TEXT DEFAULT '',
    geo_area            TEXT DEFAULT '',
    measure             TEXT NOT NULL,  -- employment_level, growth_rate, growth_number
    base_year           INTEGER NOT NULL,
    projection_year     INTEGER NOT NULL,
    value               DOUBLE PRECISION,
    scrape_run_id       INTEGER REFERENCES scrape_runs(id),
    loaded_at           TIMESTAMPTZ DEFAULT NOW()
);

-- Unique constraint: skip if migration 010's variant already exists
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname IN (
                       'projections_data_anzsco_code_industry_code_geo_area_measure_key',
                       'projections_data_anzsco_code_industry_code_state_measure_ba_key',
                       'projections_data_unique_key'
                   ))
    THEN
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'projections_data' AND column_name = 'geo_area') THEN
            ALTER TABLE projections_data ADD CONSTRAINT projections_data_anzsco_code_industry_code_geo_area_measure_key
                UNIQUE (anzsco_code, industry_code, geo_area, measure, base_year, projection_year);
        ELSE
            ALTER TABLE projections_data ADD CONSTRAINT projections_data_anzsco_code_industry_code_state_measure_ba_key
                UNIQUE (anzsco_code, industry_code, state, measure, base_year, projection_year);
        END IF;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_projections_anzsco
    ON projections_data(anzsco_code);
CREATE INDEX IF NOT EXISTS idx_projections_measure
    ON projections_data(measure);
