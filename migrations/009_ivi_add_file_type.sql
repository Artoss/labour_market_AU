-- 009: Add file_type column to ivi_data to track source file type
ALTER TABLE ivi_data ADD COLUMN IF NOT EXISTS file_type TEXT DEFAULT '';

-- Backfill existing records based on structural patterns
UPDATE ivi_data SET file_type = 'anzsco4_state' WHERE index_type = 'three_month_average';
UPDATE ivi_data SET file_type = 'skill_level_state' WHERE anzsco_code = '' AND skill_level != '';
UPDATE ivi_data SET file_type = 'anzsco2_state' WHERE file_type = '' AND anzsco_code != '';
