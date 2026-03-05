-- Migration 011: Add file_type to IVI unique constraint
-- Allows distinct geographic variants (state, remoteness, gccsa, region)
-- to coexist in the same table.
DO $$
BEGIN
    -- Ensure no NULLs in file_type before adding to constraint
    UPDATE ivi_data SET file_type = '' WHERE file_type IS NULL;

    -- Drop old constraints that referenced 'state' column
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ivi_data_anzsco_code_state_skill_level_period_index_type_key') THEN
        ALTER TABLE ivi_data DROP CONSTRAINT ivi_data_anzsco_code_state_skill_level_period_index_type_key;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ivi_data_anzsco_code_geo_area_skill_level_period_index_type_key') THEN
        ALTER TABLE ivi_data DROP CONSTRAINT ivi_data_anzsco_code_geo_area_skill_level_period_index_type_key;
    END IF;

    -- Add constraint with file_type (skip if 012 already applied final version)
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ivi_data_unique_key')
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ivi_data_unique_geo_area_key')
    THEN
        ALTER TABLE ivi_data ADD CONSTRAINT ivi_data_unique_key
            UNIQUE (anzsco_code, geo_area, skill_level, period, index_type, file_type);
    END IF;
END $$;
