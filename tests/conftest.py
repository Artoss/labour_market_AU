"""Shared test fixtures."""

from __future__ import annotations

import pytest

from labour_market_au.config import AppConfig, load_config


@pytest.fixture
def app_config(tmp_path) -> AppConfig:
    """Create a test config with temp directories."""
    config = AppConfig(
        downloads={"base_dir": str(tmp_path / "data")},
        export={"output_dir": str(tmp_path / "exports")},
        logging={"file": str(tmp_path / "logs" / "test.log"), "console": False},
    )
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "exports").mkdir(exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)
    return config
