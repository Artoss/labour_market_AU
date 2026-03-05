-- 015_unified_schema.sql
-- Unified schema: standardize column names across all dataset tables.
-- geo_level -> geo_type, state -> geo_area (projections), add geo_type where missing,
-- recreate total_vacancies_data with unified field names.

-- 1. salm_data: rename geo_level -> geo_type (conditional for existing DBs)
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'salm_data' AND column_name = 'geo_level') THEN
        ALTER TABLE salm_data RENAME COLUMN geo_level TO geo_type;
    END IF;
END $$;

-- Rebuild salm_data constraints/indexes with new name
ALTER TABLE salm_data DROP CONSTRAINT IF EXISTS salm_data_geo_code_geo_level_measure_period_key;
ALTER TABLE salm_data DROP CONSTRAINT IF EXISTS salm_data_geo_code_geo_level_measure_period_smoothed_key;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'salm_data_geo_code_geo_type_measure_period_smoothed_key'
    ) THEN
        ALTER TABLE salm_data ADD CONSTRAINT salm_data_geo_code_geo_type_measure_period_smoothed_key
            UNIQUE (geo_code, geo_type, measure, period, smoothed);
    END IF;
END $$;

DROP INDEX IF EXISTS idx_salm_data_geo;
CREATE INDEX IF NOT EXISTS idx_salm_data_geo ON salm_data(geo_code, geo_type);

-- 2. dim_geography: rename geo_level -> geo_type
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'dim_geography' AND column_name = 'geo_level') THEN
        ALTER TABLE dim_geography RENAME COLUMN geo_level TO geo_type;
    END IF;
END $$;

-- Rebuild dim_geography constraint/index
ALTER TABLE dim_geography DROP CONSTRAINT IF EXISTS dim_geography_geo_code_geo_level_key;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'dim_geography_geo_code_geo_type_key'
    ) THEN
        ALTER TABLE dim_geography ADD CONSTRAINT dim_geography_geo_code_geo_type_key
            UNIQUE (geo_code, geo_type);
    END IF;
END $$;

DROP INDEX IF EXISTS idx_dim_geography_level;
CREATE INDEX IF NOT EXISTS idx_dim_geography_level ON dim_geography(geo_type);

-- 3. ivi_data: add geo_type column
ALTER TABLE ivi_data ADD COLUMN IF NOT EXISTS geo_type TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_ivi_data_geo_type ON ivi_data(geo_type);

-- 4. projections_data: rename state -> geo_area, add geo_type
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'projections_data' AND column_name = 'state') THEN
        ALTER TABLE projections_data RENAME COLUMN state TO geo_area;
    END IF;
END $$;

ALTER TABLE projections_data ADD COLUMN IF NOT EXISTS geo_type TEXT NOT NULL DEFAULT '';

-- Rebuild unique constraint with geo_area
ALTER TABLE projections_data DROP CONSTRAINT IF EXISTS projections_data_unique_key;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'projections_data_unique_key'
    ) THEN
        ALTER TABLE projections_data ADD CONSTRAINT projections_data_unique_key
            UNIQUE (dimension_type, anzsco_code, industry_code, geo_area, measure, base_year, projection_year);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_projections_geo_type ON projections_data(geo_type);

-- 5. total_vacancies_data: DROP and RECREATE with unified field names
DROP TABLE IF EXISTS total_vacancies_data CASCADE;

CREATE TABLE total_vacancies_data (
    id              SERIAL PRIMARY KEY,
    dimension_type  TEXT NOT NULL,
    level           INTEGER NOT NULL,
    anzsco_code     TEXT NOT NULL DEFAULT '',
    anzsco_title    TEXT NOT NULL DEFAULT '',
    geo_type        TEXT NOT NULL DEFAULT '',
    geo_area        TEXT NOT NULL DEFAULT '',
    parent_geo      TEXT NOT NULL DEFAULT '',
    period          TEXT NOT NULL,
    value           DOUBLE PRECISION,
    scrape_run_id   INTEGER REFERENCES scrape_runs(id),
    loaded_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_total_vacancies_key
    ON total_vacancies_data (dimension_type, anzsco_code, geo_area, geo_type, parent_geo, period);
