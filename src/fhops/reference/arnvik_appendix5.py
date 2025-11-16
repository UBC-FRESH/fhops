"""Helpers for Arnvik (2024) Appendix 5 stand metadata."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_PATH = (
    Path(__file__).resolve().parents[3]
    / "notes/reference/arnvik_tables/appendix5_stands_normalized.json"
)

SLOPE_KEYWORDS = {
    "level": 0.0,
    "flat": 0.0,
    "predominately flat": 5.0,
    "slight": 10.0,
}


@dataclass(frozen=True)
class Appendix5Stand:
    author: str
    tree_species: str
    stand_age: str
    stem_volume: str
    dbh: str
    ground_condition: str
    ground_roughness: str
    slope_text: str
    num_operators: str
    notes: str
    pages: Sequence[int]

    @property
    def average_slope_percent(self) -> float | None:
        return _parse_slope(self.slope_text)


def _parse_slope(value: str) -> float | None:
    if not value:
        return None
    lower = value.lower()
    for keyword, default in SLOPE_KEYWORDS.items():
        if keyword in lower:
            return default
    matches = re.findall(r"-?\d+(?:\.\d+)?", value)
    if matches:
        use_first_only = False
        if "(" in value:
            before_paren = value.split("(", 1)[0]
            if re.search(r"\d", before_paren):
                use_first_only = True
        if use_first_only:
            numbers = [abs(float(matches[0]))]
        else:
            numbers = [abs(float(m)) for m in matches]
        # Degrees indicated by ° symbol
        if "°" in value:
            deg = sum(numbers) / len(numbers)
            return math.tan(math.radians(deg)) * 100.0
        # Percentages default
        return sum(numbers) / len(numbers)
    return None


@lru_cache(maxsize=1)
def load_appendix5_stands() -> Sequence[Appendix5Stand]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Appendix 5 dataset missing: {DATA_PATH}")
    with DATA_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    return tuple(
        Appendix5Stand(
            author=entry.get("author", ""),
            tree_species=entry.get("tree_species", ""),
            stand_age=entry.get("stand_age", ""),
            stem_volume=entry.get("stem_volume", ""),
            dbh=entry.get("dbh", ""),
            ground_condition=entry.get("ground_condition", ""),
            ground_roughness=entry.get("ground_roughness", ""),
            slope_text=entry.get("slope", ""),
            num_operators=entry.get("num_operators", ""),
            notes=entry.get("notes", ""),
            pages=tuple(entry.get("pages", [])),
        )
        for entry in payload
    )


def get_appendix5_profile(author: str) -> Appendix5Stand:
    normalised = author.strip().lower()
    for record in load_appendix5_stands():
        if record.author.strip().lower() == normalised:
            return record
    raise KeyError(f"No Appendix 5 profile found for author '{author}'")


__all__ = ["Appendix5Stand", "load_appendix5_stands", "get_appendix5_profile"]
