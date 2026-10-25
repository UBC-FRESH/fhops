"""Validated scenario editing for the web UI.

The editor never builds a parallel scenario model. It edits the YAML that the CLI already reads,
loads the result with the same loader, and only then replaces the file. Top-level sections are
replaced in place so comments and ordering elsewhere in the scenario are preserved. Tactical
edits are separate overlays; the base tactical bundle is never rewritten.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from fhops.planning.tactical_operational.scenario import (
    apply_tactical_overlay_payload,
    load_tactical_overlay_scenario,
    write_tactical_scenario_yaml,
)
from fhops.scenario.contract.models import ObjectiveWeights
from fhops.scenario.io import load_scenario

__all__ = [
    "ScenarioEditError",
    "read_editable",
    "save_tactical_overlay",
    "update_hauling",
    "update_locks",
    "update_objective",
]


class ScenarioEditError(ValueError):
    """A scenario edit was refused by the FHOPS loader."""


def read_editable(
    scenario_path: Path,
    *,
    domain: str | None,
    overlay_root: Path,
) -> dict[str, Any]:
    """Return the editable payload for one scenario."""
    scenario_path = scenario_path.resolve()
    if domain == "tactical_operational" or _looks_tactical(scenario_path):
        return _read_tactical(scenario_path, overlay_root=overlay_root)
    scenario = load_scenario(scenario_path)
    payload: dict[str, Any] = {
        "domain": domain or ("hauling" if scenario.hauling is not None else "operational"),
        "path": str(scenario_path),
        "objective_weights": (
            scenario.objective_weights.model_dump(mode="json")
            if scenario.objective_weights is not None
            else None
        ),
        "locked_assignments": [
            lock.model_dump(mode="json") for lock in (scenario.locked_assignments or [])
        ],
    }
    if scenario.hauling is not None:
        payload["hauling"] = {
            "driver_policy": scenario.hauling.driver_policy.model_dump(mode="json"),
            "contractors": [
                contractor.model_dump(mode="json") for contractor in scenario.hauling.contractors
            ],
        }
    return payload


def update_objective(scenario_path: Path, weights: dict[str, Any]) -> dict[str, Any]:
    """Update top-level ``objective_weights`` after loader validation."""
    scenario_path = scenario_path.resolve()
    scenario = load_scenario(scenario_path)
    current = (
        scenario.objective_weights.model_dump(mode="json")
        if scenario.objective_weights is not None
        else ObjectiveWeights().model_dump(mode="json")
    )
    current.update(weights)
    text = _replace_top_level_section(
        scenario_path.read_text(encoding="utf-8"), "objective_weights", current
    )
    _validate_and_replace(scenario_path, text, load_scenario)
    return read_editable(scenario_path, domain="operational", overlay_root=scenario_path.parent)


def update_locks(scenario_path: Path, locks: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace top-level ``locked_assignments`` after loader validation."""
    scenario_path = scenario_path.resolve()
    text = _replace_top_level_section(
        scenario_path.read_text(encoding="utf-8"), "locked_assignments", locks
    )
    _validate_and_replace(scenario_path, text, load_scenario)
    return read_editable(scenario_path, domain="operational", overlay_root=scenario_path.parent)


