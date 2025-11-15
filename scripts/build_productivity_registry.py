"""Builds a provisional productivity-model registry from Arnvik tables."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from fhops.productivity_registry import ProductivityModel, registry

APPENDIX8 = Path("notes/reference/arnvik_tables/appendix8/appendix8_aggregate.csv")
VARS_JSON = Path("notes/reference/arnvik_tables/appendix9/variables.json")
PARAM_JSON = Path("notes/reference/arnvik_tables/appendix10/parameters.json")
STAT_JSON = Path("notes/reference/arnvik_tables/appendix11/statistics.json")
OUTPUT = Path("notes/reference/arnvik_tables/registry_models.json")

with VARS_JSON.open() as fh:
    VARIABLES = json.load(fh)
with PARAM_JSON.open() as fh:
    PARAMETERS = json.load(fh)
with STAT_JSON.open() as fh:
    STATS = json.load(fh)


def iter_rows(path: Path) -> Iterable[list[str]]:
    import csv

    with path.open(encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if any(cell.strip() for cell in row):
                yield row


def human_predictors(formula: str) -> list[str]:
    tokens = re.findall(r"[A-Z][A-Za-z0-9₀-₉]*", formula)
    seen = []
    for token in tokens:
        if token not in seen:
            seen.append(token)
    return seen


def fetch_metadata(pub: str, nr: str) -> tuple[dict, dict, dict]:
    key = f"{pub} model {nr}"
    params = PARAMETERS.get(key, {})
    stats = STATS.get(key, {})
    return params, stats


def parse_model_row(row: list[str]) -> ProductivityModel | None:
    if len(row) < 14:
        return None
    prefix = " ".join(cell.strip() for cell in row[:5] if cell.strip())
    match = re.search(r"(.*?)(\d+)$", prefix)
    if not match:
        return None
    publication = match.group(1).strip().rstrip(",")
    model_nr = match.group(2)
    harvest_method = row[5].strip()
    machine_type = row[6].strip()
    base_machine = row[7].strip()
    system = row[8].strip()
    dependent = row[9].strip()
    units = " ".join(cell.strip() for cell in row[10:13] if cell.strip())
    formula = " ".join(cell.strip() for cell in row[13:] if cell.strip())
    if not formula or not harvest_method:
        return None
    predictor_codes = human_predictors(formula)
    predictor_details = [
        {
            "code": code,
            "description": VARIABLES.get(code, {}).get("description", ""),
            "unit": VARIABLES.get(code, {}).get("unit", ""),
        }
        for code in predictor_codes
    ]
    params, stats = fetch_metadata(publication, model_nr)
    model = ProductivityModel(
        machine_type=machine_type or "unknown",
        system=harvest_method,
        region="",
        publication=f"{publication} model {model_nr}",
        predictors=predictor_details,
        coefficients=params,
        intercept=params.get("a"),
        form=formula,
        r_squared=_parse_float(stats.get("r_squared")),
        notes=build_notes(base_machine, system, dependent, units, stats),
    )
    return model


def _parse_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def build_notes(base_machine: str, system: str, dependent: str, units: str, stats: dict) -> str:
    pieces = [
        f"Base machine: {base_machine}",
        f"System: {system}",
        f"Dependent: {dependent} {units}",
    ]
    if stats:
        pieces.append(f"Observational unit: {stats.get('observational_unit')} ({stats.get('observations')})")
        pieces.append(f"Structure: {stats.get('structure')}")
        if stats.get("significance"):
            pieces.append(f"Significance: {stats['significance']}")
    return "; ".join(filter(None, pieces))


def main() -> None:
    registry._models.clear()  # reset
    count = 0
    for row in iter_rows(APPENDIX8):
        model = parse_model_row(row)
        if model:
            registry.add(model)
            count += 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as fh:
        json.dump([model.__dict__ for model in registry.all()], fh, indent=2, ensure_ascii=False)
    print(f"Captured {count} enriched models -> {OUTPUT}")


if __name__ == "__main__":
    main()
