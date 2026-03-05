-- Add smoothed to the unique constraint so smoothed and unsmoothed records coexist
-- Works whether column is called geo_level (pre-015) or geo_type (post-015)

ALTER TABLE salm_data DROP CONSTRAINT IF EXISTS salm_data_geo_code_geo_level_measure_period_key;
ALTER TABLE salm_data DROP CONSTRAINT IF EXISTS salm_data_geo_code_geo_type_measure_period_key;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'salm_data' AND column_name = 'geo_type') THEN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint
                       WHERE conname = 'salm_data_geo_code_geo_type_measure_period_smoothed_key') THEN
            ALTER TABLE salm_data ADD CONSTRAINT salm_data_geo_code_geo_type_measure_period_smoothed_key
                UNIQUE (geo_code, geo_type, measure, period, smoothed);
        END IF;
        ALTER TABLE salm_data DROP CONSTRAINT IF EXISTS salm_data_geo_code_geo_level_measure_period_smoothed_key;
    ELSE
        IF NOT EXISTS (SELECT 1 FROM pg_constraint
                       WHERE conname = 'salm_data_geo_code_geo_level_measure_period_smoothed_key') THEN
            ALTER TABLE salm_data ADD CONSTRAINT salm_data_geo_code_geo_level_measure_period_smoothed_key
                UNIQUE (geo_code, geo_level, measure, period, smoothed);
        END IF;
    END IF;
END
$$;
