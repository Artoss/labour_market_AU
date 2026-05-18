# Scraper_0062_JobsAndSkills

Australian Labour Market Data Scraper for JSA (Jobs and Skills Australia) and DEWR data.

## Package

- **Package**: `labour_market_au`
- **CLI**: `labour-market-au` (entry point in `main.py:cli`)
- **Database**: `labour_market_au` (PostgreSQL)

## Key Commands

```bash
uv run labour-market-au migrate                              # Apply migrations (19 total)
uv run labour-market-au monitor                              # Check pages for changes
uv run labour-market-au download -d salm                     # Download SALM files
uv run labour-market-au download -d projections              # Download projections file
uv run labour-market-au load -d salm                         # Parse and load to DB
uv run labour-market-au load -d ivi                          # Parse and load IVI (+ captures Notes)
uv run labour-market-au load -d projections                  # Parse and load projections
uv run labour-market-au load -d total_vacancies              # Parse and load TNV (+ captures Notes)
uv run labour-market-au load -d rlmi                         # Parse and load RLMI (+ captures Notes)
uv run labour-market-au load -d labour_force_trending        # Parse and load LFT (+ captures Notes)
uv run labour-market-au run                                  # Full pipeline
uv run labour-market-au status                               # Show stats
uv run labour-market-au list                                 # List catalog sources
uv run labour-market-au automate                              # One-shot: refresh calendar + auto-load due releases
uv run labour-market-au automate --serve                      # Start Prefect scheduler (daily 8am AEST)
uv run pytest tests/ -v                                      # Run tests (142 passing)
```

## Architecture

- **Catalog-driven**: `scraping/catalog.py` defines all data sources and known files
- **Parser-per-dataset**: Each dataset (SALM, IVI, Projections, TNV, RLMI, LFT) has its own parser in `extraction/`
- **Notes capture**: IVI, TNV, RLMI, and LFT Notes/Contents sheets auto-captured to `dataset_notes` table during load (prose + tables separated)
- **Two-layer change detection**: Page hashing + file hashing
- **HTTP client = curl_cffi with `chrome120` TLS impersonation**: JSA/DEWR sit behind Akamai which fingerprints stock httpx (RemoteProtocolError "Server disconnected" on every request once flagged) and ReadTimeouts the `python-httpx/0.x` JA3 entirely. `DownloadClient` in `scraping/client.py` uses `curl_cffi.requests.Session(impersonate='chrome120')` so handshake bytes look like real Chrome. `httpx` is still imported for retry exception types — both `httpx.TransportError` and `curl_cffi.requests.errors.RequestsError` are in the `tenacity` retry guard. `config.yaml` sets browser-like headers (`Accept-Encoding: gzip, deflate, br`, `Sec-Fetch-*`, `Upgrade-Insecure-Requests`) as belt-and-braces.
- **Unified schema**: All tables use `geo_type` + `geo_area` for geographic classification (migration 015)
- **Publication calendar**: `publication_calendar` table tracks upcoming release dates scraped from source pages (migration 018), with tracking columns (migration 019)
- **Prefect automation**: `prefect_flow.py` daily flow refreshes calendar, checks due releases, auto-triggers download+load
- **Slack notifications**: `notify.py` sends pipeline success/failure to Slack (no-op if `SLACK_WEBHOOK_URL` unset)
- **Cross-project calendar**: `storage/calendar_sync.py` can sync to shared `statistic_publication_calendar` schema

## Datasets

| Dataset | Source | Table | Records | Status |
|---------|--------|-------|---------|--------|
| SALM | DEWR | `salm_data` | 1,062,720 | Loaded (Sep quarter 2025) |
| IVI | JSA | `ivi_data` | 2,476,857 | Loaded (Mar 2026) |
| Projections | JSA | `projections_data` | 7,820 | Loaded (May 2025-2035) |
| Total Vacancies | JSA | `total_vacancies_data` | 0 | Needs reload |
| RLMI | JSA | `rlmi_data` | 5,808 | Loaded (Dec 2025; SA4 ratings file refreshed 2026-04-26) |
| Labour Force Trending | JSA | `lft_data` | 1,556,928 | Loaded (Feb 2026) |

## Conventions

- Follow shared conventions in `../CLAUDE.md`
- All modules use `from __future__ import annotations`
- Lazy imports in CLI commands
- psycopg 3 with dict_row, upsert pattern
- Pydantic v2 for config and models
- Migrations must be idempotent (re-run on every command)
