"""Build structured Appendix 5 stand metadata for FHOPS."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

SOURCE = Path("notes/reference/arnvik_tables/appendix5_stands_normalized.json")
TARGET = Path("data/reference/arnvik/appendix5_stands.json")


def _ensure_dirs(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return value.strip()


def _first_float(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", "."))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", value)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


SLOPE_KEYWORDS = {
    "level": 0.0,
    "flat": 0.0,
    "predominately flat": 5.0,
    "slight": 10.0,
}


def _parse_slope_percent(value: str | None) -> float | None:
    if not value:
        return None
    lower = value.lower()
    for keyword, default in SLOPE_KEYWORDS.items():
        if keyword in lower:
            return default
    matches = re.findall(r"-?\d+(?:\.\d+)?", value)
    if not matches:
        return None
    use_first_only = False
    if "(" in value:
        before_paren = value.split("(", 1)[0]
        if re.search(r"\d", before_paren):
            use_first_only = True
    numbers = [abs(float(matches[0]))] if use_first_only else [abs(float(m)) for m in matches]
    if "°" in value:
        deg = sum(numbers) / len(numbers)
        return math.tan(math.radians(deg)) * 100.0
    return sum(numbers) / len(numbers)


def build() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"Missing Appendix 5 source: {SOURCE}")
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    output: list[dict] = []
    for entry in data:
        slope_text = _clean_text(entry.get("slope"))
        record = {
            "author": entry["author"],
            "tree_species": _clean_text(entry.get("tree_species")),
            "stand_age_text": _clean_text(entry.get("stand_age")),
            "stand_age_years": _first_float(entry.get("stand_age")),
            "stem_volume_text": _clean_text(entry.get("stem_volume")),
            "stem_volume_m3": _first_float(entry.get("stem_volume")),
            "dbh_text": _clean_text(entry.get("dbh")),
            "dbh_cm": _first_float(entry.get("dbh")),
            "ground_condition": _clean_text(entry.get("ground_condition")),
            "ground_roughness": _clean_text(entry.get("ground_roughness")),
            "slope_text": slope_text,
            "slope_percent": _parse_slope_percent(slope_text),
            "num_operators": _parse_int(entry.get("num_operators")),
            "notes": _clean_text(entry.get("notes")),
            "pages": entry.get("pages", []),
        }
        output.append(record)

    _ensure_dirs(TARGET)
    TARGET.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(output)} appendix5 profiles -> {TARGET}")


if __name__ == "__main__":
    build()
