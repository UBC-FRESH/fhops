"""Builds a provisional productivity-model registry from Arnvik tables."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from fhops.productivity_registry import ProductivityModel, registry

APPENDIX8 = Path("notes/reference/arnvik_tables/appendix8/appendix8_aggregate.csv")
OUTPUT = Path("notes/reference/arnvik_tables/registry_models.json")


def iter_rows(path: Path) -> Iterable[list[str]]:
    import csv

    with path.open(encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if any(cell.strip() for cell in row):
                yield row


def parse_model_row(row: list[str]) -> ProductivityModel | None:
    if len(row) < 10:
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
    predictors = sorted(set(re.findall(r"[A-Z][₀-₉\d]*", formula)))
    model = ProductivityModel(
        machine_type=machine_type or "unknown",
        system=harvest_method,
        region="",
        publication=f"{publication} model {model_nr}",
        predictors=predictors,
        coefficients={},
        intercept=None,
        form=formula,
        r_squared=None,
        notes=f"Base machine: {base_machine}; System: {system}; DV: {dependent} {units}",
    )
    return model


def main() -> None:
    if not APPENDIX8.exists():
        raise SystemExit("Missing appendix8 aggregate CSV")
    count = 0
    for row in iter_rows(APPENDIX8):
        model = parse_model_row(row)
        if model:
            registry.add(model)
            count += 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as fh:
        json.dump([model.__dict__ for model in registry.all()], fh, indent=2)
    print(f"Captured {count} provisional models -> {OUTPUT}")


if __name__ == "__main__":
    main()
