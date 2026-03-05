# Scraper_0062_JobsAndSkills

Australian Labour Market Data Scraper for JSA (Jobs and Skills Australia) and DEWR data.

## Package

- **Package**: `labour_market_au`
- **CLI**: `labour-market-au` (entry point in `main.py:cli`)
- **Database**: `labour_market_au` (PostgreSQL)

## Key Commands

```bash
uv run labour-market-au migrate                              # Apply migrations (17 total)
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
uv run pytest tests/ -v                                      # Run tests (142 passing)
```

## Architecture

- **Catalog-driven**: `scraping/catalog.py` defines all data sources and known files
- **Parser-per-dataset**: Each dataset (SALM, IVI, Projections, TNV, RLMI, LFT) has its own parser in `extraction/`
- **Notes capture**: IVI, TNV, RLMI, and LFT Notes/Contents sheets auto-captured to `dataset_notes` table during load (prose + tables separated)
- **Two-layer change detection**: Page hashing + file hashing
- **Sync httpx**: Government rate limits make async unnecessary
- **Unified schema**: All tables use `geo_type` + `geo_area` for geographic classification (migration 015)

## Datasets

| Dataset | Source | Table | Records | Status |
|---------|--------|-------|---------|--------|
| SALM | DEWR | `salm_data` | 1,062,720 | Loaded |
| IVI | JSA | `ivi_data` | 2,449,383 | Loaded |
| Projections | JSA | `projections_data` | 7,820 | Loaded |
| Total Vacancies | JSA | `total_vacancies_data` | 3,956 | Loaded |
| RLMI | JSA | `rlmi_data` | - | Loaded |
| Labour Force Trending | JSA | `lft_data` | 1,547,136 | Loaded |

## Conventions

- Follow shared conventions in `../CLAUDE.md`
- All modules use `from __future__ import annotations`
- Lazy imports in CLI commands
- psycopg 3 with dict_row, upsert pattern
- Pydantic v2 for config and models
- Migrations must be idempotent (re-run on every command)
