-- Migration 019: Add tracking columns to publication_calendar
-- Tracks when a release was actioned and links to the scrape run

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'publication_calendar' AND column_name = 'processed_at'
    ) THEN
        ALTER TABLE publication_calendar ADD COLUMN processed_at TIMESTAMPTZ;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'publication_calendar' AND column_name = 'scrape_run_id'
    ) THEN
        ALTER TABLE publication_calendar ADD COLUMN scrape_run_id INTEGER REFERENCES scrape_runs(id);
    END IF;
END $$;
