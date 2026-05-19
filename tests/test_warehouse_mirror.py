"""Sanity tests for the warehouse mirror's Supabase-pooler guards.

These tests run without a live Supabase connection -- they only verify
the static patterns that the preflight guards check are in place:

  - `prepare_threshold=None` on the Supabase connect call
  - `make_conninfo(...)` (keyword form) instead of a URI literal

Don't delete these checks -- they're cheap defense against accidental
regression of the two most expensive Supabase-pooler gotchas in the
portfolio (PR #11 traceback caught this for labour_market_au).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


MIRROR_PATH = Path(__file__).resolve().parent.parent / "pipeline_warehouse_mirror.py"


@pytest.fixture(scope="module")
def mirror_source() -> str:
    return MIRROR_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def mirror_tree(mirror_source: str) -> ast.Module:
    return ast.parse(mirror_source)


def _find_psycopg_connect_calls(tree: ast.Module) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "connect":
                if isinstance(func.value, ast.Name) and func.value.id == "psycopg":
                    calls.append(node)
    return calls


def test_supabase_connect_sets_prepare_threshold_none(mirror_tree: ast.Module) -> None:
    """The Supavisor pooler rejects session-level prepared statements.

    Without `prepare_threshold=None`, the second `cursor.executemany`
    against the pooler raises `DuplicatePreparedStatement`.
    """
    calls = _find_psycopg_connect_calls(mirror_tree)
    assert calls, "no psycopg.connect(...) calls found in pipeline_warehouse_mirror.py"
    for call in calls:
        kwargs = {kw.arg for kw in call.keywords if kw.arg}
        assert "prepare_threshold" in kwargs, (
            f"psycopg.connect at line {call.lineno} is missing prepare_threshold=None"
        )


def test_no_uri_form_supabase_conninfo(mirror_source: str) -> None:
    """Reject `postgresql://...supabase...` URI literals.

    The bundled libpq mis-parses dotted Supabase pooler usernames
    (`postgres.<project-ref>`) in URI form. `make_conninfo()` is safe.
    """
    lowered = mirror_source.lower()
    if "postgresql://" in lowered and "supabase" in lowered:
        # Both substrings present anywhere in the file -- could be a false
        # positive (e.g. comments mentioning the anti-pattern). Tighten by
        # requiring the URI in close textual proximity to "supabase".
        idx = lowered.find("postgresql://")
        window = lowered[max(0, idx - 200):idx + 200]
        assert "supabase" not in window, (
            "Supabase connection in URI form -- use make_conninfo(host=..., user=..., password=...) instead"
        )
