-- Migration 018: Publication calendar table
-- Stores future release/publication dates scraped from data source pages

CREATE TABLE IF NOT EXISTS publication_calendar (
    id              SERIAL PRIMARY KEY,
    dataset         TEXT NOT NULL,
    site            TEXT NOT NULL,
    data_period     TEXT NOT NULL,          -- e.g. "February 2026", "March quarter 2026"
    release_date    TEXT NOT NULL,          -- e.g. "18 March 2026", "May 2026"
    release_date_parsed DATE,              -- parsed date if available
    source_url      TEXT NOT NULL,
    scraped_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (dataset, site, data_period)
);
