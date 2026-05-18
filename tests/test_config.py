"""Tests for configuration loading."""

from __future__ import annotations

from labour_market_au.config import AppConfig, DatabaseConfig, MonitorPageConfig, load_config


def test_default_config():
    """AppConfig should have sensible defaults."""
    config = AppConfig()
    assert config.run_mode == "incremental"
    assert "salm" in config.scope.datasets
    assert config.database.pg_database == "labour_market_au"
    assert config.http.min_delay_seconds >= 1.0


def test_database_config_defaults(monkeypatch):
    """DatabaseConfig should produce valid connection params when no env vars
    override the defaults.

    Uses monkeypatch.delenv so the test passes regardless of the calling
    environment — important because the apply_env_overrides validator
    reads PGHOST/PGPORT/etc. from os.environ on every instantiation, and
    CI / Docker containers / dev machines may have those set to
    non-localhost values."""
    for var in ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE"):
        monkeypatch.delenv(var, raising=False)
    db = DatabaseConfig()
    assert db.pg_host == "localhost"
    assert db.pg_port == 5432
    params = db.connection_params
    assert params["host"] == "localhost"
    assert "postgresql://" in db.connection_string


def test_database_config_env_overrides(monkeypatch):
    """DatabaseConfig.apply_env_overrides must pick up worker-injected
    PG* env vars at instantiation time.

    This is the production deployment hook — the Prefect worker on the
    Dokploy VPS sets these env vars to point flow runs at the shared
    scraperportfoliopg container instead of the developer's localhost
    Postgres. If this validator stops working (e.g. someone refactors
    the model and forgets the @model_validator), every Prefect-driven
    flow run on the VPS silently tries to connect to localhost inside
    the worker container and fails.
    """
    monkeypatch.setenv("PGHOST", "scraperportfoliopg.docker.internal")
    monkeypatch.setenv("PGPORT", "6543")
    monkeypatch.setenv("PGUSER", "scraper")
    monkeypatch.setenv("PGPASSWORD", "se;cret$pw")  # exercise special chars
    monkeypatch.setenv("PGDATABASE", "labour_market_au")

    db = DatabaseConfig()
    assert db.pg_host == "scraperportfoliopg.docker.internal"
    assert db.pg_port == 6543
    assert db.pg_user == "scraper"
    assert db.pg_password == "se;cret$pw"
    assert db.pg_database == "labour_market_au"

    # Keyword-form connection_params is what Database.connect() uses —
    # special characters in the password pass through psycopg's parameter
    # binding unchanged, never URL-encoded.
    params = db.connection_params
    assert params["host"] == "scraperportfoliopg.docker.internal"
    assert params["port"] == 6543
    assert params["password"] == "se;cret$pw"
    assert params["dbname"] == "labour_market_au"


def test_database_config_partial_env_overrides(monkeypatch):
    """Setting only some env vars should override only those fields,
    leaving the rest at YAML/defaults — important when the worker
    container sets PGHOST/PGPORT/PGUSER/PGPASSWORD globally and the
    per-deployment prefect.yaml only injects PGDATABASE."""
    for var in ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PGDATABASE", "some_other_db")
    db = DatabaseConfig()
    assert db.pg_database == "some_other_db"
    assert db.pg_host == "localhost"  # unchanged default
    assert db.pg_port == 5432  # unchanged default


def test_config_hash_stable():
    """Same config should produce same hash."""
    c1 = AppConfig()
    c2 = AppConfig()
    assert c1.config_hash() == c2.config_hash()


def test_load_config_missing_file(tmp_path):
    """Loading from nonexistent file should return defaults."""
    config = load_config(
        config_path=tmp_path / "nonexistent.yaml",
        env_path=tmp_path / "nonexistent.env",
    )
    assert isinstance(config, AppConfig)


def test_monitor_pages_from_dict():
    """monitor_pages should load correctly from a config dict."""
    config = AppConfig(
        monitor_pages=[
            {
                "site": "jsa",
                "dataset": "ivi",
                "page_url": "https://example.com/ivi",
                "update_frequency": "monthly",
                "content_selector": "div.content",
                "date_selector": "div.date strong",
            },
            {
                "site": "dewr",
                "dataset": "salm_smoothed",
                "page_url": "https://example.com/salm",
            },
        ],
    )
    assert len(config.monitor_pages) == 2
    assert isinstance(config.monitor_pages[0], MonitorPageConfig)
    assert config.monitor_pages[0].site == "jsa"
    assert config.monitor_pages[0].date_selector == "div.date strong"
    assert config.monitor_pages[1].update_frequency == "quarterly"  # default
    assert config.monitor_pages[1].content_selector == ""  # default


def test_monitor_pages_default_empty():
    """monitor_pages should default to an empty list."""
    config = AppConfig()
    assert config.monitor_pages == []
