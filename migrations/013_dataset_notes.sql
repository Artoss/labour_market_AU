-- 013: Dataset notes table for capturing Notes sheets and methodology content
CREATE TABLE IF NOT EXISTS dataset_notes (
    id              SERIAL PRIMARY KEY,
    dataset         TEXT NOT NULL,
    file_type       TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    source_ref      TEXT DEFAULT '',
    note_text       TEXT NOT NULL DEFAULT '',
    note_tables     JSONB DEFAULT '[]',
    content_hash    TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dataset_notes_key
    ON dataset_notes (dataset, file_type, source_type);
