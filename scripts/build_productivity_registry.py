"""Builds a provisional productivity-model registry from Arnvik tables."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from pathlib import Path

from fhops.productivity_registry import ProductivityModel, registry

APPENDIX8 = Path("notes/reference/arnvik_tables/appendix8/appendix8_aggregate.csv")
APPENDIX8_CAMELOT = Path(
    "notes/reference/arnvik_tables/appendix8_camelot/appendix8_camelot_aggregate.csv"
)
VARS_JSON = Path("notes/reference/arnvik_tables/appendix9/variables.json")
PARAM_JSON = Path("notes/reference/arnvik_tables/appendix10/parameters.json")
STAT_JSON = Path("notes/reference/arnvik_tables/appendix11/statistics.json")
REF_JSON = Path("notes/reference/arnvik_tables/references.json")
OUTPUT = Path("notes/reference/arnvik_tables/registry_models.json")

with VARS_JSON.open() as fh:
    VARIABLES = json.load(fh)
with PARAM_JSON.open() as fh:
    PARAMETERS = json.load(fh)
with STAT_JSON.open() as fh:
    STATS = json.load(fh)
if REF_JSON.exists():
    with REF_JSON.open() as fh:
        REFERENCES = json.load(fh)
else:
    REFERENCES = {}

MACHINE_TYPE_MAP = {
    "H": "single_grip_harvester",
    "H Sim": "single_grip_harvester_sim",
    "FB": "feller_buncher",
    "FB DT": "feller_buncher_drive_to_tree",
    "FB Sim": "feller_buncher_sim",
    "HW": "harwarder",
    "HW Sim": "harwarder_sim",
    "SH": "skidder_harvester",
}

HARVEST_METHOD_MAP = {
    "CTL": "cut_to_length",
    "FT": "full_tree",
    "B (FT)": "bundle_full_tree",
    "H (FT)": "hand_full_tree",
    "": "",
}


def iter_rows(path: Path) -> Iterable[list[str]]:
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


def fetch_metadata(pub: str, nr: str) -> tuple[dict, dict]:
    key = f"{pub} model {nr}"
    params = PARAMETERS.get(key, {})
    stats = STATS.get(key, {})
    return params, stats


def reference_key(publication: str) -> str | None:
    match = re.search(r"([A-Za-zÄÅÖÆØÜÉáéíóúñç'`-]+)[^0-9]*(\d{4}[a-z]?)", publication)
    if not match:
        return None
    surname = re.sub(r"[^A-Za-zÄÅÖÆØÜÉáéíóúñç'`-]", " ", match.group(1)).split()[-1]
    year = match.group(2).lower()
    if not surname:
        return None
    return f"{surname.lower()}_{year}"


def fetch_reference(pub: str) -> dict | None:
    key = reference_key(pub)
    if not key:
        return None
    return REFERENCES.get(key)


def normalize_machine_type(value: str) -> str:
    if not value:
        return "unknown"
    return MACHINE_TYPE_MAP.get(value, value.lower().replace(" ", "_"))


def normalize_harvest_method(value: str) -> str:
    if not value:
        return ""
    base = HARVEST_METHOD_MAP.get(value)
    if base is not None:
        return base
    return value.lower().replace(" ", "_")


def clean_token(value: str) -> str:
    return value.strip().lstrip("*,")


def _normalize_publication(candidate: str) -> str:
    candidate = candidate.replace(" ,", ",").replace("( ", "(").replace(" )", ")")
    candidate = re.sub(
        r"\((\d+)\s+(\d+[a-z]?)\)", lambda m: f"({m.group(1)}{m.group(2)})", candidate
    )
    return candidate.strip().rstrip(",")


def decode_model_row(row: list[str]) -> tuple[str, str, str, str, str, str, str, str, str] | None:
    if len(row) < 6:
        return None
    cells = [cell.strip() for cell in row[2:] if cell and cell.strip()]
    if not cells:
        return None
    if cells[0].startswith("Author"):
        return None
    tokens = cells
    pub_tokens: list[str] = []
    rest_tokens: list[str] | None = None
    for idx, token in enumerate(tokens):
        if ")" in token:
            before, after = token.split(")", 1)
            prefix = (before + ")").strip()
            if prefix:
                pub_tokens.append(prefix)
            else:
                pub_tokens.append(")")
            remainder = after.strip()
            rest_tokens = ([remainder] if remainder else []) + tokens[idx + 1 :]
            break
        pub_tokens.append(token)
    if not pub_tokens or rest_tokens is None or not rest_tokens:
        return None
    publication = (
        " ".join(pub_tokens)
        .replace(" ,", ",")
        .replace("( ", "(")
        .replace(" )", ")")
        .strip()
        .rstrip(",")
    )
    if not publication:
        return None
    nr_token = rest_tokens[0]
    nr_match = re.search(r"(\d+)", nr_token)
    if not nr_match:
        return None
    model_nr = nr_match.group(1)
    tokens_tail = rest_tokens[1:]
    if len(tokens_tail) < 6:
        return None
    cursor = 0
    harvest_method = normalize_harvest_method(tokens_tail[cursor])
    cursor += 1
    machine_type = normalize_machine_type(tokens_tail[cursor])
    cursor += 1
    base_machine = tokens_tail[cursor]
    cursor += 1
    propulsion = tokens_tail[cursor]
    cursor += 1
    dv_type = tokens_tail[cursor]
    cursor += 1
    units_tokens: list[str] = []
    while cursor < len(tokens_tail):
        tok = tokens_tail[cursor]
        units_tokens.append(tok)
        cursor += 1
        if ")" in tok:
            break
    units = " ".join(units_tokens).replace(" )", ")").strip()
    formula = " ".join(tokens_tail[cursor:]).strip()
    if not formula or not harvest_method:
        return None
    return (
        publication,
        model_nr,
        harvest_method,
        machine_type,
        base_machine,
        propulsion,
        dv_type,
        units,
        formula,
    )


def build_productivity_model(
    publication: str,
    model_nr: str,
    harvest_method: str,
    machine_type: str,
    base_machine: str,
    propulsion: str,
    dv_type: str,
    units: str,
    formula: str,
) -> ProductivityModel:
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
    ref = fetch_reference(publication)
    return ProductivityModel(
        machine_type=machine_type or "unknown",
        system=harvest_method,
        region="",
        publication=f"{publication} model {model_nr}",
        predictors=predictor_details,
        coefficients=params,
        intercept=params.get("a"),
        form=formula,
        r_squared=_parse_float(stats.get("r_squared")),
        notes=build_notes(base_machine, propulsion, dv_type, units, stats),
        reference=ref,
    )


def parse_model_row(row: list[str]) -> ProductivityModel | None:
    payload = decode_model_row(row)
    if not payload:
        return None
    return build_productivity_model(*payload)


def parse_camelot_row(
    record: dict,
) -> tuple[ProductivityModel | None, bool, tuple[str, str] | None]:
    publication = record.get("author", "").strip()
    if not publication or "built;" in publication:
        return None, False, None
    model_nr = record.get("model", "").strip()
    if not model_nr:
        return None, False, None
    harvest_method = normalize_harvest_method(clean_token(record.get("harvest_method", "")))
    machine_raw = clean_token(record.get("machine_type", ""))
    base_machine = clean_token(record.get("base_machine", ""))
    propulsion_raw = clean_token(record.get("propulsion", ""))
    dv_type = clean_token(record.get("dv_type", ""))
    units = record.get("units", "").strip()
    formula = record.get("formula", "").strip()
    if base_machine and base_machine not in {"PB", "EB"}:
        formula = units or formula
        units = dv_type
        dv_type = propulsion_raw
        propulsion_raw = base_machine
        base_machine = ""
    if not base_machine and machine_raw:
        for candidate in ("PB", "EB"):
            if machine_raw.endswith(candidate):
                machine_raw = machine_raw[: -len(candidate)].strip()
                base_machine = candidate
                break
    machine_type = normalize_machine_type(machine_raw)
    propulsion = propulsion_raw
    fallback = LEGACY_LOOKUP.get((publication, model_nr))
    if fallback:
        _, _, fhm, fmachine, fbase, fprop, fdv, funits, fformula = fallback
        harvest_method = harvest_method or fhm
        machine_type = machine_type or fmachine
        base_machine = base_machine or fbase
        propulsion = propulsion or fprop
        dv_type = dv_type or fdv
        units = units or funits
        formula = formula or fformula
    if not formula or not harvest_method:
        return None, False, None
    return (
        build_productivity_model(
            publication,
            model_nr,
            harvest_method,
            machine_type,
            base_machine,
            propulsion,
            dv_type,
            units,
            formula,
        ),
        True,
        (publication, model_nr),
    )


def _parse_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def build_notes(base_machine: str, propulsion: str, dependent: str, units: str, stats: dict) -> str:
    pieces = [
        f"Base machine: {base_machine}",
        f"Propulsion: {propulsion}",
        f"Dependent: {dependent} {units}",
    ]
    if stats:
        pieces.append(
            f"Observational unit: {stats.get('observational_unit')} ({stats.get('observations')})"
        )
        pieces.append(f"Structure: {stats.get('structure')}")
        if stats.get("significance"):
            pieces.append(f"Significance: {stats['significance']}")
    return "; ".join(filter(None, pieces))


def build_legacy_lookup() -> dict[
    tuple[str, str], tuple[str, str, str, str, str, str, str, str, str]
]:
    lookup: dict[tuple[str, str], tuple[str, str, str, str, str, str, str, str, str]] = {}
    if not APPENDIX8.exists():
        return lookup
    for row in iter_rows(APPENDIX8):
        payload = decode_model_row(row)
        if not payload:
            continue
        publication, model_nr, *_ = payload
        lookup[(publication, model_nr)] = payload
    return lookup


LEGACY_LOOKUP = build_legacy_lookup()


def main() -> None:
    registry._models.clear()  # reset
    count = 0
    seen: set[tuple[str, str]] = set()
    if APPENDIX8_CAMELOT.exists():
        with APPENDIX8_CAMELOT.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for record in reader:
                model, matched, key = parse_camelot_row(record)
                if key and key in seen:
                    continue
                if model:
                    registry.add(model)
                    count += 1
                    if key:
                        seen.add(key)
        # backfill missing entries from legacy lookup
        for key, payload in LEGACY_LOOKUP.items():
            if key in seen:
                continue
            model = build_productivity_model(*payload)
            registry.add(model)
            count += 1
    else:
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
