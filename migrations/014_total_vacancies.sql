-- Total New Vacancies (TNV) dataset table
-- For fresh DBs, creates with final column names.
-- Migration 015 DROP+RECREATE handles the transition for existing DBs.

CREATE TABLE IF NOT EXISTS total_vacancies_data (
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

-- Index: only create if it doesn't exist (015 may have already created it)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_total_vacancies_key') THEN
        CREATE UNIQUE INDEX uq_total_vacancies_key
            ON total_vacancies_data (dimension_type, anzsco_code, geo_area, geo_type, parent_geo, period);
    END IF;
END $$;
