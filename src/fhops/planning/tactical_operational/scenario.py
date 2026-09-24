"""Scenario overlays, diffs, batch runs, and reports for tactical–operational planning."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from pydantic import TypeAdapter

from fhops.model.milp.tactical_operational import (
    build_tactical_operational_bundle,
    solve_tactical_operational_milp,
)
from fhops.planning.tactical_operational.io import load_tactical_operational_scenario
from fhops.planning.tactical_operational.models import TacticalOperationalScenario

_SECTION_ID_FIELDS: dict[str, str | tuple[str, ...]] = {
    "periods": "period_id",
    "products": "product_id",
    "planning_units": "block_id",
    "harvest_system_options": "option_id",
    "fleet_capacity": ("system_id", "period_id"),
    "facilities": "facility_id",
    "facility_demand": ("facility_id", "product_id", "period_id"),
    "initial_inventory": ("facility_id", "product_id"),
    "transport_arcs": "arc_id",
    "external_supply": ("source_id", "destination_id", "product_id", "period_id"),
    "roads": "road_id",
    "road_dependencies": ("road_id", "depends_on_road_id"),
    "block_road_access": ("block_id", "road_id"),
    "silviculture_transitions": "transition_id",
    "fleet_options": "option_id",
}


def read_yaml_mapping(path: str | Path) -> dict[str, Any]:
    """Read a YAML mapping from disk."""
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise TypeError(f"YAML file must contain a mapping: {path}")
    return payload


def scenario_content_hash(payload: dict[str, Any]) -> str:
    """Return a deterministic SHA-256 hash for a scenario payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def apply_tactical_overlay_payload(
    base: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    """Merge a sparse tactical overlay into a base scenario payload.

    List sections are merged by their declared identifier field(s): matching rows are deep-updated,
    new rows are appended, and ``_remove`` may contain identifiers to delete. Scalar sections such as
    ``name`` and ``economics`` are deep-updated recursively.
    """
    merged = deepcopy(base)
    for key, value in overlay.items():
        if key in {"overlay_id", "description", "parent"}:
            continue
        if key == "_remove":
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
            continue
        if isinstance(value, list) and isinstance(merged.get(key), list):
            merged[key] = _merge_rows(key, merged[key], value, overlay.get("_remove", {}).get(key))
            continue
        merged[key] = deepcopy(value)
    remove = overlay.get("_remove")
    if isinstance(remove, dict):
        for section, identifiers in remove.items():
            if section in merged and isinstance(merged[section], list):
                merged[section] = _merge_rows(section, merged[section], [], identifiers)
    merged["parent"] = overlay.get("parent", base.get("name"))
    merged["overlay_id"] = overlay.get("overlay_id")
    merged["source_hash"] = scenario_content_hash(merged)
    return merged


def load_tactical_overlay_scenario(
    base_path: str | Path,
    overlay_path: str | Path,
) -> TacticalOperationalScenario:
    """Load a base tactical scenario and apply a sparse overlay YAML."""
    base = read_yaml_mapping(base_path)
    overlay = read_yaml_mapping(overlay_path)
    merged = apply_tactical_overlay_payload(base, overlay)
    allowed = set(TacticalOperationalScenario.model_fields)
    filtered = {key: value for key, value in merged.items() if key in allowed}
    return TypeAdapter(TacticalOperationalScenario).validate_python(filtered)


def write_tactical_scenario_yaml(
    scenario: TacticalOperationalScenario,
    path: str | Path,
) -> None:
    """Write a validated tactical scenario as a human-readable YAML mapping."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = scenario.model_dump(mode="json")
    with output.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)


def diff_tactical_scenarios(
    base: TacticalOperationalScenario,
    candidate: TacticalOperationalScenario,
) -> pd.DataFrame:
    """Return a row-per-field diff between two validated tactical scenarios."""
    rows: list[dict[str, Any]] = []
    base_payload = base.model_dump(mode="json")
    candidate_payload = candidate.model_dump(mode="json")
    _diff_value("", base_payload, candidate_payload, rows)
    return pd.DataFrame(
        rows, columns=["section", "key", "field", "base_value", "candidate_value", "change_type"]
    )


def solve_tactical_batch_manifest(
    manifest_path: str | Path,
    *,
    out_dir: str | Path,
) -> pd.DataFrame:
    """Solve a manifest of tactical scenario cases and write per-case plus comparison outputs.

    Manifest YAML format::

        cases:
          - case_id: base
            scenario: path/to/base.yaml
          - case_id: low-demand
            scenario: path/to/base.yaml
            overlay: path/to/overlay.yaml
            enable_roads: true
    """
    manifest = read_yaml_mapping(manifest_path)
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Tactical batch manifest requires a non-empty 'cases' list")
    manifest_root = Path(manifest_path).resolve().parent
    output_root = Path(out_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            raise TypeError("Each batch case must be a mapping")
        case_id = str(case.get("case_id"))
        scenario_ref = case.get("scenario")
        if not case_id or not scenario_ref:
            raise ValueError("Each batch case requires case_id and scenario")
        scenario_path = _resolve(manifest_root, scenario_ref)
        overlay = case.get("overlay")
        if overlay:
            scenario = load_tactical_overlay_scenario(
                scenario_path, _resolve(manifest_root, overlay)
            )
        else:
            scenario = load_tactical_operational_scenario(scenario_path)
        bundle = build_tactical_operational_bundle(
            scenario,
            harvest_mode=case.get("harvest_mode", "semi_continuous"),
            demand_basis=case.get("demand_basis", "target"),
            enable_roads=bool(case.get("enable_roads", False)),
            enable_silviculture=bool(case.get("enable_silviculture", False)),
            enable_fleet_investment=bool(case.get("enable_fleet_investment", False)),
        )
        result = solve_tactical_operational_milp(
            bundle,
            solver=case.get("solver", "highs"),
            time_limit=case.get("time_limit"),
            gap=case.get("gap"),
        )
        case_dir = output_root / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        serializable = dict(result)
        for key, value in list(serializable.items()):
            if isinstance(value, pd.DataFrame):
                serializable[key] = value.to_dict("records")
        (case_dir / "result.json").write_text(
            json.dumps(serializable, indent=2, default=str),
            encoding="utf-8",
        )
        write_tactical_report(result, case_dir)
        components = result.get("objective_components") or {}
        summary_rows.append(
            {
                "case_id": case_id,
                "objective": result.get("objective"),
                "termination_condition": result.get("termination_condition"),
                "runtime_s": result.get("runtime_s"),
                **{key: value for key, value in components.items()},
            }
        )
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(output_root / "comparison.csv", index=False)
    (output_root / "comparison.md").write_text(
        _dataframe_to_markdown(summary),
        encoding="utf-8",
    )
    return summary


def write_tactical_report(
    result: dict[str, Any],
    out_dir: str | Path,
    *,
    formats: str = "csv,markdown",
) -> dict[str, Path]:
    """Write normalized tactical result tables and a Markdown objective summary."""
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    requested = {item.strip().lower() for item in formats.split(",") if item.strip()}
    written: dict[str, Path] = {}
    for table_name in (
        "harvest_decisions",
        "production",
        "flows",
        "purchases",
        "inventory",
        "consumption",
        "roads",
        "silviculture",
        "fleet",
    ):
        value = result.get(table_name)
        frame = value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame(value or [])
        if "csv" in requested:
            path = output / f"{table_name}.csv"
            frame.to_csv(path, index=False)
            written[f"{table_name}_csv"] = path
        if "parquet" in requested:
            path = output / f"{table_name}.parquet"
            frame.to_parquet(path, index=False)
            written[f"{table_name}_parquet"] = path
    if "markdown" in requested:
        path = output / "summary.md"
        path.write_text(markdown_tactical_summary(result), encoding="utf-8")
        written["summary_md"] = path
    return written


def markdown_tactical_summary(result: dict[str, Any]) -> str:
    """Render solver status and objective decomposition as a compact Markdown report."""
    components = result.get("objective_components") or {}
    lines = [
        "# Tactical–Operational Plan Summary",
        "",
        f"- Objective: `{result.get('objective')}`",
        f"- Solver status: `{result.get('solver_status')}`",
        f"- Termination: `{result.get('termination_condition')}`",
        f"- Runtime (s): `{result.get('runtime_s')}`",
        "",
        "## Objective components",
        "",
        "| Component | Value |",
        "|---|---:|",
    ]
    for key, value in components.items():
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines) + "\n"


def _dataframe_to_markdown(frame: pd.DataFrame) -> str:
    columns = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "---|" * len(columns),
    ]
    for row in frame.itertuples(index=False):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines) + "\n"


def _deep_merge_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _row_key(section: str, row: dict[str, Any]) -> tuple[Any, ...]:
    fields = _SECTION_ID_FIELDS.get(section)
    if fields is None:
        return (json.dumps(row, sort_keys=True, default=str),)
    if isinstance(fields, str):
        fields = (fields,)
    return tuple(row.get(field) for field in fields)


def _merge_rows(
    section: str,
    base_rows: list[dict[str, Any]],
    overlay_rows: list[dict[str, Any]],
    remove_rows: Any,
) -> list[dict[str, Any]]:
    merged = [deepcopy(row) for row in base_rows]
    remove_ids = set()
    if isinstance(remove_rows, list):
        for item in remove_rows:
            if isinstance(item, dict):
                remove_ids.add(_row_key(section, item))
            else:
                remove_ids.add((item,))
    merged = [row for row in merged if _row_key(section, row) not in remove_ids]
    index = {_row_key(section, row): idx for idx, row in enumerate(merged)}
    for overlay_row in overlay_rows:
        key = _row_key(section, overlay_row)
        if key in index:
            merged[index[key]] = _deep_merge_dict(merged[index[key]], overlay_row)
        else:
            index[key] = len(merged)
            merged.append(deepcopy(overlay_row))
    return merged


def _diff_value(
    prefix: str,
    base: Any,
    candidate: Any,
    rows: list[dict[str, Any]],
) -> None:
    if isinstance(base, dict) and isinstance(candidate, dict):
        for key in sorted(set(base) | set(candidate)):
            _diff_value(
                f"{prefix}.{key}" if prefix else key, base.get(key), candidate.get(key), rows
            )
        return
    if isinstance(base, list) and isinstance(candidate, list):
        base_map = {_stable_key(item): item for item in base}
        candidate_map = {_stable_key(item): item for item in candidate}
        for key in sorted(set(base_map) | set(candidate_map)):
            _diff_value(
                f"{prefix}[{key}]",
                base_map.get(key),
                candidate_map.get(key),
                rows,
            )
        return
    if base != candidate:
        section, _, field = prefix.partition(".")
        rows.append(
            {
                "section": section,
                "key": prefix,
                "field": field or prefix,
                "base_value": base,
                "candidate_value": candidate,
                "change_type": "changed"
                if base is not None and candidate is not None
                else "added_or_removed",
            }
        )


def _stable_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


__all__ = [
    "apply_tactical_overlay_payload",
    "diff_tactical_scenarios",
    "load_tactical_overlay_scenario",
    "markdown_tactical_summary",
    "read_yaml_mapping",
    "scenario_content_hash",
    "solve_tactical_batch_manifest",
    "write_tactical_report",
    "write_tactical_scenario_yaml",
]
