# Scraper_0062_JobsAndSkills

Australian Labour Market Data Scraper for JSA (Jobs and Skills Australia) and DEWR data.

## Package

- **Package**: `labour_market_au`
- **CLI**: `labour-market-au` (entry point in `main.py:cli`)
- **Database**: `labour_market_au` (PostgreSQL)

## Key Commands

```bash
uv run labour-market-au migrate          # Apply migrations
uv run labour-market-au monitor          # Check pages for changes
uv run labour-market-au download -d salm # Download SALM files
uv run labour-market-au load -d salm     # Parse and load to DB
uv run labour-market-au run              # Full pipeline
uv run labour-market-au status           # Show stats
uv run labour-market-au list             # List catalog sources
```

## Architecture

- **Catalog-driven**: `scraping/catalog.py` defines all data sources and known files
- **Parser-per-dataset**: Each dataset (SALM, IVI, Projections) has its own parser in `extraction/`
- **Two-layer change detection**: Page hashing + file hashing
- **Sync httpx**: Government rate limits make async unnecessary

## Datasets

| Dataset | Source | Status |
|---------|--------|--------|
| SALM | DEWR | Implemented |
| IVI | JSA | Stub (Phase 2) |
| Projections | JSA | Stub (Phase 3) |
| Total Vacancies | JSA | Stub (Phase 3) |

## Conventions

- Follow shared conventions in `../CLAUDE.md`
- All modules use `from __future__ import annotations`
- Lazy imports in CLI commands
- psycopg 3 with dict_row, upsert pattern
- Pydantic v2 for config and models
