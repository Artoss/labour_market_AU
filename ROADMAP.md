# Roadmap

## Completed

- [x] Download & load RLMI December 2025 release (new file at `2026-03/Labour Market Ratings by SA4.xlsx`)
- [x] Create `publication_calendar` table (migration 018) and populate with scraped future release dates
- [x] Download & load IVI February 2026 data (6 files, 2,463,120 records, run #22, 18 March 2026)
- [x] Integrate publication_calendar into the monitor command (extract_future_releases in page_monitor.py)
- [x] Prefect automation: `prefect_flow.py` with daily flow (refresh calendar, check due releases, auto-load)
- [x] Slack notifications: `notify.py` (success/failure/release detection, no-op without SLACK_WEBHOOK_URL)
- [x] Migration 019: `processed_at` + `scrape_run_id` tracking columns on publication_calendar
- [x] CLI `automate` command with `--serve` flag for Prefect scheduler
- [x] Cross-project calendar groundwork: `calendar_sync.py` + `DATASET_PUBLICATION_MAP` in catalog.py
- [x] **Switch HTTP client to curl_cffi with chrome120 TLS impersonation** (2026-04-26): JSA + DEWR are behind Akamai, which blackholes the stock python-httpx JA3 fingerprint after a few requests (manifests as `RemoteProtocolError "Server disconnected"` then `ReadTimeout` for ~hours). `DownloadClient` in `scraping/client.py` now uses `curl_cffi.requests.Session(impersonate='chrome120')` — handshake bytes match real Chrome and the WAF passes us. Added `Accept-Encoding: gzip, deflate, br`, `Sec-Fetch-*`, `Upgrade-Insecure-Requests` to `config.yaml` headers as defence-in-depth. Same pattern as Scraper_0042 / Scraper_0064.
- [x] **URL-decode + space-normalise filenames in `_infer_parser_key`** (2026-04-26): JSA serves the SA4 ratings file as `Labour%20Market%20Ratings%20by%20SA4.xlsx`; previous logic missed the prefix `labour_market_ratings` because of the URL encoding. `main.py:_infer_parser_key` now `urllib.parse.unquote(filename).lower().replace(" ", "_")` before prefix matching.
- [x] **Download & load IVI March 2026 data** (run #23, 2026-04-26, 7,428,240 records across Jan/Feb/Mar 2026 × 6 file types — Jan/Feb were re-upserted to no-op since data already loaded; Mar added 13,737 new period rows).
- [x] **Download & load LFT February 2026 data** (run #24, 2026-04-26, 3,104,064 records across Feb 2026 + Nov 2025 × 4 file types).
- [x] **Refresh RLMI SA4 ratings file** (run #25, 2026-04-26 — new SA4 file at `2026-03/Labour%20Market%20Ratings%20by%20SA4.xlsx`, 5,906 records upserted into existing 5,808 SA4×period rows).
- [x] **Refresh publication calendar** (2026-04-26): now 8 entries — IVI Feb→Jun 2026, RLMI Mar+Jun 2026, SALM Dec quarter 2025.

## Next Actions

### 1. Reload Total Vacancies (TNV) data
- **Priority**: High
- `total_vacancies_data` table is empty (data lost, likely during unified schema migration 015)
- File exists: `downloads/jsa/total_vacancies/tnv_data_-_november_2025.xlsx`
- Run: `uv run labour-market-au load -d total_vacancies`
- TNV page hash on JSA was unchanged in the 2026-04-26 monitor run, so no newer file is currently published (Nov 2025 quarter still latest).

### 2. Download & load SALM December quarter 2025
- **Priority**: High
- **When**: Expected March 2026 (exact date TBD)
- SALM downloads use intermediate DEWR resource pages, not direct links on the main page
- DEWR download URLs change each quarter; catalog entries will need updating
- Current catalog has September quarter 2025 URLs

### 3. Auto-discovery now adequate for IVI / RLMI / LFT — KNOWN_FILES update no longer required
- **Priority**: Low / done-by-design
- Pre-2026-04-26 plan was to bump IVI catalog URLs each month and add RLMI/LFT entries to `KNOWN_FILES`. The combination of `monitor` (page parse → `discovered_files`) + `_infer_parser_key` + URL-decode fix now gives the `download` and `automate` commands a complete file list without per-month catalog edits.
- Operator workflow: run `monitor` first whenever a new release is expected, then `download -d <ds>` / `load -d <ds>` (or `automate` to do both via the calendar).
- KNOWN_FILES entries that lag the live page (e.g. the January 2026 IVI URLs) are harmless — they coexist with discovered files and `get_files()` merges both lists.

### 5. Configure Prefect deployment for production
- **Priority**: Medium
- Set `PREFECT_API_URL` for remote Prefect server (or use local ephemeral mode)
- Set `SLACK_WEBHOOK_URL` for pipeline notifications
- Consider `docker-compose.dokploy.yml` following Scraper_0069 pattern
- Optional: configure `calendar_database` in config.yaml for cross-project calendar sync

### 6. Display upcoming releases in `status` command
- **Priority**: Medium
- Query `publication_calendar` table for upcoming releases
- Show next release date per dataset in `status` output

### 7. Clean up leftover .tmp files
- **Priority**: Low
- Multiple `.tmp` files in `src/` and root from previous editing sessions (ROADMAP.md.tmp, pyproject.toml.tmp, ivi_parser.py.tmp, catalog.py.tmp, loader.py.tmp, main.py.tmp, prefect_flow.py.tmp, calendar_sync.py.tmp, test_ivi_parser.py.tmp)
- Safe to delete: `git status` shows them as untracked

### 8. Mitigate the per-task migration 009 cost
- **Priority**: Medium
- Each Prefect task in `prefect_flow.py` calls `db.ensure_schema("migrations")`, which re-runs migration 009 (`ivi_add_file_type`) every time. Now that the IVI table has 2.47M rows, the no-op `ALTER TABLE ... ADD COLUMN IF NOT EXISTS file_type ... NOT NULL DEFAULT '' ...` rewrite-equivalent costs 7-10 minutes per call. A single `automate` invocation hits ensure_schema 3+ times, so most of the wall-clock is spent re-running idempotent migrations.
- Options: (a) early-exit in `Database.ensure_schema()` when migration log already shows all files applied (cache the answer per Database instance); (b) add a sentinel table that `ensure_schema` checks first; (c) move the slow ALTER into a separate migration that drops the rewrite trigger; (d) only `ensure_schema()` once per CLI invocation rather than once per task.
- Same fix would also speed up incidental `download`/`load` commands.

### 9. Mark all due releases as processed, not just the first
- **Priority**: Low
- `prefect_flow.py:jsa_monitor_flow` only calls `mark_release_processed(ds, data_period, ...)` for the first release per dataset; subsequent due releases for the same dataset (e.g. IVI Mar 2026 when Feb 2026 is also due) get skipped via `processed_datasets.add(ds)` but never marked in `publication_calendar`, so they keep reappearing as "due" in future runs.
- Fix: after a successful `task_monitor_and_load(ds)`, mark every due release for `ds` whose `data_period` is <= the latest period observed in the loaded files. Or simpler: mark all due releases for `ds` as processed since `monitor_and_load` loads everything in `data/<site>/<ds>/` regardless of period.
