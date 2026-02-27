"""Tests for configuration loading."""

from __future__ import annotations

from labour_market_au.config import AppConfig, DatabaseConfig, load_config


def test_default_config():
    """AppConfig should have sensible defaults."""
    config = AppConfig()
    assert config.run_mode == "incremental"
    assert "salm" in config.scope.datasets
    assert config.database.pg_database == "labour_market_au"
    assert config.http.min_delay_seconds >= 1.0


def test_database_config_defaults():
    """DatabaseConfig should produce valid connection params."""
    db = DatabaseConfig()
    assert db.pg_host == "localhost"
    assert db.pg_port == 5432
    params = db.connection_params
    assert params["host"] == "localhost"
    assert "postgresql://" in db.connection_string


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
