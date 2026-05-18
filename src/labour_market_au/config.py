"""
Configuration loader and validation.
Reads config.yaml + .env and produces a strongly-typed AppConfig object.
Environment variables override YAML values for sensitive fields.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------

class ScopeConfig(BaseModel):
    """What sites and datasets to process."""
    sites: list[str] = ["jsa", "dewr"]
    datasets: list[str] = ["salm", "ivi", "projections", "total_vacancies"]


class HttpConfig(BaseModel):
    """Rate limiting and HTTP client settings."""
    min_delay_seconds: float = 2.0
    max_delay_seconds: float = 5.0
    max_retries: int = 3
    retry_backoff_factor: float = 2.0
    timeout_seconds: int = 120
    user_agents: list[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    default_headers: dict[str, str] = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
    }


class DatabaseConfig(BaseModel):
    """PostgreSQL connection settings.

    The five `pg_*` fields default to laptop-friendly localhost values.
    `apply_env_overrides` then reads `PGHOST` / `PGPORT` / `PGUSER` /
    `PGPASSWORD` / `PGDATABASE` from the environment and overrides any
    that are set — this is the production deployment hook used by the
    Prefect worker on the Dokploy VPS to point flow runs at the shared
    `scraperportfoliopg` container instead of localhost.

    Env-var injection chain in production:

      1. Prefect worker container compose env sets PGHOST / PGPORT /
         PGUSER / PGPASSWORD (shared portfolio credentials, same for
         every deployment).
      2. Per-deployment `prefect.yaml` `job_variables.env` sets
         PGDATABASE (e.g. `labour_market_au` for this scraper,
         `sqm_research` for SQM).
      3. Flow run subprocess inherits both; `apply_env_overrides`
         reads from `os.environ`; `Database.connect()` uses keyword-
         form `connection_params` (no URI parsing, so special chars in
         the password survive untouched).

    Local-dev path: `.env` file at the repo root is loaded by
    `load_dotenv()` before this model is instantiated, populating the
    same env vars from the developer's preferred local settings.

    Test coverage: `tests/test_config.py` pins both the default
    behaviour and the env-override behaviour against regression.
    """
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "labour_market_au"
    pg_user: str = "postgres"
    pg_password: str = ""

    @model_validator(mode="after")
    def apply_env_overrides(self):
        if env_user := os.getenv("PGUSER"):
            self.pg_user = env_user
        if env_pass := os.getenv("PGPASSWORD"):
            self.pg_password = env_pass
        if env_host := os.getenv("PGHOST"):
            self.pg_host = env_host
        if env_port := os.getenv("PGPORT"):
            self.pg_port = int(env_port)
        if env_db := os.getenv("PGDATABASE"):
            self.pg_database = env_db
        return self

    @property
    def connection_string(self) -> str:
        return (
            f"postgresql://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )

    @property
    def connection_params(self) -> dict:
        return {
            "host": self.pg_host,
            "port": self.pg_port,
            "dbname": self.pg_database,
            "user": self.pg_user,
            "password": self.pg_password,
        }


class DownloadsConfig(BaseModel):
    base_dir: str = "./data"


class ExportConfig(BaseModel):
    enabled: bool = True
    format: Literal["csv", "json", "excel"] = "csv"
    output_dir: str = "./exports"
    timestamp_files: bool = True


class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    file: str = "./logs/labour_market_au.log"
    console: bool = True
    rotate_mb: int = 10
    keep_backups: int = 5


class MonitorPageConfig(BaseModel):
    """A web page to monitor for content changes."""
    site: str
    dataset: str
    page_url: str
    update_frequency: str = "quarterly"
    content_selector: str = ""
    date_selector: str = ""


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------

class AppConfig(BaseModel):
    """Root configuration model."""
    run_mode: Literal["full", "incremental"] = "incremental"
    scope: ScopeConfig = Field(default_factory=ScopeConfig)
    http: HttpConfig = Field(default_factory=HttpConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    downloads: DownloadsConfig = Field(default_factory=DownloadsConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    monitor_pages: list[MonitorPageConfig] = Field(default_factory=list)

    def config_hash(self) -> str:
        """SHA256 hash of config for run tracking."""
        data = self.model_dump_json(indent=None)
        return hashlib.sha256(data.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_config(
    config_path: str | Path = "config.yaml",
    env_path: str | Path = ".env",
) -> AppConfig:
    """Load YAML + .env, priority: env vars > YAML > defaults."""
    env_file = Path(env_path)
    if env_file.exists():
        load_dotenv(env_file)

    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    config = AppConfig(**raw)

    # Ensure output directories exist
    Path(config.downloads.base_dir).mkdir(parents=True, exist_ok=True)
    Path(config.export.output_dir).mkdir(parents=True, exist_ok=True)
    Path(config.logging.file).parent.mkdir(parents=True, exist_ok=True)

    return config
