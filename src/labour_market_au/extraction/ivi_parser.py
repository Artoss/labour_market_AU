"""
IVI (Internet Vacancy Index) Excel parser.
Stub for Phase 2 implementation.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("labour_market_au.extraction.ivi_parser")


def parse_ivi_excel(filepath: Path) -> list[dict]:
    """Parse an IVI Excel workbook into a list of record dicts.

    TODO: Implement in Phase 2 after examining actual IVI file structure.
    """
    logger.warning("IVI parser not yet implemented, skipping %s", filepath.name)
    return []
