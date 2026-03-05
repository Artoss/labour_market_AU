DO $$
BEGIN
    -- Rename column if it still has the old name
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'ivi_data' AND column_name = 'state'
    ) THEN
        ALTER TABLE ivi_data RENAME COLUMN state TO geo_area;
    END IF;

    -- Rebuild unique constraint with new column name
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ivi_data_unique_key') THEN
        ALTER TABLE ivi_data DROP CONSTRAINT ivi_data_unique_key;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ivi_data_unique_geo_area_key') THEN
        ALTER TABLE ivi_data ADD CONSTRAINT ivi_data_unique_geo_area_key
            UNIQUE (anzsco_code, geo_area, skill_level, period, index_type, file_type);
    END IF;

    -- Rebuild index with new name
    DROP INDEX IF EXISTS idx_ivi_data_state;
    CREATE INDEX IF NOT EXISTS idx_ivi_data_geo_area ON ivi_data(geo_area);
END $$;
