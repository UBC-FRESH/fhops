"""Build a forwarder/harwarder/grapple-skidder summary from Arnvik (2024) tables."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
REGISTRY = BASE_DIR / "notes/reference/arnvik_tables/registry_models.json"
VARIABLES_JSON = BASE_DIR / "notes/reference/arnvik_tables/appendix9/variables.json"
STATS_JSON = BASE_DIR / "notes/reference/arnvik_tables/appendix11/statistics.json"
OUTPUT = BASE_DIR / "data/productivity/arnvik_forwarder.json"

ROLE_MAP: dict[str, str] = {
    "harwarder": "forwarder_harwarder",
    "harwarder_sim": "forwarder_harwarder_sim",
    "skidder_harvester": "grapple_skidder",
}


def load_json(path: Path) -> dict[str, Any] | list[Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def canonical_predictor(code: str) -> str:
    code = (code or "").strip()
    if not code:
        return ""
    code = code.lstrip("*")
    return re.sub(r"[a-z]+$", "", code)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split())


def parse_field(notes: str, label: str) -> str | None:
    if not notes:
        return None
    match = re.search(rf"{label}:\s*([^;]+)", notes)
    if match:
        return match.group(1).strip()
    return None


def derive_range_hint(description: str) -> str | None:
    text = clean_text(description)
    if not text:
        return None
    if any(ch.isdigit() for ch in text) or any(ch in "≤≥<>%" for ch in text):
        return text
    return None


def build_predictor_catalog(models: list[dict], variables: dict[str, dict]) -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for model in models:
        for predictor in model.get("predictors", []):
            base = canonical_predictor(predictor.get("code", ""))
            if not base or base in catalog:
                continue
            meta = variables.get(base, {})
            desc = clean_text(meta.get("description") or predictor.get("description", ""))
            catalog[base] = {
                "unit": clean_text(meta.get("unit") or predictor.get("unit", "")),
                "description": desc,
                "range_hint": derive_range_hint(desc),
            }
    return dict(sorted(catalog.items()))


def build_model_records(registry: list[dict], stats: dict[str, dict]) -> list[dict]:
    records: list[dict] = []
    for model in registry:
        machine_type = model.get("machine_type", "")
        predictors = model.get("predictors", [])
        predictor_codes: list[str] = []
        seen_codes: set[str] = set()
        for predictor in predictors:
            base = canonical_predictor(predictor.get("code", ""))
            if not base:
                continue
            if base not in seen_codes:
                predictor_codes.append(base)
                seen_codes.add(base)
        stats_payload = stats.get(model.get("publication", ""), {})
        record = {
            "role": ROLE_MAP[machine_type],
            "machine_type": machine_type,
            "system": model.get("system"),
            "publication": model.get("publication"),
            "dependent_variable": parse_field(model.get("notes", ""), "Dependent"),
            "base_machine": parse_field(model.get("notes", ""), "Base machine"),
            "propulsion": parse_field(model.get("notes", ""), "Propulsion"),
            "form": model.get("form"),
            "coefficients": {
                k: v for k, v in model.get("coefficients", {}).items() if v and v != "-"
            },
            "r_squared": model.get("r_squared"),
            "observations": _maybe_int(stats_payload.get("observations")),
            "observational_unit": stats_payload.get("observational_unit"),
            "structure": stats_payload.get("structure"),
            "significance": stats_payload.get("significance"),
            "f_stat": stats_payload.get("f_stat"),
            "predictor_codes": predictor_codes,
        }
        records.append(record)
    return sorted(records, key=lambda rec: rec.get("publication") or "")


def _maybe_int(value: str | None) -> int | None:
    if not value or value in {"-", ""}:
        return None
    try:
        return int(value.replace(",", "").strip())
    except ValueError:
        return None


def main() -> None:
    registry = load_json(REGISTRY)
    variables = load_json(VARIABLES_JSON)
    stats = load_json(STATS_JSON)

    filtered_models = [model for model in registry if model.get("machine_type") in ROLE_MAP]
    records = build_model_records(filtered_models, stats)
    predictor_catalog = build_predictor_catalog(filtered_models, variables)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "Arnvik (2024) Appendix 8–11 tables (Camelot extraction)",
        "machine_types_considered": sorted(ROLE_MAP.keys()),
        "machine_types_present": sorted({rec["machine_type"] for rec in records}),
        "predictors": predictor_catalog,
        "models": records,
    }
    with OUTPUT.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
