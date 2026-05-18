"""VPS labour_market_au -> Supabase stats_warehouse mirror flow.

Daily 01:00 UTC (11am AEST / 12pm AEDT) — 3 hours after the daily monitor flow
so any late-publishing dataset has finished loading by the time we mirror.

This flow reads from the `labour_market_au` Postgres database (which lives on
the VPS-side `scraperportfoliopg` container alongside SQM Research's data) and
upserts conformed rows into Supabase `stats_warehouse.observations` with
`source_dataset='jsa_labour'`.

Mapping logic ported verbatim from
`StatDesk_Topics_ETL/src/statdesk_topics_etl/sources/jsa_labour.py` so the
warehouse rows are bit-for-bit identical regardless of whether they came
through the laptop-side StatDesk Topics ETL or through this VPS mirror flow.

Design choices vs SQM's mirror:

- **Full re-mirror every fire (not watermarked).** The labour datasets total
  ~109k rows after filtering — small enough that a full upsert in chunked
  executemany takes ~30-60s. Idempotent on the `(source_dataset, topic, metric,
  geo_type, geo_code, period)` unique key, so re-running just refreshes any
  revised values. Watermarking can be added if data volume grows.

- **No source-side aggregation.** Scraper_0062's data is already at the target
  grain — LGA quarterly for SALM, state monthly for IVI, etc. We map column
  names and write through.

- **Reads `scraperportfoliopg` via labour_market_au.config**, which honours
  the worker-injected PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE env
  vars (validated in `tests/test_config.py`).

- **Writes Supabase via `psycopg.conninfo.make_conninfo`** (keyword form), NOT
  URI form. The bundled libpq in `psycopg[binary]` mis-parses dotted usernames
  (e.g. `postgres.<project-ref>`) in URI form and silently strips the tenant
  suffix. Same lesson learned in SQM (PR #?? on that repo).

- **Password from `SUPABASE_PG_PASSWORD_B64`** preferred over plain. Base64
  alphabet (`A-Za-z0-9+/=`) survives every layer of Dokploy env-var storage,
  docker-compose dotenv parsing, and shell quoting unchanged. Plain passwords
  containing `$` / `;` / `]` / `}` get silently corrupted somewhere in the
  chain — multiple incidents in SQM.

Entrypoint declared in `prefect.yaml` as `pipeline_warehouse_mirror.py:mirror`.
"""
from __future__ import annotations

import base64
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

import psycopg
from dotenv import load_dotenv
from prefect import flow
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

load_dotenv()

from labour_market_au.config import load_config  # noqa: E402
from labour_market_au.notify import notify_pipeline_failure, send_slack  # noqa: E402
from labour_market_au.storage.database import Database  # noqa: E402

log = logging.getLogger("labour_market_au.pipeline_warehouse_mirror")

SOURCE_DATASET = "jsa_labour"
TOPIC = "labour"
UPSERT_CHUNK_SIZE = 5000


# =============================================================================
# Mapping constants (ported from StatDesk_Topics_ETL/sources/jsa_labour.py)
# =============================================================================

# Mon-YYYY period -> YYYY-Qn / YYYY-MM
_MON_TO_NUM: dict[str, int] = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
_QUARTER_END: dict[int, int] = {3: 1, 6: 2, 9: 3, 12: 4}


def _mon_yyyy_to_quarter(period_text: str) -> str | None:
    """'Sep 2025' -> '2025-Q3'. Returns None for non-quarter-end months."""
    parts = period_text.strip().split()
    if len(parts) != 2:
        return None
    mon, year = parts
    month = _MON_TO_NUM.get(mon[:3])
    quarter = _QUARTER_END.get(month) if month else None
    if quarter is None or not year.isdigit():
        return None
    return f"{year}-Q{quarter}"


def _mon_yyyy_to_month(period_text: str) -> str | None:
    """'Jun 2024' -> '2024-06'. Returns None for unrecognised input."""
    parts = period_text.strip().split()
    if len(parts) != 2:
        return None
    mon, year = parts
    month = _MON_TO_NUM.get(mon[:3])
    if month is None or not year.isdigit():
        return None
    return f"{year}-{month:02d}"


