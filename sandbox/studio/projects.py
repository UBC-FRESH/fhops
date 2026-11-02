"""Project storage and derived editor data for FHOPS Scenario Studio.

The Studio is an authoring layer over immutable Tree Lab cases.  A project
stores only edits and references its base case; source fixtures under
``sandbox/cases`` are never modified by this module.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import secrets
import shutil
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fhops.stem import ReferenceStemModel
from fhops.tree_inventory import TreeInventory, load_tree_inventory
from sandbox.tree_lab.cases import Case, load_case, sha256_file
from sandbox.tree_lab.harvest import INVENTORY_FIELDS

PROJECT_SCHEMA = "fhops.studio.project.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
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


_EDIT_SIGNATURE_FIELDS = (
    "base_case_id",
    "block_id",
    "block",
    "landing",
    "landings",
    "landing_trucks",
    "road",
    "retention",
    "machines",
    "operator_policies",
    "terrain",
)


def _stable_signature(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def project_edit_signature(project: dict[str, Any]) -> str:
    """Return a stable hash of the edits that affect derived runs.

    Parameters
    ----------
    project : dict[str, Any]
        Studio project payload. Missing fields are hashed as ``None`` so
        incomplete older projects remain comparable.

    Returns
    -------
    str
        Lower-case SHA-256 digest. Project metadata such as ``label``,
        ``notes``, timestamps, and the monotonically increasing revision are
        intentionally excluded; the digest changes only when run-affecting
        project content changes.

    Notes
    -----
    The signature covers boundary, landing, road, retention, machines,
    operator policies, terrain, and per-landing truck counts. Derived system
    arguments are excluded because they are regenerated from those inputs.
    Projects without ``landings`` or ``landing_trucks`` keep the older signature
    shape for backward freshness compatibility. The digest is stored on derived cases and copied
    into run records so the Studio can flag stale runs.
    """
    payload = {field: project.get(field) for field in _EDIT_SIGNATURE_FIELDS}
    if not project.get("landings"):
        # Preserve freshness for pre-multi-landing runs, whose signatures had
        # no landings field at all.
        payload.pop("landings", None)
    if not project.get("landing_trucks"):
        # Preserve freshness for runs created before per-landing truck counts.
        payload.pop("landing_trucks", None)
    return _stable_signature(payload)


def terrain_signature(project: dict[str, Any]) -> str:
    """Return a stable hash of the project terrain heightfield.

    Parameters
    ----------
    project : dict[str, Any]
        Studio project payload.

    Returns
    -------
    str
        SHA-256 digest of the terrain mapping, including bounds, resolution,
        heights, and base elevation. A project without terrain still receives a
        stable digest.
    """
    return _stable_signature({"terrain": project.get("terrain")})


def run_freshness(project: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Compare a persisted run record with the current project edits.

    Parameters
    ----------
    project : dict[str, Any]
        Current Studio project.
    record : dict[str, Any]
        Persisted ``run.json`` payload. Phase 22 and earlier records may not
        contain the ``studio`` signature block.

    Returns
    -------
    dict[str, Any]
        Mapping with ``stale`` (bool), ``reasons`` (list of human-readable
        strings), ``run_revision`` (int or ``None``), and
        ``current_revision`` (int or ``None``). Missing signature metadata is
        treated as stale because freshness cannot be established.
    """
    studio = record.get("studio") if isinstance(record.get("studio"), dict) else {}
    run_revision = studio.get("project_revision") if studio else None
    current_revision = project.get("revision")
    current_edit = project_edit_signature(project)
    current_terrain = terrain_signature(project)
    run_edit = studio.get("edit_signature") if studio else None
    run_terrain = studio.get("terrain_signature") if studio else None
    if not run_edit or not run_terrain:
        return {
            "stale": True,
            "reasons": ["Legacy run has no project signature; rerun to refresh."],
            "run_revision": run_revision,
            "current_revision": current_revision,
        }
    reasons: list[str] = []
    if run_terrain != current_terrain:
        reasons.append("Terrain edits changed after this run.")
    if run_edit != current_edit and run_terrain == current_terrain:
        reasons.append("Project edits changed after this run.")
    return {
        "stale": bool(reasons),
        "reasons": reasons,
        "run_revision": run_revision,
        "current_revision": current_revision,
    }


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
                "landing_id": "landing-main"
                if role in {"loader", "roadside_processor", "processor"}
                else None,
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
    points = [[min(xs) - 60.0, road_y], [max(xs) + 60.0, road_y]]
    return {
        "points": points,
        "segments": [{"id": "road-main", "label": "Main road", "points": points}],
        "width_m": 10.0,
    }


