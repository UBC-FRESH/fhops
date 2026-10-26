"""Read-only LiDAR evidence payloads for the web UI.

The service reads the scenario's committed ``lidar_products`` and ``lidar_support`` sections and
the P14.4 advisory operability report. It never discovers, downloads, or processes source LiDAR, and
it does not import the optional GeoPandas/rasterio stack.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from fhops.scenario.io import load_scenario
from fhops.scenario.lidar_operability import assess_scenario_operability
from fhops.web.discovery import RunRecord

__all__ = ["lidar_map_values", "lidar_payload", "scenario_path_for_run"]

_OGL_BC_URL = "https://www2.gov.bc.ca/gov/content/data/open-data/open-government-licence-bc"
_OGL_BC_ATTRIBUTION = (
    "Contains information licensed under the Open Government Licence - British Columbia."
)


def scenario_path_for_run(record: RunRecord, workspace: Path | None = None) -> Path | None:
    """Resolve the scenario path recorded in ``run.json``."""
    value = (record.manifest or {}).get("scenario")
    if not value:
        return None
    raw = Path(str(value)).expanduser()
    candidates = [raw] if raw.is_absolute() else []
    if workspace is not None and not raw.is_absolute():
        candidates.append(workspace / raw)
    if not raw.is_absolute():
        candidates.extend([Path.cwd() / raw, record.path / raw])
    return next((path.resolve() for path in candidates if path.is_file()), None)


def lidar_payload(record: RunRecord, workspace: Path | None = None) -> dict[str, Any]:
    """Build the read-only LiDAR panel payload for one run."""
    scenario_path = scenario_path_for_run(record, workspace)
    if scenario_path is None:
        return _empty_payload(record, "Run manifest has no readable scenario path.")
    try:
        scenario = load_scenario(scenario_path)
    except Exception as exc:  # noqa: BLE001 - the loader message is the UI result
        return _empty_payload(record, f"Scenario could not be loaded: {exc}")
    pins = [pin.model_dump(mode="json", exclude_none=True) for pin in scenario.lidar_products or []]
    support = list(scenario.lidar_support or [])
    if not pins and not support:
        return _empty_payload(record, "Scenario has no lidar_products or lidar_support sections.")
    operability = {row.block_id: row.to_dict() for row in assess_scenario_operability(scenario)}
    support_by_block: dict[str, list[dict[str, Any]]] = {}
    support_by_landing: dict[str, list[dict[str, Any]]] = {}
    for row in support:
        item = row.model_dump(mode="json", exclude_none=True)
        if row.support_unit == "block":
            support_by_block.setdefault(row.support_id, []).append(item)
        elif row.support_unit == "landing":
            support_by_landing.setdefault(row.support_id, []).append(item)
    blocks = []
    for block in scenario.blocks:
        block_rows = support_by_block.get(block.id, [])
        landing_rows = support_by_landing.get(block.landing_id, [])
        blocks.append(
            {
                "block_id": block.id,
                "landing_id": block.landing_id,
                "support": block_rows,
                "landing_support": landing_rows,
                "operability": operability.get(block.id),
                "has_support": bool(block_rows),
                "slope_percent": _first_value(block_rows, "slope_percent"),
                "canopy_height_m": _first_value(block_rows, "canopy_height_m"),
                "terrain_class": operability.get(block.id, {}).get("terrain_class"),
            }
        )
    warnings = _warnings(scenario, pins, support, blocks, scenario_path)
    classes = Counter(
        row.get("terrain_class") for row in operability.values() if row.get("terrain_class")
    )
    products = sorted({row.product for row in support})
    return {
        "run_id": record.run_id,
        "domain": record.domain,
        "scenario_path": str(scenario_path),
        "available": bool(pins or support),
        "support_available": bool(support),
        "scenario_crs": scenario.geo.crs if scenario.geo is not None else None,
        "bundle": _bundle_payload(pins, scenario_path),
        "pins": pins,
        "products": products,
        "blocks": blocks,
        "coverage": {
            "blocks": len(blocks),
            "blocks_with_support": sum(1 for block in blocks if block["has_support"]),
            "support_rows": len(support),
            "fallback_blocks": sum(
                1 for block in blocks if (block.get("operability") or {}).get("fallbacks")
            ),
            "terrain_classes": dict(sorted(classes.items())),
        },
        "warnings": warnings,
    }


def lidar_map_values(record: RunRecord, workspace: Path | None = None) -> dict[str, dict[str, Any]]:
    """Return block-level values for LiDAR map layers."""
    payload = lidar_payload(record, workspace)
    values: dict[str, dict[str, Any]] = {}
    for block in payload.get("blocks", []):
        op = block.get("operability") or {}
        support = block.get("support") or []
        first = support[0] if support else {}
        values[str(block["block_id"])] = {
            "block_id": block["block_id"],
            "slope_percent": block.get("slope_percent"),
            "canopy_height_m": block.get("canopy_height_m"),
            "terrain_class": block.get("terrain_class"),
            "current_system_id": op.get("current_system_id"),
            "current_system_compatible": op.get("current_system_compatible"),
            "recommended_system_id": op.get("recommended_system_id"),
            "fallbacks": op.get("fallbacks") or [],
            "native_resolution_m": first.get("native_resolution_m"),
            "provenance": first.get("provenance"),
            "has_support": bool(support),
        }
    return values


def _empty_payload(record: RunRecord, warning: str) -> dict[str, Any]:
    return {
        "run_id": record.run_id,
        "domain": record.domain,
        "scenario_path": str(scenario_path_for_run(record) or ""),
        "available": False,
        "support_available": False,
        "scenario_crs": None,
        "bundle": None,
        "pins": [],
        "products": [],
        "blocks": [],
        "coverage": {
            "blocks": 0,
            "blocks_with_support": 0,
            "support_rows": 0,
            "fallback_blocks": 0,
            "terrain_classes": {},
        },
        "warnings": [warning],
    }


def _bundle_payload(pins: list[dict[str, Any]], scenario_path: Path) -> dict[str, Any] | None:
    if not pins:
        return None
    pin = pins[0]
    manifest_path = pin.get("manifest_path")
    available = False
    reason = "No manifest path recorded in the scenario pin."
    if manifest_path:
        candidate = Path(str(manifest_path)).expanduser()
        if not candidate.is_absolute():
            candidate = scenario_path.parent / candidate
        candidate = candidate.resolve()
        if candidate.is_file() and (
            candidate.is_relative_to(scenario_path.parent)
            or candidate.is_relative_to(Path.cwd().resolve())
        ):
            available = True
            reason = "Manifest file is present."
        else:
            reason = "Manifest is missing or outside the scenario directory."
    licence_id = pin.get("licence_id")
    return {
        "bundle_id": pin.get("bundle_id"),
        "bundle_version": pin.get("bundle_version"),
        "manifest_sha256": pin.get("manifest_sha256"),
        "licence_id": licence_id,
        "licence_url": _OGL_BC_URL if licence_id == "OGL-BC" else None,
        "attribution": _OGL_BC_ATTRIBUTION if licence_id == "OGL-BC" else None,
        "crs": pin.get("crs"),
        "manifest_available": available,
        "manifest_status": reason,
        "products": pin.get("products") or [],
        "selection": pin.get("selection"),
    }


def _warnings(scenario, pins, support, blocks, scenario_path: Path) -> list[str]:
    warnings: list[str] = []
    if not pins:
        warnings.append("No lidar_products pin is recorded in the scenario.")
    if not support:
        warnings.append("No lidar_support rows are recorded in the scenario.")
    missing = [block["block_id"] for block in blocks if not block["has_support"]]
    if missing:
        warnings.append("Blocks without LiDAR support: " + ", ".join(missing))
    bundle = _bundle_payload(pins, scenario_path) if pins else None
    if bundle is not None and not bundle.get("manifest_available"):
        warnings.append("The pinned bundle manifest is not available in this checkout.")
    if any((block.get("operability") or {}).get("fallbacks") for block in blocks):
        warnings.append("Some blocks use labelled class-average fallbacks.")
    return warnings


def _first_value(rows: list[dict[str, Any]], key: str) -> Any:
    for row in rows:
        value = row.get(key)
        if value is not None:
            return value
    return None
