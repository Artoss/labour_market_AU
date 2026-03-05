-- 003_salm_tables.sql
-- Small Area Labour Markets data tables

-- For fresh DBs, creates with final column name (geo_type).
-- For existing DBs, CREATE TABLE IF NOT EXISTS is a no-op;
-- migration 015 handles the rename geo_level -> geo_type.

CREATE TABLE IF NOT EXISTS dim_geography (
    id              SERIAL PRIMARY KEY,
    geo_code        TEXT NOT NULL,
    geo_name        TEXT NOT NULL,
    geo_type        TEXT NOT NULL,  -- sa2, lga, sa4, state
    state           TEXT DEFAULT '',
    parent_geo_code TEXT DEFAULT ''
);

-- Unique constraint + index: use whichever column name exists
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname LIKE 'dim_geography_geo_code_geo_%_key')
    THEN
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'dim_geography' AND column_name = 'geo_type') THEN
            ALTER TABLE dim_geography ADD CONSTRAINT dim_geography_geo_code_geo_type_key
                UNIQUE (geo_code, geo_type);
        ELSE
            ALTER TABLE dim_geography ADD CONSTRAINT dim_geography_geo_code_geo_level_key
                UNIQUE (geo_code, geo_level);
        END IF;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_dim_geography_level') THEN
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'dim_geography' AND column_name = 'geo_type') THEN
            CREATE INDEX idx_dim_geography_level ON dim_geography(geo_type);
        ELSE
            CREATE INDEX idx_dim_geography_level ON dim_geography(geo_level);
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS salm_data (
    id              SERIAL PRIMARY KEY,
    geo_code        TEXT NOT NULL,
    geo_name        TEXT NOT NULL,
    geo_type        TEXT NOT NULL,
    measure         TEXT NOT NULL,  -- unemployment_rate, unemployed_persons, labour_force
    period          TEXT NOT NULL,  -- e.g. "Jun 2024"
    value           DOUBLE PRECISION,
    smoothed        BOOLEAN DEFAULT TRUE,
    scrape_run_id   INTEGER REFERENCES scrape_runs(id),
    loaded_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Unique constraint: skip if migration 007's smoothed variant already exists
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname LIKE 'salm_data_geo_code_geo_%_measure_period%')
    THEN
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'salm_data' AND column_name = 'geo_type') THEN
            ALTER TABLE salm_data ADD CONSTRAINT salm_data_geo_code_geo_type_measure_period_key
                UNIQUE (geo_code, geo_type, measure, period);
        ELSE
            ALTER TABLE salm_data ADD CONSTRAINT salm_data_geo_code_geo_level_measure_period_key
                UNIQUE (geo_code, geo_level, measure, period);
        END IF;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_salm_data_geo') THEN
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'salm_data' AND column_name = 'geo_type') THEN
            CREATE INDEX idx_salm_data_geo ON salm_data(geo_code, geo_type);
        ELSE
            CREATE INDEX idx_salm_data_geo ON salm_data(geo_code, geo_level);
        END IF;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_salm_data_period
    ON salm_data(period);
CREATE INDEX IF NOT EXISTS idx_salm_data_measure
    ON salm_data(measure);