def project_landings(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized landing choices for a project.

    Parameters
    ----------
    project : dict[str, Any]
        Studio project payload. ``landings`` is the multi-landing model;
        legacy projects have only the primary ``landing`` mapping.

    Returns
    -------
    list[dict[str, Any]]
        Landing mappings with ``id``, ``label``, ``x``, and ``y``. The first
        entry is the primary landing. Finite coordinates are required.
    """
    items: list[dict[str, Any]] = []
    for index, landing in enumerate(project.get("landings") or []):
        if not isinstance(landing, dict):
            continue
        try:
            x, y = float(landing["x"]), float(landing["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (math.isfinite(x) and math.isfinite(y)):
            continue
        items.append(
            {
                "id": str(landing.get("id") or f"landing-{index + 1}"),
                "label": str(landing.get("label") or f"Landing {index + 1}"),
                "x": x,
                "y": y,
            }
        )
    if not items:
        primary = project.get("landing") if isinstance(project.get("landing"), dict) else {}
        try:
            x, y = float(primary["x"]), float(primary["y"])
        except (KeyError, TypeError, ValueError):
            x = y = 0.0
        items.append({"id": "landing-main", "label": "Landing", "x": x, "y": y})
    return items


def road_segments(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the project's road segments, including legacy single roads.

    Parameters
    ----------
    project : dict[str, Any]
        Studio project payload. ``road.segments`` is the current representation;
        older projects stored only ``road.points``.

    Returns
    -------
    list[dict[str, Any]]
        Segments with ``id``, ``label``, and a ``points`` list of
        ``[x_m, y_m]`` vertices. Segments with fewer than two points are
        omitted. Legacy ``road.points`` become one segment with id
        ``road-main`` when no valid segments exist.
    """
    road = project.get("road") if isinstance(project.get("road"), dict) else {}
    segments: list[dict[str, Any]] = []
    for index, segment in enumerate(road.get("segments") or []):
        if not isinstance(segment, dict):
            continue
        points = segment.get("points")
        if not isinstance(points, list) or len(points) < 2:
            continue
        segments.append(
            {
                "id": str(segment.get("id") or f"road-{index + 1}"),
                "label": str(segment.get("label") or f"Road {index + 1}"),
                "points": [[float(point[0]), float(point[1])] for point in points],
            }
        )
    if not segments:
        points = road.get("points")
        if isinstance(points, list) and len(points) >= 2:
            segments.append(
                {
                    "id": "road-main",
                    "label": str(road.get("label") or "Main road"),
                    "points": [[float(point[0]), float(point[1])] for point in points],
                }
            )
    return segments


def _system_args(case: Case) -> dict[str, Any]:
    return json.loads(json.dumps(case.manifest.get("system_args") or {}))


def create_project(case: Case) -> dict[str, Any]:
    """Create a new project from an existing Tree Lab case."""
    inventory = load_tree_inventory(case.path("inventory"), metadata_path=case.path("metadata"))
    polygon = _block_polygon(case, inventory)
    catalog = _machine_catalog(case)
    for source in list(catalog):
        if source["role"] in {"loader", "roadside_processor", "processor"}:
            catalog.append({"id": f"{source['id']}-B", "role": source["role"]})
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
        "landings": [{"id": "landing-main", "label": "Landing", **landing}],
        "road": road,
        "retention": {"tree_ids": [], "clumps": [], "target_fraction_basal_area": 0.0},
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
    clumps = project.get("retention", {}).get("clumps", [])
    if not isinstance(clumps, list):
        raise StudioError("Retention clumps must be a list.")
    for clump in clumps:
        polygon_clump = clump.get("polygon") if isinstance(clump, dict) else None
        if not isinstance(polygon_clump, list) or len(polygon_clump) < 3:
            raise StudioError("Each retention clump needs at least three points.")
    landings = project_landings(project)
    project["landings"] = landings
    project["landing"] = {"x": landings[0]["x"], "y": landings[0]["y"]}
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


def duplicate_project(root: Path, project: dict[str, Any]) -> dict[str, Any]:
    """Copy one project under a new stable project id."""
    copied = json.loads(json.dumps(project))
    copied["project_id"] = _project_id(str(project.get("base_case_id", "studio")))
    copied["label"] = f"{project.get('label', 'Studio project')} — copy"
    copied["revision"] = 0
    copied["created_utc"] = _now()
    copied["updated_utc"] = _now()
    return save_project(root, copied)


def import_project(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Import a project JSON as a new project id."""
    if not isinstance(payload, dict) or payload.get("schema_version") != PROJECT_SCHEMA:
        raise StudioError("Unsupported Studio project payload.")
    copied = json.loads(json.dumps(payload))
    copied["project_id"] = _project_id(str(copied.get("base_case_id", "studio")))
    copied["label"] = f"{copied.get('label', 'Studio project')} — imported"
    copied["revision"] = 0
    copied["created_utc"] = _now()
    copied["updated_utc"] = _now()
    return save_project(root, copied)


def promote_run(root: Path, project: dict[str, Any], run_id: str) -> dict[str, str]:
    """Copy a Studio run into the Tree Lab case run directory."""
    if not run_id or "/" in run_id or ".." in run_id:
        raise StudioError("Invalid run id.")
    base_case_id = str(project.get("base_case_id", ""))
    if not base_case_id:
        raise StudioError("Project has no base case.")
    project_id = str(project.get("project_id", ""))
    source = project_path(root, project_id) / "runs" / run_id
    if not source.is_dir():
        raise StudioError(f"Unknown run {run_id!r}.")
    target = REPO_ROOT / "sandbox" / "runs" / base_case_id / run_id
    if target.exists():
        raise StudioError(f"Tree Lab run {run_id!r} already exists.")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    return {"run_id": run_id, "base_case_id": base_case_id, "path": str(target)}


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


def _retention_clumps(project: dict[str, Any]) -> list[dict[str, Any]]:
    retention = project.get("retention") or {}
    clumps = retention.get("clumps") or []
    return [
        clump
        for clump in clumps
        if isinstance(clump, dict) and isinstance(clump.get("polygon"), list)
    ]


def _in_any_clump(x: float, y: float, clumps: list[dict[str, Any]]) -> bool:
    return any(_point_in_polygon(x, y, clump.get("polygon") or []) for clump in clumps)


def _clump_area_ha(clumps: list[dict[str, Any]]) -> float:
    return sum(polygon_area_ha(clump.get("polygon") or []) for clump in clumps)


def polygon_area_ha(polygon: list[list[float]]) -> float:
    """Return polygon area in hectares using the shoelace formula."""
    if len(polygon) < 3:
        return 0.0
    area = 0.0
    for index, point in enumerate(polygon):
        nxt = polygon[(index + 1) % len(polygon)]
        area += float(point[0]) * float(nxt[1]) - float(nxt[0]) * float(point[1])
    return abs(area) / 2.0 / 10000.0


def stream_buffer_polygon(points: Sequence[Sequence[float]], width_m: float) -> list[list[float]]:
    """Buffer a stream centreline into a closed riparian-retention polygon.

    The Studio uses this helper when an operator draws a stream. The returned
    polygon is stored as a ``riparian`` retention clump, so the existing tree
    filtering, felling exclusion, and machine-routing obstacle rules apply
    without a separate simulation path.

    Parameters
    ----------
    points : Sequence[Sequence[float]]
        Centreline vertices as ``[x_m, y_m]`` in the project CRS. At least two
        distinct vertices are required. Consecutive duplicate points are
        discarded.
    width_m : float
        Full buffer width in metres. Must be positive and finite. The centreline
        is offset by ``width_m / 2`` on each side.

    Returns
    -------
    list[list[float]]
        Closed polygon vertices in ``[x_m, y_m]`` order. The first and last
        vertices are not repeated; callers should treat the ring as closed.

    Raises
    ------
    StudioError
        If the centreline has fewer than two distinct points or the width is
        not positive and finite.

    Notes
    -----
    This is a planar, single-ring offset suitable for authoring. Sharp turns
    can create small self-intersections; the point-in-polygon retention test is
    still conservative because the full offset band remains inside the ring's
    outer boundary. It is not a hydraulic or survey-grade stream buffer.
    """
    if not math.isfinite(width_m) or width_m <= 0:
        raise StudioError("Stream buffer width must be positive and finite.")
    clean: list[tuple[float, float]] = []
    for point in points:
        if len(point) != 2:
            raise StudioError("Stream points must contain exactly two coordinates.")
        x, y = float(point[0]), float(point[1])
        if not math.isfinite(x) or not math.isfinite(y):
            raise StudioError("Stream coordinates must be finite.")
        if not clean or math.hypot(x - clean[-1][0], y - clean[-1][1]) > 1e-6:
            clean.append((x, y))
    if len(clean) < 2:
        raise StudioError("A stream buffer needs at least two distinct points.")
    half = width_m / 2.0
    left: list[list[float]] = []
    right: list[list[float]] = []
    previous_tangent = (1.0, 0.0)
    for index, (x, y) in enumerate(clean):
        if index == 0:
            tx, ty = clean[1][0] - x, clean[1][1] - y
        elif index == len(clean) - 1:
            tx, ty = x - clean[index - 1][0], y - clean[index - 1][1]
        else:
            before = math.hypot(x - clean[index - 1][0], y - clean[index - 1][1])
            after = math.hypot(clean[index + 1][0] - x, clean[index + 1][1] - y)
            tx = (x - clean[index - 1][0]) / before + (clean[index + 1][0] - x) / after
            ty = (y - clean[index - 1][1]) / before + (clean[index + 1][1] - y) / after
        length = math.hypot(tx, ty)
        if length <= 1e-9:
            tx, ty = previous_tangent
            length = math.hypot(tx, ty)
        tx, ty = tx / length, ty / length
        previous_tangent = (tx, ty)
        nx, ny = -ty, tx
        left.append([round(x + nx * half, 3), round(y + ny * half, 3)])
        right.append([round(x - nx * half, 3), round(y - ny * half, 3)])
    return left + list(reversed(right))


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
    landing_ids = [landing["id"] for landing in project_landings(project)]
    default_landing = landing_ids[0] if landing_ids else "landing-main"
    fleets: dict[str, dict[str, Any]] = {}
    for machine in machines:
        role = str(machine.get("role", ""))
        if role not in {"loader", "roadside_processor", "processor"}:
            continue
        landing_id = str(machine.get("landing_id") or default_landing)
        if landing_id not in landing_ids:
            raise StudioError(f"Machine {machine.get('id')!r} references unknown landing.")
        fleet = fleets.setdefault(landing_id, {"loader": None, "processors": []})
        if role == "loader":
            if fleet["loader"] is not None:
                raise StudioError(f"Landing {landing_id!r} has more than one loader.")
            fleet["loader"] = str(machine.get("id"))
        else:
            fleet["processors"].append(str(machine.get("id")))
    primary_fleet = fleets.get(default_landing)
    if not primary_fleet or not primary_fleet.get("loader"):
        raise StudioError("The primary landing needs one loader.")
    args["loader"] = primary_fleet["loader"]
    args["processors"] = primary_fleet["processors"]
    args["landing_fleets"] = fleets
    truck_counts = project.get("landing_trucks")
    if isinstance(truck_counts, dict) and truck_counts:
        args["landing_truck_counts"] = {
            landing_id: max(0, int(truck_counts.get(landing_id, 0))) for landing_id in landing_ids
        }
    else:
        args.pop("landing_truck_counts", None)
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
                    "elevation_m": (
                        elevation_fn(tree.x_m, tree.y_m)
                        if elevation_fn is not None
                        else tree.elevation_m
                    ),
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


def apply_operator_policies(project: dict[str, Any]) -> dict[str, Any]:
    """Translate machine policy presets into system arguments the CLI can run."""
    args = sync_system_args(project)
    machines = project.get("machines") or []
    policies = project.get("operator_policies") or {}
    by_role: dict[str, list[str]] = {}
    for machine in machines:
        by_role.setdefault(str(machine.get("role", "")), []).append(str(machine.get("id")))

    def preset_for(machine_id: str) -> dict[str, Any]:
        return POLICY_PRESETS.get(str(policies.get(machine_id, "steady")), POLICY_PRESETS["steady"])

    skidder_ids = [
        machine_id
        for role in ("grapple_skidder", "skidder", "forwarder", "cable_yarder", "skyline_yarder")
        for machine_id in by_role.get(role, [])
    ]
    loader_ids = by_role.get("loader", [])
    if skidder_ids:
        presets = [preset_for(machine_id) for machine_id in skidder_ids]
        cycle = sum(float(preset["cycle_multiplier"]) for preset in presets) / len(presets)
        setup = sum(float(preset["setup_delay_s"]) for preset in presets) / len(presets)
        args["skidder_empty_speed"] = round(1.4 / max(0.5, cycle), 4)
        args["skidder_loaded_speed"] = round(1.1 / max(0.5, cycle), 4)
        args["skidder_load_fixed"] = round(max(0.0, 45.0 * cycle + setup * 0.5), 3)
        args["skidder_unload_fixed"] = round(max(0.0, 45.0 * cycle + setup * 0.5), 3)
        args["skidder_load_per_log"] = round(5.0 * cycle, 3)
        args["skidder_unload_per_log"] = round(3.0 * cycle, 3)
        if any(float(preset["cycle_multiplier"]) > 1.05 for preset in presets):
            args["max_skidder_grade"] = min(float(args.get("max_skidder_grade", 35.0)), 30.0)
    if loader_ids:
        preset = preset_for(loader_ids[0])
        cycle = float(preset["cycle_multiplier"])
        args["loader_process_fixed"] = round(
            max(0.0, 45.0 * cycle + float(preset["setup_delay_s"]) * 0.5), 3
        )
        args["loader_process_per_log"] = round(4.0 * cycle, 3)
    processor_ids = [
        machine_id
        for role in ("roadside_processor", "processor")
        for machine_id in by_role.get(role, [])
    ]
    if processor_ids:
        presets = [preset_for(machine_id) for machine_id in processor_ids]
        cycle = sum(float(preset["cycle_multiplier"]) for preset in presets) / len(presets)
        args["processor_productivity_multiplier"] = round(1.0 / max(0.5, cycle), 4)
    return args


def _ensure_derived_machines(root: Path, project: dict[str, Any]) -> None:
    """Append Studio fleet-clone machines to a derived scenario dataset."""
    machine_path = root / "scenario" / "data" / "machines.csv"
    calendar_path = root / "scenario" / "data" / "calendar.csv"
    if not machine_path.is_file():
        return
    with machine_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    existing = {row.get("id") for row in rows}
    added: list[str] = []
    for machine in project.get("machines") or []:
        machine_id = str(machine.get("id") or "")
        role = str(machine.get("role") or "")
        if (
            not machine_id
            or machine_id in existing
            or role not in {"loader", "roadside_processor", "processor"}
        ):
            continue
        row = {name: "" for name in fieldnames}
        row.update(
            {
                "id": machine_id,
                "crew": machine_id,
                "daily_hours": "24.0",
                "operating_cost": "950.0",
                "role": role,
            }
        )
        rows.append(row)
        existing.add(machine_id)
        added.append(machine_id)
    if not added:
        return
    with machine_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    if not calendar_path.is_file():
        return
    with calendar_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        calendar_fields = reader.fieldnames or []
        calendar_rows = list(reader)
    days = [int(row["day"]) for row in calendar_rows if str(row.get("day", "")).isdigit()]
    last_day = max(days, default=1)
    for machine_id in added:
        for day in range(1, last_day + 1):
            calendar_rows.append({"machine_id": machine_id, "day": str(day), "available": "1"})
    with calendar_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=calendar_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(calendar_rows)


def materialize_case(project_root: Path, project: dict[str, Any], base_case: Case) -> Case:
    """Create a disposable case directory for running an edited project."""
    project_id = str(project["project_id"])
    root = project_path(project_root, project_id) / "derived_cases" / str(base_case.case_id)
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(base_case.root, root)
    _ensure_derived_machines(root, project)
    inventory = load_tree_inventory(
        base_case.path("inventory"), metadata_path=base_case.path("metadata")
    )
    polygon = project.get("block", {}).get("polygon") or []
    retained = set(project.get("retention", {}).get("tree_ids") or [])
    clumps = _retention_clumps(project)
    rows = [
        tree
        for tree in inventory.rows
        if tree.tree_id not in retained
        and not _in_any_clump(tree.x_m, tree.y_m, clumps)
        and _point_in_polygon(tree.x_m, tree.y_m, polygon)
    ]
    residual_rows = [
        tree
        for tree in inventory.rows
        if (tree.tree_id in retained or _in_any_clump(tree.x_m, tree.y_m, clumps))
        and _point_in_polygon(tree.x_m, tree.y_m, polygon)
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
    landings = project_landings(project)
    manifest["landing"] = {"x": landings[0]["x"], "y": landings[0]["y"]}
    manifest["landings"] = landings
    manifest["studio_project_id"] = project_id
    manifest["studio_project_revision"] = int(project.get("revision") or 1)
    manifest["studio_project_updated_utc"] = project.get("updated_utc")
    if heights:
        try:
            import numpy as np
            import rasterio
            from rasterio.transform import from_origin

            bounds = terrain.get("bounds") or []
            if len(bounds) == 4:
                min_x, min_y, max_x, max_y = (float(value) for value in bounds)
                landing_points = [[item["x"], item["y"]] for item in landings]
                road_points = [
                    point
                    for segment in road_segments(project)
                    for point in segment.get("points") or []
                ]
                margin = 60.0
                dem_min_x = min(
                    [
                        min_x,
                        *[float(point[0]) - margin for point in road_points],
                        *[float(point[0]) - margin for point in landing_points],
                    ]
                )
                dem_min_y = min(
                    [
                        min_y,
                        *[float(point[1]) - margin for point in road_points],
                        *[float(point[1]) - margin for point in landing_points],
                    ]
                )
                dem_max_x = max(
                    [
                        max_x,
                        *[float(point[0]) + margin for point in road_points],
                        *[float(point[0]) + margin for point in landing_points],
                    ]
                )
                dem_max_y = max(
                    [
                        max_y,
                        *[float(point[1]) + margin for point in road_points],
                        *[float(point[1]) + margin for point in landing_points],
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
    segments = road_segments(project)
    if segments:
        road_path = root / "approaches" / "studio_road.geojson"
        road_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            [[float(point[0]), float(point[1])] for point in segment["points"]]
            for segment in segments
        ]
        geometry = (
            {"type": "LineString", "coordinates": lines[0]}
            if len(lines) == 1
            else {"type": "MultiLineString", "coordinates": lines}
        )
        road_path.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "source": "studio",
                                "segments": [
                                    {"id": segment["id"], "label": segment["label"]}
                                    for segment in segments
                                ],
                            },
                            "geometry": geometry,
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        manifest["road"] = str(road_path.relative_to(root))
        manifest["road_segments"] = segments
    manifest["retention_clumps"] = clumps
    manifest["obstacles"] = [
        [
            round(tree.x_m, 3),
            round(tree.y_m, 3),
            round(max(2.0, (tree.crown_radius_m or 3.0) * 0.55), 3),
        ]
        for tree in residual_rows
    ]
    apply_operator_policies(project)
    manifest["system_args"] = project["system_args"]
    manifest["landing_fleets"] = project["system_args"].get("landing_fleets") or {}
    manifest["landing_truck_counts"] = project["system_args"].get("landing_truck_counts") or {}
    manifest["operator_policies"] = project.get("operator_policies", {})
    manifest["studio_edit_signature"] = project_edit_signature(project)
    manifest["studio_terrain_signature"] = terrain_signature(project)
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
    catalog = project.setdefault("catalog", [])
    existing = {str(item.get("id")) for item in catalog if isinstance(item, dict)}
    for source in list(catalog):
        if not isinstance(source, dict):
            continue
        if source.get("role") not in {"loader", "roadside_processor", "processor"}:
            continue
        if str(source.get("id") or "").endswith("-B"):
            continue
        clone_id = f"{source.get('id')}-B"
        if clone_id not in existing:
            catalog.append({"id": clone_id, "role": source["role"]})
            existing.add(clone_id)
    inventory = load_tree_inventory(case.path("inventory"), metadata_path=case.path("metadata"))
    polygon = project.get("block", {}).get("polygon") or []
    retained = set(project.get("retention", {}).get("tree_ids") or [])
    clumps = _retention_clumps(project)
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
        is_retained = tree.tree_id in retained or _in_any_clump(tree.x_m, tree.y_m, clumps)
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
            "clump_count": len(clumps),
            "clump_area_ha": round(_clump_area_ha(clumps), 6),
        },
        "policy_presets": POLICY_PRESETS,
    }
