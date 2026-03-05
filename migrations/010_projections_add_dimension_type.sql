-- 010_projections_add_dimension_type.sql
-- Add dimension_type to projections_data for distinguishing table sources
-- Works whether column is called state (pre-015) or geo_area (post-015)

ALTER TABLE projections_data ADD COLUMN IF NOT EXISTS dimension_type TEXT DEFAULT '';

ALTER TABLE projections_data
    DROP CONSTRAINT IF EXISTS projections_data_anzsco_code_industry_code_state_measure_ba_key;
ALTER TABLE projections_data
    DROP CONSTRAINT IF EXISTS projections_data_anzsco_code_industry_code_geo_area_measure_key;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'projections_data_unique_key'
    ) THEN
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'projections_data' AND column_name = 'geo_area') THEN
            ALTER TABLE projections_data
                ADD CONSTRAINT projections_data_unique_key
                UNIQUE (dimension_type, anzsco_code, industry_code, geo_area, measure, base_year, projection_year);
        ELSE
            ALTER TABLE projections_data
                ADD CONSTRAINT projections_data_unique_key
                UNIQUE (dimension_type, anzsco_code, industry_code, state, measure, base_year, projection_year);
        END IF;
    END IF;
END $$;
