"""Case schema, discovery, validation, and pinning for the Tree Lab sandbox.

A case is a directory containing a ``case.json`` manifest plus a FHOPS scenario,
a ``fhops.tree.inventory.v1`` tree list, and an assignments CSV. Every path in
the manifest is relative to the case directory; absolute paths, ``..``
traversal, and symlinks that escape the case root are rejected.

This module does not modify FHOPS. It validates and pins inputs using the
released :mod:`fhops.tree_inventory`, :mod:`fhops.tree_mapping`, and
:mod:`fhops.scenario.io` APIs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CASE_SCHEMA = "fhops.tree_lab.case.v1"
CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
MAX_MANIFEST_BYTES = 64 * 1024
MAX_INVENTORY_BYTES = 16 * 1024 * 1024
REQUIRED_KEYS = (
    "schema_version",
    "case_id",
    "label",
    "block_id",
    "landing_id",
    "scenario",
    "inventory",
    "metadata",
    "system_args",
    "provenance",
)

__all__ = [
    "CASE_SCHEMA",
    "Case",
    "CaseError",
    "discover_cases",
    "load_case",
    "sha256_file",
    "validate_case",
]


class CaseError(RuntimeError):
    """Raised when a case manifest or case directory is unusable."""


@dataclass(frozen=True, slots=True)
class Case:
    """One discovered Tree Lab case.

    Attributes
    ----------
    case_id : str
        Case identifier from the manifest.
    root : Path
        Absolute case directory.
    manifest : dict[str, Any]
        Parsed ``case.json`` payload.
    """

    case_id: str
    root: Path
    manifest: dict[str, Any]

    @property
    def label(self) -> str:
        return str(self.manifest.get("label", self.case_id))

    def path(self, key: str) -> Path:
        """Resolve a manifest path key and refuse escapes from the case root."""
        value = self.manifest.get(key)
        if not isinstance(value, str) or not value:
            raise CaseError(f"Case {self.case_id!r} has no usable {key!r} path.")
        return safe_join(self.root, value)


def safe_join(root: Path, relative: str) -> Path:
    """Join ``relative`` to ``root`` and reject absolute/traversing paths.

    Parameters
    ----------
    root : Path
        Allowlisted root directory.
    relative : str
        Manifest-declared relative path.

    Returns
    -------
    Path
        Resolved path guaranteed to stay inside ``root``.

    Raises
    ------
    CaseError
        If the path is absolute, contains ``..``, or resolves outside ``root``.
    """
    candidate = Path(relative)
    if candidate.is_absolute():
        raise CaseError(f"Absolute paths are not allowed in case manifests: {relative!r}")
    if any(part == ".." for part in candidate.parts):
        raise CaseError(f"Parent traversal is not allowed in case manifests: {relative!r}")
    resolved = (root / candidate).resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise CaseError(f"Path escapes the case root: {relative!r}")
    return resolved


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(case_dir: Path) -> dict[str, Any]:
    manifest_path = case_dir / "case.json"
    if not manifest_path.is_file():
        raise CaseError(f"No case.json in {case_dir}")
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise CaseError(f"case.json exceeds {MAX_MANIFEST_BYTES} bytes: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaseError(f"Cannot read {manifest_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CaseError(f"{manifest_path} must contain a JSON object.")
    return payload


def load_case(case_dir: Path) -> Case:
    """Load and shallow-validate one case directory."""
    case_dir = case_dir.resolve()
    manifest = _load_manifest(case_dir)
    if manifest.get("schema_version") != CASE_SCHEMA:
        raise CaseError(
            f"Unsupported case schema {manifest.get('schema_version')!r}; expected {CASE_SCHEMA}."
        )
    missing = [key for key in REQUIRED_KEYS if key not in manifest]
    if missing:
        raise CaseError(f"Case manifest is missing keys: {', '.join(missing)}")
    case_id = manifest.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise CaseError("case_id must be a non-empty string.")
    if case_id != case_dir.name:
        raise CaseError(f"case_id {case_id!r} does not match directory {case_dir.name!r}.")
    return Case(case_id=case_id, root=case_dir, manifest=manifest)


def discover_cases(root: Path) -> list[Case]:
    """Discover valid cases under ``root``, skipping candidate directories."""
    if not root.is_dir():
        return []
    cases: list[Case] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        try:
            cases.append(load_case(child))
        except CaseError:
            continue
    return cases


def _check_system_args(case: Case) -> list[str]:
    errors: list[str] = []
    args = case.manifest.get("system_args")
    if not isinstance(args, dict):
        return ["system_args must be an object."]
    for key in ("feller", "loader"):
        if not isinstance(args.get(key), str) or not args.get(key):
            errors.append(f"system_args.{key} must be a machine id string.")
    skidders = args.get("skidders")
    if (
        not isinstance(skidders, list)
        or not skidders
        or not all(isinstance(item, str) and item for item in skidders)
    ):
        errors.append("system_args.skidders must be a non-empty list of machine ids.")
    processors = args.get("processors", [])
    if processors is not None and (
        not isinstance(processors, list) or not all(isinstance(item, str) for item in processors)
    ):
        errors.append("system_args.processors must be a list of machine ids.")
    return errors


def validate_case(case: Case, *, run_fhops: bool = True) -> dict[str, Any]:
    """Validate a case manifest, its paths, inventory, and scenario.

    Parameters
    ----------
    case : Case
        Case loaded by :func:`load_case`.
    run_fhops : bool, optional
        When ``True`` (default) also validate the inventory with
        :func:`fhops.tree_inventory.validate_tree_inventory` and load the
        scenario with :func:`fhops.scenario.io.load_scenario`.

    Returns
    -------
    dict[str, Any]
        Report with ``valid``, ``errors``, ``warnings``, file hashes, and
        inventory/scenario summaries.
    """
    errors: list[str] = []
    warnings: list[str] = []
    report: dict[str, Any] = {"case_id": case.case_id, "errors": errors, "warnings": warnings}

    errors.extend(_check_system_args(case))
    block_id = case.manifest.get("block_id")
    if not isinstance(block_id, str) or not block_id.strip():
        errors.append("block_id must be a non-empty string.")
    if not CASE_ID_PATTERN.fullmatch(str(case.manifest.get("case_id", ""))):
        errors.append("case_id must match ^[a-z0-9][a-z0-9-]{1,63}$.")
    try:
        from sandbox.tree_lab.harvest import HarvestError, harvest_prescription

        harvest_prescription(case)
    except (HarvestError, ValueError) as exc:
        errors.append(f"Invalid harvest prescription: {exc}")

    paths: dict[str, Path] = {}
    for key in ("scenario", "inventory", "metadata"):
        try:
            paths[key] = case.path(key)
        except CaseError as exc:
            errors.append(str(exc))
            continue
        if not paths[key].is_file():
            errors.append(f"{key} file is missing: {paths[key]}")
        elif paths[key].stat().st_size > MAX_INVENTORY_BYTES:
            errors.append(f"{key} file exceeds the {MAX_INVENTORY_BYTES} byte limit.")
    if "assignments" in case.manifest:
        try:
            paths["assignments"] = case.path("assignments")
        except CaseError as exc:
            errors.append(str(exc))
        else:
            if not paths["assignments"].is_file():
                errors.append(f"assignments file is missing: {paths['assignments']}")

    hashes: dict[str, str] = {}
    for key, path in paths.items():
        if path.is_file():
            hashes[key] = sha256_file(path)
    report["hashes"] = hashes

    if errors or not run_fhops or "inventory" not in paths or "scenario" not in paths:
        report["valid"] = not errors
        return report

    from fhops.scenario.io import load_scenario
    from fhops.tree_inventory import TreeInventoryError, validate_tree_inventory

    block_ids = {str(case.manifest.get("block_id"))}
    try:
        inventory_report = validate_tree_inventory(
            paths["inventory"],
            metadata_path=paths.get("metadata"),
            block_ids=block_ids,
        )
    except (TreeInventoryError, OSError, ValueError) as exc:
        errors.append(f"Inventory validation failed: {exc}")
    else:
        report["inventory"] = {
            "valid": inventory_report.is_valid,
            "tree_count": inventory_report.tree_count,
            "errors": list(inventory_report.errors),
        }
        errors.extend(inventory_report.errors)

    try:
        scenario = load_scenario(paths["scenario"])
    except Exception as exc:  # noqa: BLE001 - FHOPS raises several types
        errors.append(f"Scenario load failed: {exc}")
    else:
        report["scenario"] = {
            "name": scenario.name,
            "num_days": scenario.num_days,
            "block_ids": sorted(scenario.block_ids()),
            "machine_ids": sorted(machine.id for machine in scenario.machines),
        }
        if case.manifest.get("block_id") not in scenario.block_ids():
            errors.append(f"Block {case.manifest.get('block_id')!r} is not in the scenario.")
        if scenario.tree_inventory is None:
            warnings.append(
                "Scenario is not pinned to a tree inventory yet; it will be pinned on first run."
            )

    report["valid"] = not errors
    return report


def ensure_pinned(case: Case) -> dict[str, Any]:
    """Pin the case inventory into its scenario, keeping relative paths.

    Runs :func:`fhops.tree_mapping.register_tree_inventory`, rewrites the
    generated absolute paths to paths relative to the scenario directory, and
    verifies the scenario still loads.

    Returns
    -------
    dict[str, Any]
        ``{"pinned": bool, "inventory_id": str, "changed": bool}``.
    """
    from fhops.scenario.io import load_scenario
    from fhops.tree_mapping import register_tree_inventory

    scenario_path = case.path("scenario")
    inventory_path = case.path("inventory")
    metadata_path = case.path("metadata")
    scenario = load_scenario(scenario_path)
    if scenario.tree_inventory is not None:
        changed = _relativize_pin(scenario_path, inventory_path, metadata_path)
        return {
            "pinned": True,
            "inventory_id": scenario.tree_inventory.inventory_id,
            "changed": changed,
        }

    result = register_tree_inventory(
        scenario_path,
        inventory_path,
        metadata_path=metadata_path,
    )
    _relativize_pin(scenario_path, inventory_path, metadata_path)
    reloaded = load_scenario(scenario_path)
    if reloaded.tree_inventory is None:
        raise CaseError("Pinning failed: scenario has no tree_inventory section.")
    return {
        "pinned": True,
        "inventory_id": result.inventory_id,
        "changed": True,
    }


def _relativize_pin(scenario_path: Path, inventory_path: Path, metadata_path: Path) -> bool:
    """Rewrite absolute pin paths to scenario-relative paths when needed."""
    from fhops.scenario.io import load_scenario

    scenario = load_scenario(scenario_path)
    pin = scenario.tree_inventory
    if pin is None:
        return False
    if not (Path(pin.inventory_path).is_absolute() or Path(pin.metadata_path).is_absolute()):
        return False
    text = scenario_path.read_text(encoding="utf-8")
    replacements = (
        (pin.inventory_path, os.path.relpath(inventory_path, scenario_path.parent)),
        (pin.metadata_path, os.path.relpath(metadata_path, scenario_path.parent)),
    )
    for absolute, relative in replacements:
        text = text.replace(absolute, relative)
    scenario_path.write_text(text, encoding="utf-8")
    load_scenario(scenario_path)
    return True