_STATE_LOOKUP: dict[str, tuple[str, str, str]] = {
    "AUST": ("AUS", "australia", "Australia"),
    "AUS":  ("AUS", "australia", "Australia"),
    "NSW":  ("NSW", "state", "New South Wales"),
    "VIC":  ("VIC", "state", "Victoria"),
    "QLD":  ("QLD", "state", "Queensland"),
    "SA":   ("SA",  "state", "South Australia"),
    "WA":   ("WA",  "state", "Western Australia"),
    "TAS":  ("TAS", "state", "Tasmania"),
    "NT":   ("NT",  "state", "Northern Territory"),
    "ACT":  ("ACT", "state", "Australian Capital Territory"),
}

_SALM_METRICS: dict[str, tuple[str, str]] = {
    "unemployment_rate":  ("labour_salm_unemployment_rate",  "percent"),
    "unemployed_persons": ("labour_salm_unemployed_persons", "persons"),
    "labour_force":       ("labour_salm_labour_force",       "persons"),
}

_IVI_MAJOR_METRICS: dict[str, str] = {
    "1": "labour_vac_managers",
    "2": "labour_vac_professionals",
    "3": "labour_vac_technicians_trades",
    "4": "labour_vac_community_personal",
    "5": "labour_vac_clerical_admin",
    "6": "labour_vac_sales",
    "7": "labour_vac_machinery_drivers",
    "8": "labour_vac_labourers",
}

_PROJ_MEASURES: dict[str, tuple[str, str]] = {
    "employment_level":  ("labour_proj_employment_level", "persons_thousands"),
    "growth_rate_5yr":   ("labour_proj_growth_rate_5yr",  "percent"),
    "growth_rate_10yr":  ("labour_proj_growth_rate_10yr", "percent"),
    "employment_share":  ("labour_proj_employment_share", "share"),
}

_RLMI_MEASURES: dict[str, tuple[str, str]] = {
    "unemployment_rate":           ("labour_rlmi_unemployment_rate",   "percent"),
    "underemployment_rate":        ("labour_rlmi_underemployment_rate","percent"),
    "job_vacancy_rate":            ("labour_rlmi_job_vacancy_rate",    "percent"),
    "skill_underutilisation_rate": ("labour_rlmi_skill_underutil",     "percent"),
    "working_age_employment_rate": ("labour_rlmi_wae_rate",            "percent"),
    "overall_rating":              ("labour_rlmi_overall_rating",      "rating"),
}


def _period_to_date_str(period: str) -> str | None:
    """Map a YYYY-Qn / YYYY-MM / YYYY period to its end-of-period ISO date.

    Returns None for unrecognised input. Inlined here (not imported from
    statdesk_topics_etl) so this flow has no cross-repo runtime dependency.
    """
    import calendar
    s = period.strip()
    if len(s) == 4 and s.isdigit():
        return f"{s}-06-30"
    if len(s) == 7 and s[4] == "-":
        if s[5] == "Q":
            try:
                year, q = int(s[:4]), int(s[6])
                month = q * 3
                day = calendar.monthrange(year, month)[1]
                return f"{year:04d}-{month:02d}-{day:02d}"
            except (ValueError, IndexError):
                return None
        if s[5:].isdigit():
            try:
                year, month = int(s[:4]), int(s[5:])
                day = calendar.monthrange(year, month)[1]
                return f"{year:04d}-{month:02d}-{day:02d}"
            except ValueError:
                return None
    return None


