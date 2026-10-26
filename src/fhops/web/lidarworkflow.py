"""LiDAR bundle validation, registration, and mapping actions for the web service.

Bundle validation and scenario registration are core FHOPS operations. Mapping runs through the
CLI subprocess so the request process never imports GeoPandas/rasterio. Bundle roots and scenario
paths are allowlisted.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from fhops.scenario.lidar import validate_femic_lidar_bundle
from fhops.scenario.lidar_registration import (
    FemicLidarRegistrationError,
    register_femic_lidar_bundle,
)
from fhops.web.discovery import RunRecord
from fhops.web.lidarview import scenario_path_for_run

__all__ = [
    "LidarBundleRequest",
    "LidarMapRequest",
    "LidarWorkflowError",
    "list_bundles",
    "map_bundle_products",
    "register_bundle",
    "resolve_bundle",
    "validate_bundle",
]


class LidarWorkflowError(RuntimeError):
    """A LiDAR web action cannot be completed safely."""


class LidarBundleRequest(BaseModel):
    """A bundle action request."""

    bundle: str
    expected_bundle_id: str | None = None
    expected_bundle_version: str | None = None


class LidarRegisterRequest(LidarBundleRequest):
    """Register a bundle pin; optional dry-run."""

    dry_run: bool = False


class LidarMapRequest(LidarBundleRequest):
    """Map bundle products into the scenario's support rows."""

    products: dict[str, str] | None = None
    statistic: str = "mean"
    include_blocks: bool = True
    include_landings: bool = True
    roads_geojson: str | None = None
    dry_run: bool = False


def list_bundles(roots: list[Path]) -> dict[str, Any]:
    """List manifest-bearing bundle directories under the configured roots."""
    entries: list[dict[str, str]] = []
    normalized_roots = [root.expanduser().resolve() for root in roots]
    for root in normalized_roots:
        if not root.is_dir():
            continue
        candidates = [root, *sorted(path for path in root.iterdir() if path.is_dir())]
        for candidate in candidates:
            manifest = candidate / "manifest.json"
            if not manifest.is_file():
                continue
            try:
                name = str(candidate.relative_to(root)) if candidate != root else "."
            except ValueError:  # pragma: no cover - defensive
                name = candidate.name
            entries.append({"name": name, "root": str(root)})
    return {
        "roots": [str(root) for root in normalized_roots],
        "bundles": entries,
    }


def resolve_bundle(value: str, roots: list[Path]) -> Path:
    """Resolve a bundle name under the configured roots."""
    if not roots:
        raise LidarWorkflowError(
            "No LiDAR bundle roots configured; start fhops web with --lidar-bundles <dir>."
        )
    raw = Path(value).expanduser()
    normalized_roots = [root.expanduser().resolve() for root in roots]
    candidates = [raw] if raw.is_absolute() else []
    if not raw.is_absolute():
        candidates.extend(root / raw for root in normalized_roots)
    for candidate in candidates:
        path = candidate.resolve()
        if not any(path.is_relative_to(root) for root in normalized_roots):
            continue
        if not path.is_dir():
            continue
        if not (path / "manifest.json").is_file():
            continue
        return path
    names = ", ".join(str(root) for root in normalized_roots)
    raise LidarWorkflowError(f"Bundle {value!r} was not found under the configured roots: {names}")


def validate_bundle(
    bundle_path: Path,
    *,
    expected_bundle_id: str | None = None,
    expected_bundle_version: str | None = None,
) -> dict[str, Any]:
    """Validate a bundle and return the report."""
    report = validate_femic_lidar_bundle(bundle_path)
    if (expected_bundle_id or expected_bundle_version) and report.is_valid:
        # Use the full loader for the expected-pin check, but keep the report shape.
        from fhops.scenario.lidar import load_femic_lidar_bundle

        try:
            load_femic_lidar_bundle(
                bundle_path,
                expected_bundle_id=expected_bundle_id,
                expected_bundle_version=expected_bundle_version,
            )
        except Exception as exc:  # noqa: BLE001 - user-facing validation message
            return {**report.to_dict(), "is_valid": False, "errors": [str(exc)]}
    return report.to_dict()


def register_bundle(
    scenario_path: Path,
    bundle_path: Path,
    *,
    expected_bundle_id: str | None = None,
    expected_bundle_version: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Register a bundle pin in a scenario."""
    try:
        result = register_femic_lidar_bundle(
            scenario_path,
            bundle_path,
            expected_bundle_id=expected_bundle_id,
            expected_bundle_version=expected_bundle_version,
            dry_run=dry_run,
        )
    except FemicLidarRegistrationError as exc:
        raise LidarWorkflowError(str(exc)) from exc
    return result.to_dict()


def map_bundle_products(
    scenario_path: Path,
    bundle_path: Path,
    *,
    workspace: Path,
    cli_command: tuple[str, ...],
    request: LidarMapRequest,
    timeout: float = 300.0,
) -> dict[str, Any]:
    """Run ``fhops scenario lidar map`` in a subprocess and return its JSON result."""
    command = list(cli_command) + [
        "scenario",
        "lidar",
        "map",
        str(scenario_path),
        str(bundle_path),
        "--statistic",
        request.statistic,
    ]
    if request.products:
        for field, product in sorted(request.products.items()):
            command.extend(["--product", f"{field}={product}"])
    if not request.include_blocks:
        command.append("--no-include-blocks")
    if not request.include_landings:
        command.append("--no-include-landings")
    if request.roads_geojson:
        command.extend(["--roads-geojson", request.roads_geojson])
    if request.dry_run:
        command.append("--dry-run")
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LidarWorkflowError(f"LiDAR mapping timed out after {timeout:g} s") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-3000:]
        raise LidarWorkflowError(detail or f"LiDAR mapping exited {completed.returncode}")
    try:
        payload = json.loads(completed.stdout)
    except ValueError as exc:
        raise LidarWorkflowError(
            "The mapping command did not return JSON: " + completed.stdout[-1000:]
        ) from exc
    if not isinstance(payload, dict):
        raise LidarWorkflowError("The mapping command returned a non-object JSON payload.")
    return payload


def scenario_for_run(record: RunRecord, workspace: Path, roots: list[Path]) -> Path:
    """Resolve a run scenario and require it to stay inside the allowed roots."""
    path = scenario_path_for_run(record, workspace)
    if path is None:
        raise LidarWorkflowError("Run manifest has no readable scenario path.")
    allowed = [workspace.expanduser().resolve(), *[root.expanduser().resolve() for root in roots]]
    if not any(path.is_relative_to(root) for root in allowed):
        raise LidarWorkflowError("Scenario path escapes the allowed workspace/run roots.")
    return path
