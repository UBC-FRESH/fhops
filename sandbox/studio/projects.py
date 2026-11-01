"""Project storage and derived editor data for FHOPS Scenario Studio.

The Studio is an authoring layer over immutable Tree Lab cases.  A project
stores only edits and references its base case; source fixtures under
``sandbox/cases`` are never modified by this module.
"""

from __future__ import annotations

import csv
import json
import math
import re
import secrets
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fhops.stem import ReferenceStemModel
from fhops.tree_inventory import TreeInventory, load_tree_inventory
from sandbox.tree_lab.cases import Case, load_case, sha256_file
from sandbox.tree_lab.harvest import INVENTORY_FIELDS

PROJECT_SCHEMA = "fhops.studio.project.v1"
PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
MAX_PROJECT_BYTES = 2 * 1024 * 1024
POLICY_PRESETS: dict[str, dict[str, Any]] = {
    "steady": {
        "label": "Steady / Standard",
        "cycle_multiplier": 1.0,
        "setup_delay_s": 0.0,
        "break_policy": "standard",
        "grade_caution": "normal",
        "damage_risk": "normal",
        "breakdown_risk": "normal",
    },
    "throughput": {
        "label": "Throughput",
        "cycle_multiplier": 0.92,
        "setup_delay_s": -30.0,
        "break_policy": "minimal",
        "grade_caution": "relaxed",
        "damage_risk": "elevated",
        "breakdown_risk": "elevated",
    },
    "careful": {
        "label": "Careful / Quality",
        "cycle_multiplier": 1.12,
        "setup_delay_s": 30.0,
        "break_policy": "standard",
        "grade_caution": "high",
        "damage_risk": "low",
        "breakdown_risk": "low",
    },
    "terrain": {
        "label": "Terrain-cautious",
        "cycle_multiplier": 1.08,
        "setup_delay_s": 20.0,
        "break_policy": "standard",
        "grade_caution": "high",
        "damage_risk": "low",
        "breakdown_risk": "normal",
    },
    "maintenance": {
        "label": "Maintenance-first",
        "cycle_multiplier": 1.03,
        "setup_delay_s": 10.0,
        "break_policy": "planned",
        "grade_caution": "normal",
        "damage_risk": "normal",
        "breakdown_risk": "low",
    },
    "greenhorn": {
        "label": "Greenhorn",
        "cycle_multiplier": 1.18,
        "setup_delay_s": 45.0,
        "break_policy": "standard",
        "grade_caution": "high",
        "damage_risk": "high",
        "breakdown_risk": "elevated",
    },
    "expert": {
        "label": "Expert",
        "cycle_multiplier": 0.95,
        "setup_delay_s": -15.0,
        "break_policy": "standard",
        "grade_caution": "normal",
        "damage_risk": "low",
        "breakdown_risk": "low",
    },
}


