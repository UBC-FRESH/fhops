"""Utilities for inflating historical cost figures to current CAD."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

TARGET_YEAR = 2024
_CPI_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "costing" / "cpi_canada_all_items_2002_100.json"
)


@lru_cache(maxsize=1)
def _load_cpi_series() -> dict[int, float]:
    """Load the CPI index (2002=100) used to inflate historical costs."""

    data = json.loads(_CPI_PATH.read_text(encoding="utf-8"))
    series = data.get("values") or {}
    return {int(year): float(value) for year, value in series.items()}


def inflation_multiplier(from_year: int, to_year: int = TARGET_YEAR) -> float:
    """
    Return the CPI multiplier required to restate a cost into the target year.

    Parameters
    ----------
    from_year:
        Original CPI base year for the cost figure (e.g., 2014). Must exist in the CPI file.
    to_year:
        Target CPI year (defaults to ``TARGET_YEAR`` / 2024).

    Returns
    -------
    float
        Scalar that, when multiplied by the original cost, expresses the amount in ``to_year`` CAD.

    Raises
    ------
    ValueError
        Raised when CPI coverage is missing for either year.
    """

    cpi = _load_cpi_series()
    if from_year not in cpi:
        raise ValueError(
            f"CPI data missing for year {from_year} (available {min(cpi)}-{max(cpi)})."
        )
    if to_year not in cpi:
        raise ValueError(f"CPI data missing for target year {to_year}.")
    return cpi[to_year] / cpi[from_year]


def inflate_value(value: float | None, from_year: int, to_year: int = TARGET_YEAR) -> float | None:
    """
    Inflate a nominal CAD value from ``from_year`` to ``to_year`` using CPI.

    Parameters
    ----------
    value:
        Cost expressed in ``from_year`` CAD. ``None`` is returned unchanged so callers can pipe
        optional values without branching.
    from_year:
        CPI base year for ``value``.
    to_year:
        Target CPI year (defaults to ``TARGET_YEAR`` / 2024).

    Returns
    -------
    float | None
        The CPI-adjusted amount, or ``None`` when ``value`` was ``None``.
    """

    if value is None:
        return None
    return float(value) * inflation_multiplier(from_year, to_year)


__all__ = ["TARGET_YEAR", "inflation_multiplier", "inflate_value"]
