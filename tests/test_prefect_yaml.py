"""Smoke-test that prefect.yaml parses + has the portfolio-shape essentials.

Deliberately uses raw `yaml.safe_load` (not `statdesk_prefect_tools.preflight
.yaml_schema`) so the test stays runnable with just `pip install -e .[dev]`
-- no `[ci]` extra required. Full schema validation lives in the preflight
CI job, which DOES install `[ci]`.

Note: this scraper has *unpaused* production deployments, so we don't assert
`paused: True` here (unlike the freshly-scaffolded cookiecutter template
where new scrapers ship paused).
"""
from __future__ import annotations

from pathlib import Path

import yaml


PREFECT_YAML = Path(__file__).resolve().parent.parent / "prefect.yaml"


def test_prefect_yaml_parses_and_names_pipeline() -> None:
    data = yaml.safe_load(PREFECT_YAML.read_text(encoding="utf-8"))
    assert data["name"] == "labour-market-au"
    assert "deployments" in data
    assert len(data["deployments"]) == 2


def test_every_deployment_on_default_pool_with_pgdatabase() -> None:
    data = yaml.safe_load(PREFECT_YAML.read_text(encoding="utf-8"))
    for dep in data["deployments"]:
        assert dep["work_pool"]["name"] == "default", f"{dep['name']!r} is not on default pool"
        # PGDATABASE wired through to the worker
        assert dep["job_variables"]["env"]["PGDATABASE"] == "labour_market_au"


def test_expected_deployment_names() -> None:
    data = yaml.safe_load(PREFECT_YAML.read_text(encoding="utf-8"))
    names = {dep["name"] for dep in data["deployments"]}
    assert names == {"labour-daily-monitor", "labour-warehouse-mirror"}