def update_hauling(
    scenario_path: Path,
    *,
    driver_policy: dict[str, Any] | None = None,
    contractors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Update the inline hauling driver policy or contractor preferred workloads."""
    scenario_path = scenario_path.resolve()
    meta = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
    data_section = meta.get("data") or {}
    if "hauling" in data_section:
        raise ScenarioEditError(
            "This scenario stores hauling in a separate YAML file; edit that file directly."
        )
    scenario = load_scenario(scenario_path)
    if scenario.hauling is None:
        raise ScenarioEditError("This scenario has no hauling section.")
    hauling = scenario.hauling.model_dump(mode="json")
    if driver_policy is not None:
        hauling["driver_policy"] = {**hauling.get("driver_policy", {}), **driver_policy}
    if contractors is not None:
        existing = {row["id"]: row for row in hauling.get("contractors", [])}
        for incoming in contractors:
            contractor_id = incoming.get("id")
            if not contractor_id:
                raise ScenarioEditError("Each contractor edit needs an id.")
            existing[contractor_id] = {**existing.get(contractor_id, {}), **incoming}
        hauling["contractors"] = list(existing.values())
    text = _replace_top_level_section(scenario_path.read_text(encoding="utf-8"), "hauling", hauling)
    _validate_and_replace(scenario_path, text, load_scenario)
    return read_editable(scenario_path, domain="hauling", overlay_root=scenario_path.parent)


def save_tactical_overlay(
    scenario_path: Path,
    overlay: dict[str, Any],
    *,
    overlay_root: Path,
) -> dict[str, Any]:
    """Validate and persist a tactical overlay without rewriting the base bundle."""
    scenario_path = scenario_path.resolve()
    overlay_root = overlay_root.resolve()
    overlay_root.mkdir(parents=True, exist_ok=True)
    overlay = dict(overlay)
    overlay.setdefault("overlay_id", f"{scenario_path.stem}-web")
    target_dir = overlay_root / "_scenarios"
    target_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = target_dir / f"{scenario_path.stem}.overlay.yaml"
    derived_path = target_dir / f"{scenario_path.stem}.overlay.scenario.yaml"

    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=target_dir,
        prefix=".fhops-overlay-",
        suffix=".yaml",
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            yaml.safe_dump(overlay, handle, sort_keys=False, allow_unicode=True)
        validated = load_tactical_overlay_scenario(scenario_path, temp_path)
        write_tactical_scenario_yaml(validated, derived_path)
        os.replace(temp_path, overlay_path)
    except Exception as exc:  # noqa: BLE001 - the loader's message is the user-facing result
        temp_path.unlink(missing_ok=True)
        raise ScenarioEditError(_format_error(exc)) from exc
    return _read_tactical(
        scenario_path,
        overlay_root=overlay_root,
        overlay_path=overlay_path,
        derived_path=derived_path,
    )


def _read_tactical(
    scenario_path: Path,
    *,
    overlay_root: Path,
    overlay_path: Path | None = None,
    derived_path: Path | None = None,
) -> dict[str, Any]:
    base = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
    if not isinstance(base, dict):
        raise ScenarioEditError("Tactical scenario YAML must contain a mapping.")
    overlay_path = (
        overlay_path or overlay_root / "_scenarios" / f"{scenario_path.stem}.overlay.yaml"
    )
    derived_path = (
        derived_path or overlay_root / "_scenarios" / f"{scenario_path.stem}.overlay.scenario.yaml"
    )
    overlay: dict[str, Any] = {}
    if overlay_path.is_file():
        loaded = yaml.safe_load(overlay_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            overlay = loaded
    merged = apply_tactical_overlay_payload(base, overlay)
    return {
        "domain": "tactical_operational",
        "path": str(scenario_path),
        "tactical": {
            "periods": merged.get("periods", []),
            "facility_demand": merged.get("facility_demand", []),
            "overlay": overlay,
            "overlay_path": str(overlay_path),
            "derived_path": str(derived_path),
        },
    }


def _looks_tactical(path: Path) -> bool:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError:
        return False
    return isinstance(payload, dict) and payload.get("planning_level") == "tactical_operational"


def _replace_top_level_section(text: str, key: str, value: Any) -> str:
    """Replace one top-level YAML block, preserving text outside it."""
    lines = text.splitlines()
    pattern = re.compile(rf"^{re.escape(key)}\s*:")
    start = next((index for index, line in enumerate(lines) if pattern.match(line)), None)
    rendered = (
        yaml.safe_dump({key: value}, sort_keys=False, allow_unicode=True, default_flow_style=False)
        .rstrip("\n")
        .splitlines()
    )
    if start is None:
        prefix = text.rstrip("\n")
        return (prefix + "\n\n" if prefix else "") + "\n".join(rendered) + "\n"
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and line[0] not in " \t":
            break
        end += 1
    return "\n".join(lines[:start] + rendered + lines[end:]).rstrip("\n") + "\n"


def _validate_and_replace(path: Path, text: str, loader) -> None:
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=".fhops-edit-",
        suffix=path.suffix,
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(text)
        loader(temp_path)
        os.chmod(temp_path, path.stat().st_mode)
        os.replace(temp_path, path)
    except Exception as exc:  # noqa: BLE001 - the loader's message is the user-facing result
        temp_path.unlink(missing_ok=True)
        raise ScenarioEditError(_format_error(exc)) from exc


def _format_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for error in exc.errors():
            location = ".".join(str(item) for item in error.get("loc", ()))
            parts.append(f"{location}: {error.get('msg', 'invalid value')}")
        return "; ".join(parts) or str(exc)
    return f"{type(exc).__name__}: {exc}"