def _to_decimal(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (ValueError, TypeError, ArithmeticError):
        return None


# =============================================================================
# Supabase connection helpers
# =============================================================================

def _supabase_password() -> str:
    """Prefer SUPABASE_PG_PASSWORD_B64 over plain to dodge shell mangling.

    The shared portfolio password contains shell-special characters
    (`$`, `;`, `]`, `}`) which get silently corrupted by Dokploy / docker-compose
    /bash quoting. Base64 alphabet survives unchanged.
    """
    b64 = os.environ.get("SUPABASE_PG_PASSWORD_B64", "")
    if b64:
        try:
            return base64.b64decode(b64.encode("ascii")).decode("utf-8")
        except Exception as exc:
            raise RuntimeError(
                "SUPABASE_PG_PASSWORD_B64 set but failed to decode. "
                "Re-encode with: echo -n '<password>' | base64"
            ) from exc
    plain = os.environ.get("SUPABASE_PG_PASSWORD", "")
    if not plain:
        raise RuntimeError(
            "Neither SUPABASE_PG_PASSWORD_B64 nor SUPABASE_PG_PASSWORD is set."
        )
    return plain


def _supabase_conninfo() -> str:
    """Build a libpq keyword conninfo for Supabase. NEVER use URI form."""
    return make_conninfo(
        host=os.environ["SUPABASE_PG_HOST"],
        port=int(os.environ.get("SUPABASE_PG_PORT", "6543")),
        dbname=os.environ.get("SUPABASE_PG_DATABASE", "postgres"),
        user=os.environ["SUPABASE_PG_USER"],
        password=_supabase_password(),
        sslmode="require",
    )


def _open_supabase() -> psycopg.Connection:
    return psycopg.connect(_supabase_conninfo(), row_factory=dict_row, autocommit=False)


def _assert_warehouse_unique_includes_source_dataset(sb: psycopg.Connection) -> None:
    """Refuse to run if the cross-repo Supabase provenance migration is missing.

    `stats_warehouse.observations` originally had a UNIQUE on (topic, metric,
    geo_type, geo_code, period). The warehouse_provenance migration added
    `source_dataset` to that constraint so multiple scrapers can contribute
    rows for the same (topic, metric, geo) without colliding. If that
    migration hasn't been applied we'd get false conflicts on every upsert.
    """
    with sb.cursor() as cur:
        cur.execute(
            """
            SELECT a.attname
            FROM   pg_constraint c
            JOIN   pg_attribute  a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
            JOIN   pg_class      t ON t.oid = c.conrelid
            JOIN   pg_namespace  n ON n.oid = t.relnamespace
            WHERE  n.nspname = 'stats_warehouse'
              AND  t.relname = 'observations'
              AND  c.contype = 'u'
            """
        )
        cols = {r["attname"] for r in cur.fetchall()}
    if "source_dataset" not in cols:
        raise RuntimeError(
            "stats_warehouse.observations UNIQUE constraint does not include "
            "source_dataset. Apply the warehouse_provenance migration in "
            "StatDeskAU_web_prod before running this mirror."
        )


# =============================================================================
# Extract + map from labour_market_au
# =============================================================================

def _fetch_salm_lga(db: Database) -> list[dict[str, Any]]:
    """3 measures × ~550 LGAs × ~63 quarters (smoothed) = ~100k rows."""
    sql = """
        SELECT geo_code, geo_name, measure, period, value
        FROM   salm_data
        WHERE  geo_type = 'lga'
          AND  smoothed = TRUE
          AND  measure IN ('unemployment_rate', 'unemployed_persons', 'labour_force')
          AND  value IS NOT NULL
    """
    db.connect_if_needed() if hasattr(db, "connect_if_needed") else None
    with db.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        metric_info = _SALM_METRICS.get(r["measure"])
        if metric_info is None:
            continue
        metric, unit = metric_info
        quarter = _mon_yyyy_to_quarter(r["period"])
        if quarter is None:
            continue
        period_date = _period_to_date_str(quarter)
        if period_date is None:
            continue
        out.append({
            "source_dataset": SOURCE_DATASET,
            "topic": TOPIC,
            "metric": metric,
            "geo_type": "lga",
            "geo_code": str(r["geo_code"]),
            "geo_name": str(r["geo_name"]),
            "period": quarter,
            "period_date": period_date,
            "value": _to_decimal(r["value"]),
            "unit": unit,
        })
    return out


def _fetch_ivi_state_majors(db: Database) -> list[dict[str, Any]]:
    """8 ANZSCO majors × 9 geos × ~243 months (seasonally adjusted) = ~17k rows."""
    sql = """
        SELECT anzsco_code, geo_area, period, value
        FROM   ivi_data
        WHERE  LENGTH(anzsco_code) = 1
          AND  anzsco_code IN ('1','2','3','4','5','6','7','8')
          AND  geo_area IN ('AUST','NSW','VIC','QLD','SA','WA','TAS','NT','ACT')
          AND  index_type = 'seasonally_adjusted'
          AND  value IS NOT NULL
    """
    with db.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        metric = _IVI_MAJOR_METRICS.get(str(r["anzsco_code"]))
        geo_info = _STATE_LOOKUP.get(str(r["geo_area"]))
        if metric is None or geo_info is None:
            continue
        geo_code, geo_type, geo_name = geo_info
        month = _mon_yyyy_to_month(r["period"])
        if month is None:
            continue
        period_date = _period_to_date_str(month)
        if period_date is None:
            continue
        out.append({
            "source_dataset": SOURCE_DATASET,
            "topic": TOPIC,
            "metric": metric,
            "geo_type": geo_type,
            "geo_code": geo_code,
            "geo_name": geo_name,
            "period": month,
            "period_date": period_date,
            "value": _to_decimal(r["value"]),
            "unit": "vacancies",
        })
    return out


def _fetch_projections_state(db: Database) -> list[dict[str, Any]]:
    """4 measures × 8 states × 3 horizons = ~80 rows."""
    sql = """
        SELECT geo_area, measure, base_year, projection_year, value
        FROM   projections_data
        WHERE  dimension_type = 'state_territory'
          AND  value IS NOT NULL
    """
    with db.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        metric_info = _PROJ_MEASURES.get(r["measure"])
        geo_info = _STATE_LOOKUP.get(str(r["geo_area"]))
        if metric_info is None or geo_info is None:
            continue
        metric, unit = metric_info
        geo_code, geo_type, geo_name = geo_info
        period = str(r["projection_year"])
        period_date = _period_to_date_str(period)
        if period_date is None:
            continue
        out.append({
            "source_dataset": SOURCE_DATASET,
            "topic": TOPIC,
            "metric": metric,
            "geo_type": geo_type,
            "geo_code": geo_code,
            "geo_name": geo_name,
            "period": period,
            "period_date": period_date,
            "value": _to_decimal(r["value"]),
            "unit": unit,
        })
    return out


def _fetch_rlmi_sa4(db: Database) -> list[dict[str, Any]]:
    """6 measures × 88 SA4s × varying periods = ~5k rows."""
    sql = """
        SELECT data_source, sa4_code, sa4_name, measure, period, value, rating_value
        FROM   rlmi_data
        WHERE  measure IN (
            'unemployment_rate', 'underemployment_rate', 'job_vacancy_rate',
            'skill_underutilisation_rate', 'working_age_employment_rate',
            'overall_rating'
        )
    """
    with db.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        metric_info = _RLMI_MEASURES.get(r["measure"])
        if metric_info is None:
            continue
        metric, unit = metric_info
        # RLMI mixes monthly + quarterly cadences; try monthly first.
        period = _mon_yyyy_to_month(r["period"]) or _mon_yyyy_to_quarter(r["period"])
        if period is None:
            continue
        period_date = _period_to_date_str(period)
        if period_date is None:
            continue
        raw = r["value"]
        if raw is None and r.get("rating_value") is not None:
            raw = r["rating_value"]
        if raw is None:
            continue
        out.append({
            "source_dataset": SOURCE_DATASET,
            "topic": TOPIC,
            "metric": metric,
            "geo_type": "sa4",
            "geo_code": str(r["sa4_code"]),
            "geo_name": str(r["sa4_name"]),
            "period": period,
            "period_date": period_date,
            "value": _to_decimal(raw),
            "unit": unit,
        })
    return out


# =============================================================================
# Load into Supabase
# =============================================================================

UPSERT_SQL = """
INSERT INTO stats_warehouse.observations
    (source_dataset, topic, metric, geo_type, geo_code, geo_name,
     period, period_date, value, unit, loaded_at)
VALUES (%(source_dataset)s, %(topic)s, %(metric)s, %(geo_type)s, %(geo_code)s, %(geo_name)s,
        %(period)s, %(period_date)s, %(value)s, %(unit)s, NOW())
ON CONFLICT (source_dataset, topic, metric, geo_type, geo_code, period)
DO UPDATE SET
    value       = EXCLUDED.value,
    geo_name    = EXCLUDED.geo_name,
    period_date = EXCLUDED.period_date,
    unit        = EXCLUDED.unit,
    loaded_at   = NOW()
"""


def _chunked(seq: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _upsert_observations(sb: psycopg.Connection, rows: list[dict[str, Any]]) -> int:
    """Chunked executemany upsert. Returns total rows written."""
    if not rows:
        return 0
    total = 0
    with sb.cursor() as cur:
        for chunk in _chunked(rows, UPSERT_CHUNK_SIZE):
            cur.executemany(UPSERT_SQL, chunk)
            total += len(chunk)
            log.info("mirror upsert chunk: %d rows (cumulative %d)", len(chunk), total)
    sb.commit()
    return total


def _log_etl_run(sb: psycopg.Connection, status: str, rows_written: int,
                 started_at: datetime, error: str | None = None) -> None:
    with sb.cursor() as cur:
        cur.execute(
            """
            INSERT INTO stats_warehouse.etl_runs
                (source, started_at, completed_at, status, rows_written, error)
            VALUES (%s, %s, NOW(), %s, %s, %s)
            """,
            (SOURCE_DATASET, started_at, status, rows_written, error),
        )
    sb.commit()


# =============================================================================
# Flow
# =============================================================================

def _on_crashed(flow, flow_run, state):  # noqa: ARG001
    """Catch SIGKILL/OOM — fires on terminal CRASHED state."""
    try:
        err = state.result(raise_on_failure=False) if state else RuntimeError("crashed")
        if not isinstance(err, Exception):
            err = RuntimeError(f"mirror crashed (state={state.name if state else 'unknown'})")
    except Exception as exc:
        err = exc
    notify_pipeline_failure(err, dataset="warehouse-mirror:crash")


@flow(name="labour-warehouse-mirror", log_prints=True, on_crashed=[_on_crashed])
def mirror() -> None:
    """Full re-mirror from labour_market_au -> Supabase stats_warehouse.

    Sequence:
      1. Schema guard (refuse to run if source_dataset missing from UQ).
      2. Fetch all 4 source tables (SALM / IVI / Projections / RLMI),
         map each row to the warehouse schema.
      3. Chunked upsert into stats_warehouse.observations.
      4. Log run to stats_warehouse.etl_runs + Slack notify.

    Idempotent on the (source_dataset, topic, metric, geo_type, geo_code,
    period) unique constraint. Re-running just refreshes any revised values.
    """
    config = load_config("config.yaml")
    started_at = datetime.now(timezone.utc)
    rows_total = 0
    current_step = "init"

    db = Database(config.database)
    sb: psycopg.Connection | None = None
    try:
        current_step = "open_source"
        db.connect()

        current_step = "open_supabase"
        sb = _open_supabase()

        current_step = "schema_guard"
        _assert_warehouse_unique_includes_source_dataset(sb)

        # Stage by source table. Per-table breakdown surfaces in logs which
        # makes a partial outage easier to diagnose than a single big batch.
        for source_name, fetcher in (
            ("salm_lga",         _fetch_salm_lga),
            ("ivi_state_majors", _fetch_ivi_state_majors),
            ("projections",      _fetch_projections_state),
            ("rlmi_sa4",         _fetch_rlmi_sa4),
        ):
            current_step = f"fetch_{source_name}"
            mapped = fetcher(db)
            log.info("mirror %s: %d rows mapped from source", source_name, len(mapped))

            current_step = f"upsert_{source_name}"
            written = _upsert_observations(sb, mapped)
            rows_total += written
            log.info("mirror %s: %d rows upserted to warehouse (cumulative %d)",
                     source_name, written, rows_total)

        current_step = "log_etl_run"
        _log_etl_run(sb, "success", rows_total, started_at)

        send_slack(
            f":white_check_mark: *Labour warehouse mirror complete*\n"
            f"Source: jsa_labour | Rows mirrored: {rows_total:,}"
        )
        log.info("mirror: SUCCESS rows_total=%d", rows_total)

    except Exception as exc:
        log.exception("mirror failed at step %s", current_step)
        tb = "".join(traceback.format_exception_only(type(exc), exc)).strip()[:500]
        if sb is not None:
            try:
                _log_etl_run(sb, "failure", rows_total, started_at, error=tb)
            except Exception:
                pass  # don't mask the original exception
        notify_pipeline_failure(exc, dataset=f"warehouse-mirror:{current_step}")
        raise
    finally:
        if sb is not None:
            try:
                sb.close()
            except Exception:
                pass
        try:
            db.close()
        except Exception:
            pass


if __name__ == "__main__":
    # One-shot run for local testing or operator-initiated backfill.
    # Set LABOUR_MARKET_AU_PG* + SUPABASE_PG_* env vars first.
    try:
        mirror()
    except Exception as exc:
        log.error("Mirror crashed at top level: %s", exc)
        sys.exit(1)
