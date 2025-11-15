"""Reference parameter ranges for Lahrsen (2025)."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping

RangePayload = Mapping[str, Any]


@lru_cache(maxsize=None)
def load_lahrsen_ranges() -> RangePayload:
    """Return Lahrsen (2025) descriptive ranges as a nested mapping."""

    data_path = resources.files(__package__) / "_data" / "lahrsen2025_ranges.json"
    with resources.as_file(data_path) as path:
        return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["load_lahrsen_ranges"]
