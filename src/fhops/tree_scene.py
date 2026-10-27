"""Deterministic glTF/GLB export for tree-scale FHOPS scenes.

The exporter produces a portable scene artifact plus a camera path and a thin
viewer page. It is not a renderer: video production stays in external tools such
as Blender or a browser/Three.js pipeline.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fhops.spatial_machine import Obstacle
from fhops.stem import StemModelError, StemResult, build_stem_inventory
from fhops.tree_replay import TreeReplay, TreeReplayError, replay_tree_schedule

TREE_SCENE_SCHEMA = "fhops.tree.scene.v1"
DEFAULT_LOD_THRESHOLD = 5000
DEFAULT_MAX_LOG_NODES = 2000
_FLOAT = 5126
_UINT = 5125
_MODE_TRIANGLES = 4
_MODE_LINES = 1
_ARRAY_BUFFER = 34962
_ELEMENT_ARRAY_BUFFER = 34963
_SPECIES_COLORS: dict[str, tuple[float, float, float, float]] = {
    "Fd": (0.16, 0.42, 0.18, 1.0),
    "Cw": (0.12, 0.50, 0.32, 1.0),
    "Hw": (0.20, 0.58, 0.28, 1.0),
    "Ba": (0.22, 0.46, 0.20, 1.0),
    "Dr": (0.36, 0.45, 0.20, 1.0),
    "At": (0.40, 0.52, 0.24, 1.0),
}

__all__ = [
    "DEFAULT_LOD_THRESHOLD",
    "DEFAULT_MAX_LOG_NODES",
    "TreeSceneResult",
    "TreeSceneError",
    "write_tree_scene",
]


class TreeSceneError(RuntimeError):
    """Raised when a tree scene cannot be exported."""


@dataclass(frozen=True)
class TreeSceneResult:
    """Paths and summary for one exported tree scene.

    Attributes
    ----------
    scene_id : str
        Deterministic scene identifier.
    gltf_path : Path
        Embedded-buffer glTF file.
    glb_path : Path
        Binary glTF file.
    manifest_path : Path
        Scene manifest.
    camera_path : Path
        Camera keyframe JSON.
    viewer_path : Path
        Standalone HTML viewer.
    tree_count : int
        Exported tree count.
    processed_count : int
        Trees processed by the replay.
    log_count : int
        Exported log-node count.
    lod : str
        ``detailed`` or ``simple``.
    """

    scene_id: str
    gltf_path: Path
    glb_path: Path
    manifest_path: Path
    camera_path: Path
    viewer_path: Path
    tree_count: int
    processed_count: int
    log_count: int
    lod: str


def write_tree_scene(
    scenario_path: str | Path,
    assignments_path: str | Path,
    out_dir: Path,
    *,
    lod_threshold: int = DEFAULT_LOD_THRESHOLD,
    max_log_nodes: int = DEFAULT_MAX_LOG_NODES,
    obstacles: tuple[Obstacle, ...] = (),
    require_complete: bool = False,
    generated_utc: str | None = None,
) -> TreeSceneResult:
    """Export a deterministic glTF/GLB scene from a tree-scale schedule replay.

    Parameters
    ----------
    scenario_path : str | Path
        Scenario YAML with a tree-inventory pin.
    assignments_path : str | Path
        Assignments CSV used by the replay.
    out_dir : Path
        Output directory.
    lod_threshold : int, optional
        Use simple tree geometry above this tree count.
    max_log_nodes : int, optional
        Cap individual log nodes; above this, a log pile marker is used.
    obstacles : tuple[Obstacle, ...], optional
        Obstacles passed to the replay simulator.
    require_complete : bool, optional
        Refuse a replay with discrepancies.
    generated_utc : str | None, optional
        Generation timestamp.

    Returns
    -------
    TreeSceneResult
        Paths, counts, and LOD mode.

    Raises
    ------
    TreeSceneError
        If the replay or scene build fails.
    """
    if lod_threshold < 1:
        raise TreeSceneError("lod_threshold must be >= 1.")
    if max_log_nodes < 0:
        raise TreeSceneError("max_log_nodes must be >= 0.")
    scenario_file = Path(scenario_path).expanduser().resolve()
    try:
        stems = build_stem_inventory(scenario_file)
        replay = replay_tree_schedule(
            scenario_file,
            assignments_path,
            stem_inventory=stems,
            obstacles=obstacles,
            require_complete=require_complete,
        )
    except (StemModelError, TreeReplayError, ValueError, FileNotFoundError) as exc:
        raise TreeSceneError(str(exc)) from exc
    output = out_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    lod = "simple" if len(stems.trees) > lod_threshold else "detailed"
    builder = _GltfBuilder()
    tree_meshes = _build_tree_meshes(
        builder, sorted({tree.species_code for tree in stems.trees}), lod
    )
    processed_ids = {
        event.tree_id
        for assignment in replay.assignments
        for event in assignment.events
        if event.status == "processed"
    }
    tree_by_id = {tree.tree_id: tree for tree in stems.trees}
    min_z = min((tree.elevation_m or 0.0) for tree in stems.trees) if stems.trees else 0.0
    for tree in stems.trees:
        z = tree.elevation_m if tree.elevation_m is not None else min_z
        builder.add_node(
            f"tree:{tree.tree_id}",
            mesh=tree_meshes[tree.species_code],
            translation=(tree.x_m, z, tree.y_m),
            scale=(tree.dbh_cm / 40.0, tree.height_m / 25.0, tree.dbh_cm / 40.0),
            extras={
                "tree_id": tree.tree_id,
                "block_id": tree.block_id,
                "species_code": tree.species_code,
                "dbh_cm": tree.dbh_cm,
                "height_m": tree.height_m,
                "processed": tree.tree_id in processed_ids,
            },
        )
    xs = [tree.x_m for tree in stems.trees]
    ys = [tree.y_m for tree in stems.trees]
    if xs and ys:
        margin = max(10.0, max(max(xs) - min(xs), max(ys) - min(ys)) * 0.1)
        ground = _ground_mesh(
            builder, min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin
        )
        builder.add_node("ground", mesh=ground, translation=(0.0, min_z - 0.1, 0.0))
        path_points = _machine_path(replay, tree_by_id, min_z)
        if len(path_points) >= 2:
            path_mesh = _line_mesh(builder, path_points)
            builder.add_node("machine_path", mesh=path_mesh)
        log_count = _add_logs(builder, replay, tree_by_id, processed_ids, max_log_nodes, min_z)
        camera = _camera_path(xs, ys, min_z)
    else:
        path_points = []
        log_count = 0
        camera = {"frames": []}
    scene_doc = builder.build()
    gltf_path = output / "scene.gltf"
    gltf_path.write_text(
        json.dumps(_with_data_uri(scene_doc, builder.buffer), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    glb_path = output / "scene.glb"
    glb_path.write_bytes(_glb_bytes(scene_doc, builder.buffer))
    camera_path = output / "camera_path.json"
    camera_path.write_text(json.dumps(camera, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    viewer_path = output / "viewer.html"
    viewer_path.write_text(_viewer_html(), encoding="utf-8")
    bounds = {
        "x": [min(xs), max(xs)] if xs else [0.0, 0.0],
        "y": [min(ys), max(ys)] if ys else [0.0, 0.0],
        "z": [min_z, max((tree.elevation_m or min_z) for tree in stems.trees)]
        if stems.trees
        else [0.0, 0.0],
    }
    material = {
        "scenario": str(scenario_file),
        "schedule": replay.schedule_sha256,
        "replay_id": replay.replay_id,
        "trees": [tree.to_dict() for tree in stems.trees],
        "lod": lod,
    }
    scene_id = (
        "fhops-tree-scene-"
        + hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
    )
    manifest = {
        "schema_version": TREE_SCENE_SCHEMA,
        "scene_id": scene_id,
        "generated_utc": generated_utc or _utc_now(),
        "scenario_path": str(scenario_file),
        "assignments_path": str(Path(assignments_path).expanduser().resolve()),
        "schedule_sha256": replay.schedule_sha256,
        "replay_id": replay.replay_id,
        "stem_id": stems.stem_id,
        "tree_count": len(stems.trees),
        "processed_count": len(processed_ids),
        "log_count": log_count,
        "lod": lod,
        "lod_threshold": lod_threshold,
        "bounds": bounds,
        "machine_path_points": len(path_points),
        "files": {
            "gltf": "scene.gltf",
            "glb": "scene.glb",
            "camera_path": "camera_path.json",
            "viewer": "viewer.html",
        },
        "caveats": (
            "Procedural tree geometry only; not a surveyed tree map or machine CAD.",
            "Ground is a flat plane at the lowest tree elevation; it is not a terrain model.",
            "Rendering video is external to FHOPS.",
            *stems.caveats,
        ),
    }
    manifest_path = output / "scene_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return TreeSceneResult(
        scene_id=scene_id,
        gltf_path=gltf_path,
        glb_path=glb_path,
        manifest_path=manifest_path,
        camera_path=camera_path,
        viewer_path=viewer_path,
        tree_count=len(stems.trees),
        processed_count=len(processed_ids),
        log_count=log_count,
        lod=lod,
    )


class _GltfBuilder:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.buffer_views: list[dict[str, Any]] = []
        self.accessors: list[dict[str, Any]] = []
        self.meshes: list[dict[str, Any]] = []
        self.materials: list[dict[str, Any]] = []
        self.nodes: list[dict[str, Any]] = []

    def add_material(self, name: str, color: tuple[float, float, float, float]) -> int:
        self.materials.append(
            {
                "name": name,
                "pbrMetallicRoughness": {
                    "baseColorFactor": list(color),
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.9,
                },
            }
        )
        return len(self.materials) - 1

    def add_geometry(self, positions: list[float], indices: list[int]) -> tuple[int, int]:
        pos_accessor = self._accessor(positions, "VEC3", _ARRAY_BUFFER)
        idx_accessor = self._accessor(
            indices, "SCALAR", _ELEMENT_ARRAY_BUFFER, component_type=_UINT
        )
        return pos_accessor, idx_accessor

    def add_mesh(self, name: str, primitives: list[dict[str, Any]]) -> int:
        self.meshes.append({"name": name, "primitives": primitives})
        return len(self.meshes) - 1

    def add_node(
        self,
        name: str,
        *,
        mesh: int | None = None,
        translation: tuple[float, float, float] | None = None,
        scale: tuple[float, float, float] | None = None,
        extras: dict[str, object] | None = None,
    ) -> int:
        node: dict[str, Any] = {"name": name}
        if mesh is not None:
            node["mesh"] = mesh
        if translation is not None:
            node["translation"] = list(translation)
        if scale is not None:
            node["scale"] = list(scale)
        if extras:
            node["extras"] = extras
        self.nodes.append(node)
        return len(self.nodes) - 1

    def build(self) -> dict[str, Any]:
        return {
            "asset": {"version": "2.0", "generator": "FHOPS tree scene exporter"},
            "scene": 0,
            "scenes": [{"nodes": list(range(len(self.nodes)))}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "buffers": [{"byteLength": len(self.buffer)}],
            "bufferViews": self.buffer_views,
            "accessors": self.accessors,
        }

    def _accessor(
        self,
        values: list[float] | list[int],
        kind: str,
        target: int,
        *,
        component_type: int = _FLOAT,
    ) -> int:
        while len(self.buffer) % 4:
            self.buffer.append(0)
        fmt = "<" + ("f" if component_type == _FLOAT else "I") * len(values)
        data = struct.pack(fmt, *values)
        offset = len(self.buffer)
        self.buffer.extend(data)
        view_index = len(self.buffer_views)
        self.buffer_views.append(
            {"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target}
        )
        count = len(values) // 3 if kind == "VEC3" else len(values)
        accessor: dict[str, Any] = {
            "bufferView": view_index,
            "componentType": component_type,
            "count": count,
            "type": kind,
        }
        if kind == "VEC3":
            components = [float(value) for value in values]
            accessor["min"] = [min(components[index::3]) for index in range(3)]
            accessor["max"] = [max(components[index::3]) for index in range(3)]
        self.accessors.append(accessor)
        return len(self.accessors) - 1


def _build_tree_meshes(
    builder: _GltfBuilder,
    species: list[str],
    lod: str,
) -> dict[str, int]:
    trunk_pos, trunk_idx = _cylinder_geometry(0.12, 0.4, 8)
    trunk_accessors = builder.add_geometry(trunk_pos, trunk_idx)
    if lod == "simple":
        crown_pos, crown_idx = _cone_geometry(0.0, 0.55, 1.0, 0.8, 8)
    else:
        crown_pos, crown_idx = _cone_geometry(0.4, 0.5, 1.0, 0.8, 8)
    crown_accessors = builder.add_geometry(crown_pos, crown_idx)
    trunk_material = builder.add_material("trunk", (0.28, 0.16, 0.08, 1.0))
    meshes: dict[str, int] = {}
    for code in species:
        color = _color_for_species(code)
        crown_material = builder.add_material(f"crown:{code}", color)
        if lod == "simple":
            primitives = [
                {
                    "attributes": {"POSITION": crown_accessors[0]},
                    "indices": crown_accessors[1],
                    "material": crown_material,
                    "mode": _MODE_TRIANGLES,
                }
            ]
        else:
            primitives = [
                {
                    "attributes": {"POSITION": trunk_accessors[0]},
                    "indices": trunk_accessors[1],
                    "material": trunk_material,
                    "mode": _MODE_TRIANGLES,
                },
                {
                    "attributes": {"POSITION": crown_accessors[0]},
                    "indices": crown_accessors[1],
                    "material": crown_material,
                    "mode": _MODE_TRIANGLES,
                },
            ]
        meshes[code] = builder.add_mesh(f"tree:{code}", primitives)
    return meshes


def _ground_mesh(builder: _GltfBuilder, xmin: float, xmax: float, ymin: float, ymax: float) -> int:
    positions = [
        xmin,
        0.0,
        ymin,
        xmax,
        0.0,
        ymin,
        xmax,
        0.0,
        ymax,
        xmin,
        0.0,
        ymax,
    ]
    indices = [0, 1, 2, 0, 2, 3]
    pos_accessor, idx_accessor = builder.add_geometry(positions, indices)
    material = builder.add_material("ground", (0.42, 0.40, 0.32, 1.0))
    return builder.add_mesh(
        "ground",
        [
            {
                "attributes": {"POSITION": pos_accessor},
                "indices": idx_accessor,
                "material": material,
                "mode": _MODE_TRIANGLES,
            }
        ],
    )


def _line_mesh(builder: _GltfBuilder, points: list[tuple[float, float, float]]) -> int:
    positions = [value for point in points for value in point]
    indices = list(range(len(points)))
    pos_accessor, idx_accessor = builder.add_geometry(positions, indices)
    material = builder.add_material("machine_path", (0.95, 0.45, 0.05, 1.0))
    return builder.add_mesh(
        "machine_path",
        [
            {
                "attributes": {"POSITION": pos_accessor},
                "indices": idx_accessor,
                "material": material,
                "mode": _MODE_LINES,
            }
        ],
    )


def _add_logs(
    builder: _GltfBuilder,
    replay: TreeReplay,
    tree_by_id: dict[str, StemResult],
    processed_ids: set[str],
    max_log_nodes: int,
    min_z: float,
) -> int:
    logs = [
        log for tree in tree_by_id.values() if tree.tree_id in processed_ids for log in tree.logs
    ]
    if not logs:
        return 0
    if len(logs) > max_log_nodes:
        logs = logs[:max_log_nodes]
    positions, indices = _box_geometry()
    pos_accessor, idx_accessor = builder.add_geometry(positions, indices)
    material = builder.add_material("logs", (0.55, 0.30, 0.10, 1.0))
    mesh = builder.add_mesh(
        "logs",
        [
            {
                "attributes": {"POSITION": pos_accessor},
                "indices": idx_accessor,
                "material": material,
                "mode": _MODE_TRIANGLES,
            }
        ],
    )
    base = {}
    for assignment in replay.assignments:
        for event in assignment.events:
            if event.status != "processed":
                continue
            base[event.tree_id] = (event.x_m, event.y_m)
    for index, log in enumerate(logs):
        tree = tree_by_id.get(
            log["tree_id"] if isinstance(log, dict) else getattr(log, "tree_id", "")
        )
        if tree is None:
            continue
        x, y = base.get(tree.tree_id, (tree.x_m, tree.y_m))
        builder.add_node(
            f"log:{tree.tree_id}:{index}",
            mesh=mesh,
            translation=(x + 0.4, (tree.elevation_m or min_z) + 0.1, y + 0.4),
            scale=(0.2, 0.2, 1.0),
        )
    return min(len(logs), max_log_nodes)


def _machine_path(
    replay: TreeReplay,
    tree_by_id: dict[str, StemResult],
    min_z: float,
) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []
    for assignment in replay.assignments:
        for event in assignment.events:
            if event.status == "processed":
                tree = tree_by_id.get(event.tree_id)
                z = tree.elevation_m if tree is not None and tree.elevation_m is not None else min_z
                points.append((event.machine_x_m, z + 0.2, event.machine_y_m))
    return points


def _camera_path(xs: list[float], ys: list[float], z: float) -> dict[str, object]:
    if not xs or not ys:
        return {"frames": []}
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    extent = max(max(xs) - min(xs), max(ys) - min(ys), 20.0)
    radius = extent * 0.9
    height = z + extent * 0.7
    frames = []
    for index, angle in enumerate((0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0)):
        frames.append(
            {
                "frame": index,
                "position": [cx + radius * math.cos(angle), height, cy + radius * math.sin(angle)],
                "target": [cx, z, cy],
            }
        )
    return {"frames": frames, "target": [cx, z, cy], "radius_m": radius}


def _color_for_species(code: str) -> tuple[float, float, float, float]:
    if code in _SPECIES_COLORS:
        return _SPECIES_COLORS[code]
    digest = hashlib.sha256(code.encode("utf-8")).digest()
    return (0.25 + digest[0] / 512.0, 0.35 + digest[1] / 512.0, 0.20 + digest[2] / 512.0, 1.0)


def _cylinder_geometry(
    radius: float, height: float, segments: int
) -> tuple[list[float], list[int]]:
    positions: list[float] = []
    indices: list[int] = []
    for index in range(segments + 1):
        angle = 2.0 * math.pi * index / segments
        x = radius * math.cos(angle)
        z = radius * math.sin(angle)
        positions.extend([x, 0.0, z, x, height, z])
    for index in range(segments):
        a = index * 2
        b = a + 1
        c = a + 2
        d = a + 3
        indices.extend([a, c, b, b, c, d])
    return positions, indices


def _cone_geometry(
    base_y: float, radius: float, height: float, apex_height: float, segments: int
) -> tuple[list[float], list[int]]:
    positions: list[float] = []
    indices: list[int] = []
    for index in range(segments + 1):
        angle = 2.0 * math.pi * index / segments
        positions.extend([radius * math.cos(angle), base_y, radius * math.sin(angle)])
    apex = len(positions) // 3
    positions.extend([0.0, base_y + apex_height, 0.0])
    for index in range(segments):
        indices.extend([index, index + 1, apex])
    return positions, indices


def _box_geometry() -> tuple[list[float], list[int]]:
    positions = [
        -0.5,
        0.0,
        -0.5,
        0.5,
        0.0,
        -0.5,
        0.5,
        0.0,
        0.5,
        -0.5,
        0.0,
        0.5,
        -0.5,
        1.0,
        -0.5,
        0.5,
        1.0,
        -0.5,
        0.5,
        1.0,
        0.5,
        -0.5,
        1.0,
        0.5,
    ]
    indices = [
        0,
        1,
        2,
        0,
        2,
        3,
        4,
        6,
        5,
        4,
        7,
        6,
        0,
        4,
        5,
        0,
        5,
        1,
        1,
        5,
        6,
        1,
        6,
        2,
        2,
        6,
        7,
        2,
        7,
        3,
        3,
        7,
        4,
        3,
        4,
        0,
    ]
    return positions, indices


def _with_data_uri(doc: dict[str, Any], buffer: bytearray) -> dict[str, Any]:
    result = json.loads(json.dumps(doc))
    result["buffers"][0]["uri"] = "data:application/octet-stream;base64," + base64.b64encode(
        buffer
    ).decode("ascii")
    return result


def _glb_bytes(doc: dict[str, Any], buffer: bytearray) -> bytes:
    doc = json.loads(json.dumps(doc))
    doc["buffers"][0]["byteLength"] = len(buffer)
    json_bytes = json.dumps(doc, separators=(",", ":"), sort_keys=True).encode("utf-8")
    json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
    bin_bytes = bytes(buffer)
    bin_bytes += b"\x00" * ((4 - len(bin_bytes) % 4) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    return (
        struct.pack("<III", 0x46546C67, 2, total)
        + struct.pack("<II", len(json_bytes), 0x4E4F534A)
        + json_bytes
        + struct.pack("<II", len(bin_bytes), 0x004E4942)
        + bin_bytes
    )


def _viewer_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FHOPS tree scene</title>
  <style>
    html, body { margin: 0; height: 100%; overflow: hidden; background: #101416; }
    canvas { display: block; }
    #note { position: fixed; left: 12px; bottom: 12px; color: #d8e0e6;
            font: 12px/1.4 system-ui, sans-serif; background: #101416cc; padding: 8px 10px; }
  </style>
</head>
<body>
  <div id="note">FHOPS tree scene · drag to orbit · wheel to zoom</div>
  <script type="importmap">
    {"imports": {
      "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
      "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/"
    }}
  </script>
  <script type="module">
    import * as THREE from 'three';
    import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
    import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
    const renderer = new THREE.WebGLRenderer({antialias: true});
    renderer.setSize(innerWidth, innerHeight);
    renderer.setPixelRatio(devicePixelRatio);
    document.body.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x101416);
    const camera = new THREE.PerspectiveCamera(55, innerWidth / innerHeight, 0.1, 5000);
    camera.position.set(0, 40, 80);
    const controls = new OrbitControls(camera, renderer.domElement);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x25302d, 1.1));
    const sun = new THREE.DirectionalLight(0xfff2d8, 2.0);
    sun.position.set(50, 100, 40);
    scene.add(sun);
    new GLTFLoader().load('scene.gltf', (gltf) => {
      scene.add(gltf.scene);
      const box = new THREE.Box3().setFromObject(gltf.scene);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3()).length() || 50;
      controls.target.copy(center);
      camera.position.copy(center).add(new THREE.Vector3(size * 0.7, size * 0.45, size * 0.7));
      controls.update();
    });
    addEventListener('resize', () => {
      camera.aspect = innerWidth / innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(innerWidth, innerHeight);
    });
    (function animate() { requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); })();
  </script>
</body>
</html>
"""


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