class StudioError(RuntimeError):
    """Raised when a Studio project cannot be loaded, validated, or saved."""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _project_id(case_id: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S").lower()
    return f"{case_id}-{stamp}-{secrets.token_hex(2)}"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _machine_catalog(case: Case) -> list[dict[str, str]]:
    path = case.root / "scenario" / "data" / "machines.csv"
    if not path.is_file():
        return []
    return [
        {"id": row["id"], "role": row["role"]}
        for row in _read_csv(path)
        if row.get("id") and row.get("role")
    ]


def _normalize_role(role: str) -> str:
    return {"skyline_yarder": "cable_yarder"}.get(role, role)


def _active_machines(case: Case, catalog: list[dict[str, str]]) -> list[dict[str, Any]]:
    args = case.manifest.get("system_args") or {}
    roles = {item["id"]: item["role"] for item in catalog}
    ids: list[str] = []
    for key in ("feller", "loader"):
        if args.get(key):
            ids.append(str(args[key]))
    ids.extend(str(value) for value in args.get("skidders") or [])
    ids.extend(str(value) for value in args.get("processors") or [])
    result = []
    for machine_id in dict.fromkeys(ids):
        role = _normalize_role(roles.get(machine_id, "machine"))
        result.append(
            {
                "id": machine_id,
                "role": role,
                "type": role,
                "policy": "steady",
                "source": "base",
            }
        )
    return result


def _block_polygon(case: Case, inventory: TreeInventory) -> list[list[float]]:
    if case.manifest.get("footprint"):
        try:
            payload = json.loads(case.path("footprint").read_text(encoding="utf-8"))
            features = (
                payload.get("features") if payload.get("type") == "FeatureCollection" else [payload]
            )
            geometry = (features or [{}])[0].get("geometry") or {}
            coords = geometry.get("coordinates") or []
            if geometry.get("type") == "Polygon":
                ring = coords[0]
            elif geometry.get("type") == "MultiPolygon":
                ring = coords[0][0]
            else:
                ring = []
            polygon = [[float(point[0]), float(point[1])] for point in ring]
            if len(polygon) > 1 and polygon[0] == polygon[-1]:
                polygon = polygon[:-1]
            if len(polygon) >= 3:
                return polygon
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            pass
    xs = [tree.x_m for tree in inventory.rows]
    ys = [tree.y_m for tree in inventory.rows]
    if not xs or not ys:
        return []
    pad = 1.5
    return [
        [min(xs) - pad, min(ys) - pad],
        [max(xs) + pad, min(ys) - pad],
        [max(xs) + pad, max(ys) + pad],
        [min(xs) - pad, max(ys) + pad],
    ]


def _edge_landing(case: Case, inventory: TreeInventory) -> dict[str, float]:
    cable = case.manifest.get("cable") or {}
    yarder = cable.get("yarder") if isinstance(cable, dict) else None
    if isinstance(yarder, dict) and "x" in yarder and "y" in yarder:
        return {"x": float(yarder["x"]), "y": float(yarder["y"])}
    xs = [tree.x_m for tree in inventory.rows]
    ys = [tree.y_m for tree in inventory.rows]
    if not xs or not ys:
        return {"x": 0.0, "y": 0.0}
    return {"x": max(xs) - 45.0, "y": min(ys) - 28.0}


def _road_for_landing(polygon: list[list[float]], landing: dict[str, float]) -> dict[str, Any]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    if not xs or not ys:
        return {"points": [], "width_m": 10.0}
    road_y = min(min(ys) - 12.0, landing["y"])
    return {
        "points": [[min(xs) - 60.0, road_y], [max(xs) + 60.0, road_y]],
        "width_m": 10.0,
    }


def _system_args(case: Case) -> dict[str, Any]:
    return json.loads(json.dumps(case.manifest.get("system_args") or {}))


def create_project(case: Case) -> dict[str, Any]:
    """Create a new project from an existing Tree Lab case."""
    inventory = load_tree_inventory(case.path("inventory"), metadata_path=case.path("metadata"))
    polygon = _block_polygon(case, inventory)
    catalog = _machine_catalog(case)
    landing = _edge_landing(case, inventory)
    road = _road_for_landing(polygon, landing)
    return {
        "schema_version": PROJECT_SCHEMA,
        "project_id": _project_id(case.case_id),
        "label": f"{case.label} — Studio edit",
        "base_case_id": case.case_id,
        "block_id": str(case.manifest.get("block_id", "")),
        "revision": 1,
        "created_utc": _now(),
        "updated_utc": _now(),
        "block": {
            "polygon": polygon,
            "base_polygon": json.loads(json.dumps(polygon)),
            "source": "base",
        },
        "landing": landing,
        "road": road,
        "retention": {"tree_ids": [], "target_fraction_basal_area": 0.0},
        "machines": _active_machines(case, catalog),
        "catalog": catalog,
        "system_args": _system_args(case),
        "operator_policies": {item["id"]: "steady" for item in _active_machines(case, catalog)},
        "terrain": {
            "resolution": 24,
            "heights": [],
            "note": "Visual terrain edits; simulation hook pending.",
        },
        "notes": "",
    }


def project_path(root: Path, project_id: str) -> Path:
    """Resolve and validate a project directory."""
    if not PROJECT_ID_RE.match(project_id):
        raise StudioError("Invalid project id.")
    path = (root / project_id).resolve()
    if root.resolve() not in path.parents:
        raise StudioError("Project path escapes the Studio root.")
    return path


def load_project(root: Path, project_id: str) -> dict[str, Any]:
    """Load one project JSON document."""
    path = project_path(root, project_id) / "project.json"
    if not path.is_file():
        raise StudioError(f"Unknown project {project_id!r}.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StudioError(f"Project {project_id!r} is unreadable.") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != PROJECT_SCHEMA:
        raise StudioError("Unsupported Studio project schema.")
    return payload


def save_project(root: Path, project: dict[str, Any]) -> dict[str, Any]:
    """Validate and atomically save a project."""
    if not isinstance(project, dict):
        raise StudioError("Project payload must be an object.")
    project_id = str(project.get("project_id", ""))
    path = project_path(root, project_id) / "project.json"
    polygon = (
        project.get("block", {}).get("polygon") if isinstance(project.get("block"), dict) else None
    )
    if not isinstance(polygon, list) or len(polygon) < 3:
        raise StudioError("Block boundary needs at least three points.")
    if not isinstance(project.get("landing"), dict):
        raise StudioError("Project needs a landing.")
    machines = project.get("machines")
    if not isinstance(machines, list):
        raise StudioError("Project machines must be a list.")
    sync_system_args(project)
    project["updated_utc"] = _now()
    project["revision"] = int(project.get("revision") or 0) + 1
    encoded = json.dumps(project, indent=2) + "\n"
    if len(encoded.encode("utf-8")) > MAX_PROJECT_BYTES:
        raise StudioError("Project exceeds the 2 MiB size limit.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)
    return project


def list_projects(root: Path) -> list[dict[str, Any]]:
    """Return lightweight project summaries, newest first."""
    if not root.is_dir():
        return []
    summaries = []
    for path in sorted(root.glob("*/project.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        summaries.append(
            {
                "project_id": payload.get("project_id"),
                "label": payload.get("label"),
                "base_case_id": payload.get("base_case_id"),
                "revision": payload.get("revision"),
                "updated_utc": payload.get("updated_utc"),
            }
        )
    return summaries


def _point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    inside = False
    if len(polygon) < 3:
        return False
    j = len(polygon) - 1
    for i, point in enumerate(polygon):
        xi, yi = float(point[0]), float(point[1])
        xj, yj = float(polygon[j][0]), float(polygon[j][1])
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def polygon_area_ha(polygon: list[list[float]]) -> float:
    """Return polygon area in hectares using the shoelace formula."""
    if len(polygon) < 3:
        return 0.0
    area = 0.0
    for index, point in enumerate(polygon):
        nxt = polygon[(index + 1) % len(polygon)]
        area += float(point[0]) * float(nxt[1]) - float(nxt[0]) * float(point[1])
    return abs(area) / 2.0 / 10000.0


def sync_system_args(project: dict[str, Any]) -> dict[str, Any]:
    """Synchronize the active machine list into Tree Lab system arguments."""
    args = json.loads(json.dumps(project.get("system_args") or {}))
    machines = project.get("machines") or []
    roles = [
        (str(item.get("id")), str(item.get("role", ""))) for item in machines if item.get("id")
    ]
    feller = next(
        (
            machine
            for machine, role in roles
            if role in {"feller_buncher", "harvester", "hand_faller"}
        ),
        None,
    )
    loader = next((machine for machine, role in roles if role == "loader"), None)
    if not feller or not loader:
        raise StudioError("The system needs one feller/harvester and one loader.")
    args["feller"] = feller
    args["loader"] = loader
    args["skidders"] = [
        machine
        for machine, role in roles
        if role in {"grapple_skidder", "skidder", "forwarder", "cable_yarder", "skyline_yarder"}
    ]
    args["processors"] = [
        machine for machine, role in roles if role in {"roadside_processor", "processor"}
    ]
    policy = project.get("operator_policies", {}).get(feller, "steady")
    preset = POLICY_PRESETS.get(policy, POLICY_PRESETS["steady"])
    args["feller_productivity_multiplier"] = 1.0 / max(0.5, float(preset["cycle_multiplier"]))
    project["system_args"] = args
    return args


def _terrain_elevation(project: dict[str, Any], base: float, x: float, y: float) -> float:
    terrain = project.get("terrain") or {}
    heights = terrain.get("heights") or []
    bounds = terrain.get("bounds")
    if not heights or not isinstance(bounds, list) or len(bounds) != 4:
        return base
    min_x, min_y, max_x, max_y = (float(value) for value in bounds)
    res = max(2, int(terrain.get("resolution") or 24))
    fx = max(0.0, min(res - 1, (x - min_x) / max(1e-9, max_x - min_x) * (res - 1)))
    fy = max(0.0, min(res - 1, (y - min_y) / max(1e-9, max_y - min_y) * (res - 1)))
    x0, y0 = int(fx), int(fy)
    x1, y1 = min(res - 1, x0 + 1), min(res - 1, y0 + 1)
    dx, dy = fx - x0, fy - y0
    h00 = float(heights[y0 * res + x0] or 0.0)
    h10 = float(heights[y0 * res + x1] or 0.0)
    h01 = float(heights[y1 * res + x0] or 0.0)
    h11 = float(heights[y1 * res + x1] or 0.0)
    return base + (h00 * (1 - dx) + h10 * dx) * (1 - dy) + (h01 * (1 - dx) + h11 * dx) * dy


def _write_project_inventory(
    rows: list[Any],
    directory: Path,
    case_id: str,
    *,
    elevation_fn: Callable[[float, float], float] | None = None,
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    inventory = directory / "tree_inventory.csv"
    with inventory.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INVENTORY_FIELDS, lineterminator="\n")
        writer.writeheader()
        for tree in rows:
            writer.writerow(
                {
                    "tree_id": tree.tree_id,
                    "block_id": tree.block_id,
                    "x_m": tree.x_m,
                    "y_m": tree.y_m,
                    "elevation_m": tree.elevation_m,
                    "species_code": tree.species_code,
                    "dbh_cm": tree.dbh_cm,
                    "height_m": tree.height_m,
                    "crown_radius_m": tree.crown_radius_m,
                    "status": tree.status,
                    "confidence": tree.confidence,
                    "source_id": tree.source_id,
                    "source_tile_id": tree.source_tile_id,
                    "merchantable_height_m": "",
                    "defect": "",
                    "grade_hint": "",
                }
            )
    metadata = {
        "schema_version": "fhops.tree.inventory.v1",
        "inventory_id": f"{case_id}-studio",
        "generated_utc": _now(),
        "source_id": f"studio-{case_id}",
        "producer": "FHOPS Scenario Studio",
        "method": "Boundary and retention filtered from an immutable base case.",
        "crs": "EPSG:3005",
        "units": {"x_y": "m", "elevation": "m", "dbh": "cm", "height": "m", "crown_radius": "m"},
        "review_status": "not_reviewed",
        "block_ids": sorted({tree.block_id for tree in rows}),
        "tree_count": len(rows),
        "inventory_sha256": sha256_file(inventory),
        "caveats": ["Studio-derived inventory; not a surveyed stand or operational plan."],
    }
    meta_path = directory / "tree_inventory.meta.json"
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return inventory, meta_path


def materialize_case(project_root: Path, project: dict[str, Any], base_case: Case) -> Case:
    """Create a disposable case directory for running an edited project."""
    project_id = str(project["project_id"])
    root = project_path(project_root, project_id) / "derived_cases" / str(base_case.case_id)
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(base_case.root, root)
    inventory = load_tree_inventory(
        base_case.path("inventory"), metadata_path=base_case.path("metadata")
    )
    polygon = project.get("block", {}).get("polygon") or []
    retained = set(project.get("retention", {}).get("tree_ids") or [])
    rows = [
        tree
        for tree in inventory.rows
        if tree.tree_id not in retained and _point_in_polygon(tree.x_m, tree.y_m, polygon)
    ]
    residual_rows = [
        tree
        for tree in inventory.rows
        if tree.tree_id in retained and _point_in_polygon(tree.x_m, tree.y_m, polygon)
    ]
    if not rows:
        raise StudioError("The edited block and retention rules leave no harvestable trees.")
    terrain = project.get("terrain") or {}
    heights = terrain.get("heights") or []
    base_elevation = min(
        (float(tree.elevation_m) for tree in inventory.rows if tree.elevation_m is not None),
        default=0.0,
    )
    elevation_fn = None
    if heights:
        base_elevation = float(terrain.get("base_m") or base_elevation)

        def elevation_fn(x: float, y: float) -> float:
            return _terrain_elevation(project, base_elevation, x, y)

    inv_path, meta_path = _write_project_inventory(
        rows, root / "tree_inventory", str(base_case.case_id), elevation_fn=elevation_fn
    )
    manifest = json.loads((base_case.root / "case.json").read_text(encoding="utf-8"))
    manifest["label"] = str(project.get("label") or manifest.get("label"))
    manifest["inventory"] = str(inv_path.relative_to(root))
    manifest["metadata"] = str(meta_path.relative_to(root))
    manifest["harvest"] = {
        "type": "clear_cut",
        "marking_rule": "all",
        "target_basal_area_fraction": 1.0,
    }
    manifest["landing"] = project.get("landing")
    manifest["studio_project_id"] = project_id
    if heights:
        try:
            import numpy as np
            import rasterio
            from rasterio.transform import from_origin

            bounds = terrain.get("bounds") or []
            if len(bounds) == 4:
                min_x, min_y, max_x, max_y = (float(value) for value in bounds)
                landing = project.get("landing") or {}
                road_points = (project.get("road") or {}).get("points") or []
                margin = 60.0
                dem_min_x = min(
                    [
                        min_x,
                        *[float(point[0]) - margin for point in road_points],
                        float(landing.get("x", min_x)) - margin,
                    ]
                )
                dem_min_y = min(
                    [
                        min_y,
                        *[float(point[1]) - margin for point in road_points],
                        float(landing.get("y", min_y)) - margin,
                    ]
                )
                dem_max_x = max(
                    [
                        max_x,
                        *[float(point[0]) + margin for point in road_points],
                        float(landing.get("x", max_x)) + margin,
                    ]
                )
                dem_max_y = max(
                    [
                        max_y,
                        *[float(point[1]) + margin for point in road_points],
                        float(landing.get("y", max_y)) + margin,
                    ]
                )
                dem_res = 40
                cell_x = (dem_max_x - dem_min_x) / dem_res
                cell_y = (dem_max_y - dem_min_y) / dem_res
                array = np.empty((dem_res, dem_res), dtype="float32")
                for row in range(dem_res):
                    for col in range(dem_res):
                        x = dem_min_x + (col + 0.5) * cell_x
                        y = dem_min_y + (row + 0.5) * cell_y
                        array[row, col] = _terrain_elevation(project, base_elevation, x, y)
                array = np.flipud(array)
                dem_path = root / "terrain" / "studio_dem.tif"
                dem_path.parent.mkdir(parents=True, exist_ok=True)
                transform = from_origin(dem_min_x, dem_max_y, cell_x, cell_y)
                with rasterio.open(
                    dem_path,
                    "w",
                    driver="GTiff",
                    height=dem_res,
                    width=dem_res,
                    count=1,
                    dtype="float32",
                    crs="EPSG:3005",
                    transform=transform,
                ) as dataset:
                    dataset.write(array, 1)
                manifest["dem"] = str(dem_path.relative_to(root))
                manifest.setdefault("terrain", {})["dem"] = manifest["dem"]
                manifest["terrain"]["studio_base_m"] = base_elevation
        except Exception:
            # A visual terrain edit must not prevent a run if rasterio is unavailable.
            pass
    road = project.get("road") or {}
    road_points = road.get("points") or []
    if len(road_points) >= 2:
        road_path = root / "approaches" / "studio_road.geojson"
        road_path.parent.mkdir(parents=True, exist_ok=True)
        road_path.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"source": "studio"},
                            "geometry": {
                                "type": "LineString",
                                "coordinates": [[float(x), float(y)] for x, y in road_points],
                            },
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        manifest["road"] = str(road_path.relative_to(root))
    manifest["obstacles"] = [
        [
            round(tree.x_m, 3),
            round(tree.y_m, 3),
            round(max(2.0, (tree.crown_radius_m or 3.0) * 0.55), 3),
        ]
        for tree in residual_rows
    ]
    sync_system_args(project)
    manifest["system_args"] = project["system_args"]
    if isinstance(manifest.get("cable"), dict):
        manifest["cable"]["yarder"] = project.get("landing") or manifest["cable"].get("yarder")
    # Update lightweight stand totals for the derived view.
    model = ReferenceStemModel()
    volume = sum(model.evaluate(tree).merchantable_volume_m3 for tree in rows)
    manifest.setdefault("stand", {})["tree_count"] = len(rows)
    manifest["stand"]["merchantable_volume_m3"] = round(volume, 6)
    manifest["stand"]["area_ha"] = round(polygon_area_ha(polygon), 6)
    (root / "case.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return load_case(root)


def project_dataset(case: Case, project: dict[str, Any]) -> dict[str, Any]:
    """Build the editor dataset for a project against its immutable base case."""
    inventory = load_tree_inventory(case.path("inventory"), metadata_path=case.path("metadata"))
    polygon = project.get("block", {}).get("polygon") or []
    retained = set(project.get("retention", {}).get("tree_ids") or [])
    model = ReferenceStemModel()
    trees = []
    inside_count = 0
    retained_count = 0
    retained_ba = 0.0
    total_ba = 0.0
    for tree in inventory.rows:
        inside = _point_in_polygon(tree.x_m, tree.y_m, polygon)
        volume = model.evaluate(tree).merchantable_volume_m3
        ba = math.pi / 4.0 * (tree.dbh_cm / 100.0) ** 2
        total_ba += ba if inside else 0.0
        is_retained = tree.tree_id in retained
        if inside:
            inside_count += 1
        if is_retained:
            retained_count += 1
            retained_ba += ba
        trees.append(
            {
                "tree_id": tree.tree_id,
                "x": tree.x_m,
                "y": tree.y_m,
                "dbh_cm": tree.dbh_cm,
                "height_m": tree.height_m,
                "species_code": tree.species_code,
                "volume_m3": round(volume, 6),
                "inside": inside,
                "retained": is_retained,
            }
        )
    return {
        "project": project,
        "trees": trees,
        "stats": {
            "block_area_ha": round(polygon_area_ha(polygon), 6),
            "tree_count": len(trees),
            "inside_tree_count": inside_count,
            "retained_tree_count": retained_count,
            "retained_basal_area_fraction": round(retained_ba / total_ba, 6) if total_ba else 0.0,
            "total_basal_area_m2": round(total_ba, 4),
        },
        "policy_presets": POLICY_PRESETS,
    }
