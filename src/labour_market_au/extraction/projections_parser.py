"""
Employment Projections Excel parser.
Stub for Phase 3 implementation.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("labour_market_au.extraction.projections_parser")


def parse_projections_excel(filepath: Path) -> list[dict]:
    """Parse an Employment Projections Excel workbook into record dicts.

    TODO: Implement in Phase 3 after examining actual file structure.
    """
    logger.warning("Projections parser not yet implemented, skipping %s", filepath.name)
    return []
