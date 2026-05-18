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

## Production deployment (Dokploy / Prefect work pool)

As of 2026-05-18 this scraper runs on the shared Dokploy Prefect work pool
alongside Scraper_0021_SQM_Research. The laptop is no longer in the
production data path — both scraping and warehouse mirroring run on the
VPS regardless of whether the developer machine is on.

### Deployments

Declared in `prefect.yaml` at the repo root. Registered via:

```bash
PREFECT_API_URL=https://prefect.statdesk.com.au/api \
PREFECT_API_AUTH_STRING="admin:3yOh6oefGukVZLceJWsN" \
.venv/Scripts/python.exe -m prefect deploy --all
```

| Deployment | Cron (UTC) | Cron (AEST) | Entrypoint | What it does |
|---|---|---|---|---|
| `labour-daily-monitor` | `0 22 * * *` | 8am | `src/labour_market_au/prefect_flow.py:jsa_monitor_flow` | Refresh publication_calendar from JSA/DEWR; load any dataset due today; quiet exit otherwise |
| `labour-warehouse-mirror` | `0 1 * * *` | 11am | `pipeline_warehouse_mirror.py:mirror` | Full re-mirror of labour_market_au → Supabase `stats_warehouse.observations` (~105k rows, idempotent, ~30-60s) |

Both fire from the shared `prefect-worker` container. The worker's compose
env provides `PGHOST` / `PGPORT` / `PGUSER` / `PGPASSWORD` pointing at the
co-located `scraperportfoliopg` Postgres container; `prefect.yaml`
`job_variables.env` injects `PGDATABASE=labour_market_au` per deployment.

### Data flow

```
JSA / DEWR pages
     │
     │   (curl_cffi chrome120, Akamai bypass — verified working from VPS IP)
     ▼
labour-daily-monitor flow
     │
     │   parse + load
     ▼
labour_market_au DB on scraperportfoliopg (VPS Postgres)
     │
     │   labour-warehouse-mirror flow
     │   (Decimal-safe upsert, source_dataset='jsa_labour',
     │    prepare_threshold=None for Supabase pooler)
     ▼
Supabase stats_warehouse.observations
     │
     │   public.v_observations proxy view
     ▼
statdesk.com.au / Topics ETL / Topic datapack ZIPs
```

### Two-tenant scraperportfoliopg

`scraperportfoliopg` (container name
`prefect-server-scraperportfoliopg-dblay6-postgres-1` as of 2026-05) hosts:

- `sqm_research` — SQM Research scraper's data (~9.6 GB)
- `labour_market_au` — this scraper's data (~3.3 GB after initial migration)

Total ~13 GB on the VPS's 59 GB root FS. Both DBs use `postgres` superuser,
both pulled in via the same worker env-var pattern.

### Initial DB migration to the VPS (one-off, completed 2026-05-18)

```bash
docker exec prefect-server-scraperportfoliopg-dblay6-postgres-1 \
  psql -U postgres -c "CREATE DATABASE labour_market_au WITH OWNER postgres;"

PGPASSWORD=<laptop-pg-password> pg_dump -h localhost -U postgres -d labour_market_au \
  --format=custom --compress=9 --no-owner --no-acl --verbose 2>/tmp/dump.log \
| ssh root@<vps> \
    "docker exec -i prefect-server-scraperportfoliopg-dblay6-postgres-1 \
     pg_restore -U postgres -d labour_market_au --no-owner --no-acl --verbose 2>&1"
```

Runs from the laptop, streams the dump via SSH stdin to `pg_restore` on the
VPS. ~15-30 min for 3.3 GB depending on upload bandwidth.

### Manual run / smoke test

Trigger a flow run without unpausing the schedule:

```bash
PREFECT_API_URL=https://prefect.statdesk.com.au/api \
PREFECT_API_AUTH_STRING="admin:3yOh6oefGukVZLceJWsN" \
.venv/Scripts/python.exe -c "
from prefect.client.orchestration import get_client
from uuid import UUID
import asyncio
async def main():
    async with get_client() as c:
        run = await c.create_flow_run_from_deployment(UUID('<deployment-id>'))
        print(f'Created: {run.id} | name={run.name}')
asyncio.run(main())
"
```

Deployment IDs visible in the Prefect UI (https://prefect.statdesk.com.au)
or via `prefect deployment ls`.

### `pipeline_warehouse_mirror.py` design notes

- **Full re-mirror per fire** (no watermark) — ~105k rows is small enough
  that idempotent upsert in ~30-60s is fine. Add watermarking later if
  data volume grows.
- **Mapping logic ported from `StatDesk_Topics_ETL/sources/jsa_labour.py`**.
  Same metric slugs, same period normalisation. Warehouse rows are
  bit-for-bit identical regardless of which path produced them.
- **`prepare_threshold=None`** on the Supabase connection — Supavisor in
  transaction mode trips on psycopg3's prepared-statement caching.
- **`make_conninfo` keyword form** for Supabase — URI form silently
  truncates dotted usernames (`postgres.<ref>`) on the bundled libpq.
- **`SUPABASE_PG_PASSWORD_B64`** preferred over plain — base64 alphabet
  survives shell quoting; plain passwords with `$` `;` `]` `}` get
  silently mangled. See `Scraper_0021_SQM_Research/docs/operator/
  DOKPLOY_ENV_VAR_MANGLING.md`.
- **Schema guard** refuses to run if `stats_warehouse.observations`
  UNIQUE constraint doesn't include `source_dataset`. That constraint
  ships with StatDeskAU_web migration `warehouse_provenance`.

### Operational caveats picked up during migration

Lessons recorded in `prefect-worker/README.md` § "Onboarding gotchas":

1. `prefect deploy` needs `PREFECT_API_AUTH_STRING` (basic auth) in
   addition to `PREFECT_API_URL`
2. Multi-line bash env-var prefix silently loses the assignments — use
   `export` or single-line
3. Supabase pooler `DuplicatePreparedStatement` → `prepare_threshold=None`
4. Worker only sees committed code — `git status` before deploying
5. PuTTY paste corrupts heredocs / long base64 — use SSH stdin piping
6. PR merge timing — cherry-pick stranded commits to master

### Failure mode

If the laptop is off or the operator is unavailable:
- `labour-daily-monitor` fires anyway, scrapes, loads to VPS PG
- `labour-warehouse-mirror` fires anyway, mirrors to Supabase
- Slack notifications continue to land in the StatsDatabaseAU channel
- Topic datapacks on statdesk.com.au continue to update on the same cron

If the VPS is down:
- Scrape stops; warehouse keeps last-good data
- Frontend keeps serving cached + last-good Supabase rows
- Slack failure notifications signal the outage
- Once VPS returns, next daily fire catches up automatically

### Legacy paths (preserved, currently redundant)

- `python -m labour_market_au.prefect_flow` — runs the flow locally
  against laptop PG. Still works for ad-hoc operator backfills.
- `StatDesk_Topics_ETL/sources/jsa_labour.py` — same mapping logic ported
  into `pipeline_warehouse_mirror.py`. Kept as operator-side fallback.
  Slated for removal after a month of mirror-flow stability.
