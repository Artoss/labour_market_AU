"""
Shared Excel parsing utilities.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger("labour_market_au.extraction.excel_parser")


def read_excel_sheets(
    filepath: Path,
    header: int = 0,
    index_col: int | list[int] | None = None,
    na_values: str | list[str] | None = None,
    sheet_names: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Read all (or selected) sheets from an Excel file into DataFrames.

    Returns a dict of {sheet_name: DataFrame}.
    """
    sheets: dict[str, pd.DataFrame] = {}
    try:
        with pd.ExcelFile(filepath) as xlsx:
            names_to_read = sheet_names or xlsx.sheet_names
            for name in names_to_read:
                if name not in xlsx.sheet_names:
                    logger.warning("Sheet '%s' not found in %s", name, filepath.name)
                    continue
                df = pd.read_excel(
                    xlsx,
                    sheet_name=name,
                    header=header,
                    index_col=index_col,
                    na_values=na_values,
                )
                sheets[name] = df
                logger.debug(
                    "Read sheet '%s': %d rows x %d cols",
                    name, len(df), len(df.columns),
                )
    except Exception as e:
        logger.error("Failed to read %s: %s", filepath.name, e)
        raise
    return sheets


def melt_wide_to_long(
    df: pd.DataFrame,
    id_vars: list[str],
    var_name: str = "period",
    value_name: str = "value",
) -> pd.DataFrame:
    """Melt a wide-format DataFrame to long format."""
    return pd.melt(
        df.reset_index() if df.index.name else df,
        id_vars=id_vars,
        var_name=var_name,
        value_name=value_name,
    )
