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
    data = json.loads(_CPI_PATH.read_text(encoding="utf-8"))
    series = data.get("values") or {}
    return {int(year): float(value) for year, value in series.items()}


def inflation_multiplier(from_year: int, to_year: int = TARGET_YEAR) -> float:
    """Return multiplier to convert a cost from ``from_year`` CAD to ``to_year`` CAD."""

    cpi = _load_cpi_series()
    if from_year not in cpi:
        raise ValueError(f"CPI data missing for year {from_year} (available {min(cpi)}-{max(cpi)}).")
    if to_year not in cpi:
        raise ValueError(f"CPI data missing for target year {to_year}.")
    return cpi[to_year] / cpi[from_year]


def inflate_value(value: float | None, from_year: int, to_year: int = TARGET_YEAR) -> float | None:
    """Inflate ``value`` (CAD) from ``from_year`` to ``to_year`` using CPI."""

    if value is None:
        return None
    return float(value) * inflation_multiplier(from_year, to_year)


__all__ = ["TARGET_YEAR", "inflation_multiplier", "inflate_value"]
