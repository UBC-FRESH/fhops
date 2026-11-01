import * as THREE from "three";
import { OrbitControls } from "../lab/vendor/three/OrbitControls.js";

const API = new URL("api/", document.baseURI).pathname;
const $ = (selector) => document.querySelector(selector);
const params = new URLSearchParams(location.search);
const projectId = params.get("project") || "";
let project = null;
let dataset = null;
let terrainMesh = null;
let treeGroup = null;
let treeMeshes = [];
let treeById = new Map();
let boundaryGroup = null;
let roadLine = null;
let landingGroup = null;
let handleMeshes = [];
let selectedHandle = null;
let tool = "orbit";
let brush = 25;
let dragging = null;
let dirty = false;
let accessMode = false;
let clumpDraft = [];
let streamDraft = [];
let history = [];
let future = [];

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0e1214);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
renderer.setSize($("#scene").clientWidth, $("#scene").clientHeight);
$("#scene").appendChild(renderer.domElement);
const camera = new THREE.PerspectiveCamera(48, 1, 0.5, 100000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
scene.add(new THREE.HemisphereLight(0xffffff, 0x24302d, 1.4));
const sun = new THREE.DirectionalLight(0xfff2d8, 2.0);
sun.position.set(100, 300, 120);
scene.add(sun);
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();

function pushHistory() {
  if (!project) return;
  history.push(JSON.stringify(project));
  if (history.length > 50) history.shift();
  future = [];
}

function restoreProject(json) {
  project = JSON.parse(json);
  dirty = true;
  rebuildAll();
  updateStats();
  setStatus("Undo applied");
}

function undo() {
  if (!history.length) return;
  future.push(JSON.stringify(project));
  restoreProject(history.pop());
}

function redo() {
  if (!future.length) return;
  history.push(JSON.stringify(project));
  restoreProject(future.pop());
}

function setStatus(text, error = false) {
  $("#status").textContent = text;
  $("#status").style.color = error ? "#ff8b80" : "";
}
function markDirty() { dirty = true; setStatus("Unsaved 3D edits"); }

function getBounds() {
  const polygon = project?.block?.polygon || [];
  const xs = polygon.map((point) => Number(point[0]));
  const ys = polygon.map((point) => Number(point[1]));
  if (!xs.length) return [0, 0, 1, 1];
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

function terrainInfo() {
  const [minX, minY, maxX, maxY] = getBounds();
  const terrain = project.terrain || {};
  const res = Math.max(2, Number(terrain.resolution) || 24);
  const heights = Array.isArray(terrain.heights) && terrain.heights.length
    ? terrain.heights
    : Array(res * res).fill(0);
  return { minX, minY, maxX, maxY, res, heights };
}

function pointInPolygon(x, z, polygon) {
  let inside = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index++) {
    const xi = Number(polygon[index][0]), zi = Number(polygon[index][1]);
    const xj = Number(polygon[previous][0]), zj = Number(polygon[previous][1]);
    if ((zi > z) !== (zj > z) && x < ((xj - xi) * (z - zi)) / (zj - zi) + xi) inside = !inside;
  }
  return inside;
}

function terrainHeight(x, z) {
  const { minX, minY, maxX, maxY, res, heights } = terrainInfo();
  const fx = Math.max(0, Math.min(res - 1, (x - minX) / Math.max(1e-9, maxX - minX) * (res - 1)));
  const fz = Math.max(0, Math.min(res - 1, (z - minY) / Math.max(1e-9, maxY - minY) * (res - 1)));
  const x0 = Math.floor(fx), z0 = Math.floor(fz);
  const x1 = Math.min(res - 1, x0 + 1), z1 = Math.min(res - 1, z0 + 1);
  const dx = fx - x0, dz = fz - z0;
  const h00 = Number(heights[z0 * res + x0]) || 0;
  const h10 = Number(heights[z0 * res + x1]) || 0;
  const h01 = Number(heights[z1 * res + x0]) || 0;
  const h11 = Number(heights[z1 * res + x1]) || 0;
  return (h00 * (1 - dx) + h10 * dx) * (1 - dz) + (h01 * (1 - dx) + h11 * dx) * dz;
}

function ensureTerrain() {
  const [minX, minY, maxX, maxY] = getBounds();
  const info = project.terrain || {};
  if (!Array.isArray(info.heights) || !info.heights.length) {
    const res = Math.max(8, Number(info.resolution) || 24);
    project.terrain = { ...info, resolution: res, bounds: [minX, minY, maxX, maxY], heights: Array(res * res).fill(0) };
  } else {
    project.terrain.bounds = project.terrain.bounds || [minX, minY, maxX, maxY];
  }
  return terrainInfo();
}

function buildTerrain() {
  if (terrainMesh) {
    scene.remove(terrainMesh);
    terrainMesh.geometry.dispose();
    terrainMesh.material.dispose();
    terrainMesh = null;
  }
  const { minX, minY, maxX, maxY, res, heights } = ensureTerrain();
  const width = Math.max(1, maxX - minX);
  const depth = Math.max(1, maxY - minY);
  const geometry = new THREE.PlaneGeometry(width, depth, res, res);
  geometry.rotateX(-Math.PI / 2);
  geometry.translate((minX + maxX) / 2, 0, (minY + maxY) / 2);
  const position = geometry.attributes.position;
  let minH = Infinity, maxH = -Infinity;
  for (let index = 0; index < position.count; index += 1) {
    const y = terrainHeight(position.getX(index), position.getZ(index));
    position.setY(index, y);
    minH = Math.min(minH, y);
    maxH = Math.max(maxH, y);
  }
  const colors = [];
  for (let index = 0; index < position.count; index += 1) {
    if (accessMode) {
      const x = position.getX(index);
      const z = position.getZ(index);
      const dzdx = Math.abs(terrainHeight(x + 5, z) - terrainHeight(x - 5, z)) / 10 * 100;
      const dzdy = Math.abs(terrainHeight(x, z + 5) - terrainHeight(x, z - 5)) / 10 * 100;
      const grade = Math.max(dzdx, dzdy);
      const inClump = (project.retention?.clumps || []).some((clump) => pointInPolygon(x, z, clump.polygon || []));
      if (inClump || grade > 35) colors.push(0.72, 0.16, 0.12);
      else if (grade > 25) colors.push(0.82, 0.58, 0.12);
      else colors.push(0.16, 0.48, 0.28);
    } else {
      const f = Math.max(0, Math.min(1, (position.getY(index) - minH) / Math.max(1, maxH - minH)));
      colors.push(0.18 + f * 0.44, 0.30 + f * 0.30, 0.16 + f * 0.14);
    }
  }
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  geometry.computeVertexNormals();
  terrainMesh = new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, side: THREE.DoubleSide }),
  );
  terrainMesh.name = "terrain";
  scene.add(terrainMesh);
  const wire = new THREE.Mesh(
    geometry.clone(),
    new THREE.MeshBasicMaterial({ color: 0x1b2b24, wireframe: true, transparent: true, opacity: 0.18 }),
  );
  wire.name = "terrain_wire";
  terrainMesh.userData.wire = wire;
  scene.add(wire);
  updateTreeHeights();
}

function buildTrees() {
  if (treeGroup) {
    scene.remove(treeGroup);
    treeGroup.traverse((object) => {
      if (object.geometry) object.geometry.dispose();
      if (object.material) object.material.dispose();
    });
  }
  treeGroup = new THREE.Group();
  treeMeshes = [];
  treeById = new Map();
  const retained = new Set(project.retention?.tree_ids || []);
  for (const tree of dataset.trees || []) {
    const group = new THREE.Group();
    const height = Math.max(4, Number(tree.height_m) || 20);
    const dbh = Math.max(0.2, (Number(tree.dbh_cm) || 30) / 100);
    const base = terrainHeight(tree.x, tree.y);
    const trunk = new THREE.Mesh(
      new THREE.CylinderGeometry(dbh * 0.35, dbh * 0.5, height * 0.45, 5),
      new THREE.MeshStandardMaterial({ color: 0x5a4632, roughness: 0.9 }),
    );
    trunk.position.set(tree.x, base + height * 0.225, tree.y);
    const crown = new THREE.Mesh(
      new THREE.ConeGeometry(Math.max(1.5, dbh * 15), height * 0.65, 6),
      new THREE.MeshStandardMaterial({
        color: tree.retained ? 0x2fbfb0 : tree.inside ? 0x4f9a56 : 0x476064,
        roughness: 0.9,
      }),
    );
    crown.position.set(tree.x, base + height * 0.65, tree.y);
    crown.userData.treeId = tree.tree_id;
    trunk.userData.treeId = tree.tree_id;
    group.add(trunk, crown);
    treeGroup.add(group);
    treeMeshes.push(crown, trunk);
    treeById.set(tree.tree_id, { group, tree, crown, trunk, base: 0 });
  }
  scene.add(treeGroup);
  updateStats();
}

function updateTreeHeights() {
  for (const item of treeById.values()) {
    const base = terrainHeight(item.tree.x, item.tree.y);
    const height = Math.max(4, Number(item.tree.height_m) || 20);
    item.trunk.position.y = base + height * 0.225;
    item.crown.position.y = base + height * 0.65;
  }
}

function buildOverlays() {
  if (boundaryGroup) scene.remove(boundaryGroup);
  if (roadLine) scene.remove(roadLine);
  if (landingGroup) scene.remove(landingGroup);
  boundaryGroup = new THREE.Group();
  roadLine = null;
  handleMeshes = [];
  const polygon = project.block?.polygon || [];
  if (polygon.length >= 3) {
    const points = polygon.map(([x, y]) => new THREE.Vector3(Number(x), terrainHeight(Number(x), Number(y)) + 0.8, Number(y)));
    const line = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: 0xf08a24 }),
    );
    boundaryGroup.add(line);
    polygon.forEach(([x, y], index) => {
      const handle = new THREE.Mesh(
        new THREE.SphereGeometry(3.5, 10, 8),
        new THREE.MeshBasicMaterial({ color: index === selectedHandle ? 0xffe0a3 : 0xf08a24 }),
      );
      handle.position.set(Number(x), terrainHeight(Number(x), Number(y)) + 1.2, Number(y));
      handle.userData.vertex = index;
      handleMeshes.push(handle);
      boundaryGroup.add(handle);
    });
  }
  scene.add(boundaryGroup);
  const road = project.road?.points || [];
  if (road.length > 1) {
    const points = road.map(([x, y]) => new THREE.Vector3(Number(x), terrainHeight(Number(x), Number(y)) + 0.8, Number(y)));
    roadLine = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: 0xd8c58a }),
    );
    scene.add(roadLine);
  }
  const clumps = project.retention?.clumps || [];
  for (const clump of clumps) {
    const polygon = clump.polygon || [];
    if (polygon.length < 3) continue;
    const color = clump.kind === "riparian" ? 0x4a9fd8 : 0x2fbfb0;
    const points = polygon.map(([x, y]) => new THREE.Vector3(Number(x), terrainHeight(Number(x), Number(y)) + 0.9, Number(y)));
    const outline = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color }),
    );
    boundaryGroup.add(outline);
    const shape = new THREE.Shape();
    polygon.forEach(([x, y], index) => {
      if (index === 0) shape.moveTo(Number(x), Number(y)); else shape.lineTo(Number(x), Number(y));
    });
    const geometry = new THREE.ShapeGeometry(shape);
    geometry.rotateX(Math.PI / 2);
    const fill = new THREE.Mesh(
      geometry,
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.14, side: THREE.DoubleSide, depthWrite: false }),
    );
    fill.position.y = terrainHeight(polygon[0][0], polygon[0][1]) + 0.9;
    boundaryGroup.add(fill);
  }
  if (clumpDraft.length) {
    const points = clumpDraft.map(([x, y]) => new THREE.Vector3(Number(x), terrainHeight(Number(x), Number(y)) + 1.0, Number(y)));
    boundaryGroup.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: 0x8ff0e5 }),
    ));
  }
  if (streamDraft.length) {
    const halfWidth = Math.max(1, Number($("#stream-width")?.value || 30)) / 2;
    const points = streamDraft.map(([x, y]) => new THREE.Vector3(Number(x), terrainHeight(Number(x), Number(y)) + 1.1, Number(y)));
    boundaryGroup.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: 0x68b6ff, linewidth: 3 }),
    ));
    for (const [x, y] of [streamDraft[0], streamDraft[streamDraft.length - 1]]) {
      if (!Number.isFinite(Number(x))) continue;
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(Math.max(0.5, halfWidth - 0.6), halfWidth, 24),
        new THREE.MeshBasicMaterial({ color: 0x68b6ff, transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthWrite: false }),
      );
      ring.rotation.x = -Math.PI / 2;
      ring.position.set(Number(x), terrainHeight(Number(x), Number(y)) + 1.0, Number(y));
      boundaryGroup.add(ring);
    }
  }
  landingGroup = new THREE.Group();
  const [lx, ly] = [Number(project.landing.x), Number(project.landing.y)];
  const pad = new THREE.Mesh(
    new THREE.CircleGeometry(16, 24),
    new THREE.MeshStandardMaterial({ color: 0x8b876e, roughness: 0.95, side: THREE.DoubleSide }),
  );
  pad.rotation.x = -Math.PI / 2;
  pad.position.set(lx, terrainHeight(lx, ly) + 0.9, ly);
  landingGroup.add(pad);
  const pole = new THREE.Mesh(
    new THREE.CylinderGeometry(0.8, 1.3, 8, 8),
    new THREE.MeshStandardMaterial({ color: 0xf08a24 }),
  );
  pole.position.set(lx, terrainHeight(lx, ly) + 5, ly);
  landingGroup.add(pole);
  scene.add(landingGroup);
}

function rebuildAll() {
  buildTerrain();
  buildTrees();
  buildOverlays();
}

function updateStats() {
  const retained = new Set(project.retention?.tree_ids || []);
  const terrain = terrainInfo();
  const range = terrain.heights.length ? `${Math.min(...terrain.heights).toFixed(1)} … ${Math.max(...terrain.heights).toFixed(1)} m` : "flat";
  const area = stateArea(project.block.polygon);
  const clumps = project.retention?.clumps || [];
  $("#scene-stats").innerHTML = `<b>${area.toFixed(2)} ha</b> block<br><b>${dataset.trees.filter((tree) => tree.inside).length.toLocaleString()}</b> trees in block<br><b>${retained.size.toLocaleString()}</b> retained<br><b>${clumps.length}</b> clumps<br><b>${terrain.res}</b>× terrain grid<br><b>${range}</b> relief<br><span class="hint">${dirty ? "unsaved edits" : "saved"}</span>`;
  $("#project-id").textContent = `Project ID: ${project.project_id}`;
}

function stateArea(polygon) {
  let area = 0;
  for (let index = 0; index < polygon.length; index += 1) {
    const next = polygon[(index + 1) % polygon.length];
    area += Number(polygon[index][0]) * Number(next[1]) - Number(next[0]) * Number(polygon[index][1]);
  }
  return Math.abs(area) / 2 / 10000;
}

function fitView() {
  const [minX, minY, maxX, maxY] = getBounds();
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  const span = Math.max(30, maxX - minX, maxY - minY);
  camera.position.set(cx + span * 0.65, span * 0.65, cy + span * 0.8);
  controls.target.set(cx, 0, cy);
  controls.update();
  camera.lookAt(cx, 0, cy);
}

function setTool(next) {
  tool = next;
  if (next !== "clump") clumpDraft = [];
  if (next !== "stream") streamDraft = [];
  document.querySelectorAll("#tools [data-tool]").forEach((button) => button.classList.toggle("active", button.dataset.tool === next));
  controls.enableRotate = next === "orbit";
  controls.enablePan = true;
  const hints = {
    orbit: "Orbit",
    stream: "Click along the stream centreline; double-click to generate the riparian buffer",
    clump: "Click a clump ring; double-click to close it",
    retain: "Click trees to toggle retention",
    terrain: "Click to raise terrain; shift-click lowers",
    road: "Click to append road points",
    boundary: "Drag a boundary handle; shift-click to add a vertex",
    landing: "Click to move the landing",
  };
  setStatus(hints[next] || `${next} tool — click/drag in the scene`);
}

function pointerRay(event) {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
}

function groundPoint(event) {
  pointerRay(event);
  const hit = raycaster.intersectObject(terrainMesh, false)[0];
  return hit ? hit.point : null;
}

function toggleRetention(event) {
  pointerRay(event);
  const hit = raycaster.intersectObjects(treeMeshes, false)[0];
  if (!hit) return;
  pushHistory();
  const point = hit.point;
  const retained = new Set(project.retention?.tree_ids || []);
  const erase = event.shiftKey;
  let changed = false;
  for (const item of treeById.values()) {
    if (Math.hypot(item.tree.x - point.x, item.tree.y - point.z) > brush) continue;
    if (erase) retained.delete(item.tree.tree_id); else retained.add(item.tree.tree_id);
    item.tree.retained = retained.has(item.tree.tree_id);
    item.crown.material.color.setHex(retained.has(item.tree.tree_id) ? 0x2fbfb0 : item.tree.inside ? 0x4f9a56 : 0x476064);
    changed = true;
  }
  if (!changed) return;
  project.retention.tree_ids = [...retained];
  markDirty();
  updateStats();
}

function paintTerrain(event) {
  const point = groundPoint(event);
  if (!point) return;
  ensureTerrain();
  const { minX, minY, maxX, maxY, res, heights } = terrainInfo();
  const cellX = (maxX - minX) / res;
  const cellY = (maxY - minY) / res;
  const direction = ($("#lower").checked || event.shiftKey) ? -0.4 : 0.4;
  for (let row = 0; row < res; row += 1) {
    for (let col = 0; col < res; col += 1) {
      const x = minX + (col + 0.5) * cellX;
      const z = minY + (row + 0.5) * cellY;
      if (Math.hypot(x - point.x, z - point.z) > brush) continue;
      heights[row * res + col] = Math.max(-30, Math.min(30, Number(heights[row * res + col] || 0) + direction));
    }
  }
  rebuildAll();
  markDirty();
}

function onPointerDown(event) {
  if (!project || !terrainMesh) return;
  if (event.button !== 0 || tool === "orbit") return;
  if (tool === "retain") { toggleRetention(event); return; }
  if (tool === "terrain") { pushHistory(); paintTerrain(event); dragging = { type: "terrain" }; controls.enabled = false; return; }
  if (tool === "landing") {
    const point = groundPoint(event);
    if (!point) return;
    pushHistory();
    project.landing = { x: point.x, y: point.z };
    buildOverlays();
    updateStats();
    markDirty();
    return;
  }
  if (tool === "clump") {
    const point = groundPoint(event);
    if (!point) return;
    clumpDraft.push([point.x, point.z]);
    buildOverlays();
    markDirty();
    return;
  }
  if (tool === "stream") {
    const point = groundPoint(event);
    if (!point) return;
    streamDraft.push([point.x, point.z]);
    buildOverlays();
    return;
  }
  if (tool === "boundary") {
    pointerRay(event);
    const hit = raycaster.intersectObjects(handleMeshes, false)[0];
    if (hit) {
      pushHistory();
      selectedHandle = hit.object.userData.vertex;
      dragging = { type: "vertex" };
      controls.enabled = false;
      buildOverlays();
    } else if (event.shiftKey) {
      const point = groundPoint(event);
      if (!point) return;
      pushHistory();
      project.block.polygon.push([point.x, point.z]);
      selectedHandle = project.block.polygon.length - 1;
      buildOverlays();
      markDirty();
    }
  }
  if (tool === "road") {
    const point = groundPoint(event);
    if (!point) return;
    pushHistory();
    project.road.points = project.road.points || [];
    project.road.points.push([point.x, point.z]);
    buildOverlays();
    markDirty();
  }
}

function onPointerMove(event) {
  if (!dragging) return;
  if (dragging.type === "terrain") { paintTerrain(event); return; }
  if (dragging.type === "vertex" && selectedHandle != null) {
    const point = groundPoint(event);
    if (!point) return;
    project.block.polygon[selectedHandle] = [point.x, point.z];
    buildOverlays();
    updateStats();
    markDirty();
  }
}

function onPointerUp() {
  dragging = null;
  controls.enabled = true;
}

async function save() {
  if (!project) return null;
  setStatus("Saving…");
  try {
    project = await fetch(`${API}projects/${encodeURIComponent(projectId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(project),
    }).then((response) => {
      if (!response.ok) throw new Error(`save ${response.status}`);
      return response.json();
    });
    dirty = false;
    $("#project-name").textContent = `${project.label} · revision ${project.revision}`;
    setStatus("Saved");
    updateStats();
    return project;
  } catch (error) {
    setStatus(`Save failed: ${error.message}`, true);
    return null;
  }
}

async function runScenario() {
  if (!project) return;
  const saved = await save();
  if (!saved) return;
  setStatus("Running edited scenario…");
  try {
    const record = await fetch(`${API}projects/${encodeURIComponent(projectId)}/run`, { method: "POST" }).then((response) => {
      if (!response.ok) throw new Error(`run ${response.status}`);
      return response.json();
    });
    const link = $("#replay-link");
    link.href = `replay?project=${encodeURIComponent(projectId)}&run=${encodeURIComponent(record.run_id)}`;
    link.hidden = false;
    const warnings = Array.isArray(record.warnings) ? record.warnings : [];
    const kpis = record.kpis || {};
    $("#run-output").innerHTML = `<b>${Number(kpis.processed_volume_m3 || 0).toFixed(0)} m³</b> · ${(Number(kpis.makespan_s || 0) / 3600).toFixed(1)} h · ${Number(kpis.tree_count || 0).toLocaleString()} trees`
      + (warnings.length ? `<br><b>Blocked / warnings</b><ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>` : " · no warnings");
    setStatus(`Run ${record.run_id} complete${warnings.length ? ` · ${warnings.length} warning(s)` : ""}`);
  } catch (error) {
    setStatus(`Run failed: ${error.message}`, true);
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
}

function renameProject() {
  if (!project) return;
  const next = prompt("Project name", project.label || "");
  if (next === null || !next.trim()) return;
  pushHistory();
  project.label = next.trim();
  $("#project-name").textContent = `${project.label} · revision ${project.revision}`;
  markDirty();
}

async function duplicateProject() {
  if (!project) return;
  try {
    const copied = await fetch(`${API}projects/${encodeURIComponent(projectId)}/duplicate`, { method: "POST" }).then((response) => {
      if (!response.ok) throw new Error(`duplicate ${response.status}`);
      return response.json();
    });
    location.href = `3d?project=${encodeURIComponent(copied.project_id)}`;
  } catch (error) { setStatus(`Duplicate failed: ${error.message}`, true); }
}

async function init() {
  try {
    const projects = await fetch(`${API}projects`).then((response) => response.json());
    const id = projectId || projects.projects?.[0]?.project_id;
    if (!id) throw new Error("No project found.");
    project = await fetch(`${API}projects/${encodeURIComponent(id)}`).then((response) => response.json());
    dataset = await fetch(`${API}projects/${encodeURIComponent(id)}/dataset`).then((response) => response.json());
    $("#project-name").textContent = `${project.label} · revision ${project.revision}`;
    $("#back-plan").href = `./?project=${encodeURIComponent(id)}`;
    buildTerrain();
    buildTrees();
    buildOverlays();
    fitView();
    updateStats();
    setStatus("3D editor ready");
  } catch (error) { setStatus(`Load failed: ${error.message}`, true); }
}

function resize() {
  const width = $("#scene").clientWidth;
  const height = $("#scene").clientHeight;
  renderer.setSize(width, height);
  camera.aspect = width / Math.max(1, height);
  camera.updateProjectionMatrix();
}

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}

document.querySelectorAll("#tools [data-tool]").forEach((button) => button.addEventListener("click", () => setTool(button.dataset.tool)));
$("#save").addEventListener("click", save);
$("#run").addEventListener("click", runScenario);
$("#undo").addEventListener("click", undo);
$("#redo").addEventListener("click", redo);
$("#rename").addEventListener("click", renameProject);
$("#duplicate").addEventListener("click", duplicateProject);
$("#fit").addEventListener("click", fitView);
$("#brush").addEventListener("input", () => { brush = Number($("#brush").value); $("#brush-label").textContent = `${brush} m`; });
$("#access-map").addEventListener("change", () => { accessMode = $("#access-map").checked; buildTerrain(); buildOverlays(); updateStats(); });
$("#stream-width").addEventListener("input", () => {
  $("#stream-width-label").textContent = `${Number($("#stream-width").value)} m`;
  buildOverlays();
});
async function finishStream() {
  if (!project || streamDraft.length < 2) return;
  const width = Math.max(1, Number($("#stream-width")?.value || 30));
  const centerline = streamDraft.slice();
  setStatus(`Building ${width} m stream buffer…`);
  try {
    const response = await fetch(`${API}geometry/stream-buffer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ points: centerline, width_m: width }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || response.statusText);
    }
    const result = await response.json();
    pushHistory();
    project.retention.clumps = project.retention.clumps || [];
    project.retention.clumps.push({
      id: `stream-${Date.now().toString(36)}`,
      label: `stream riparian buffer (${width} m)`,
      kind: "riparian",
      source: "stream",
      buffer_m: width,
      centerline,
      polygon: result.polygon,
    });
    streamDraft = [];
    buildOverlays();
    updateStats();
    markDirty();
    setStatus(`Added ${width} m stream riparian buffer`);
  } catch (error) {
    setStatus(`Stream buffer failed: ${error.message}`, true);
  }
}
function finalizeClump() {
  if (tool !== "clump" || clumpDraft.length < 3) return;
  pushHistory();
  project.retention.clumps = project.retention.clumps || [];
  const kind = $("#clump-kind")?.value || "retention";
  project.retention.clumps.push({
    id: `clump-${Date.now().toString(36)}`,
    label: kind === "riparian" ? "riparian buffer" : kind === "corridor" ? "no-harvest corridor" : "retention clump",
    kind,
    polygon: clumpDraft.slice(),
  });
  clumpDraft = [];
  buildOverlays();
  markDirty();
  updateStats();
}

renderer.domElement.addEventListener("pointerdown", onPointerDown);
renderer.domElement.addEventListener("dblclick", () => {
  if (tool === "stream") finishStream();
  else finalizeClump();
});
renderer.domElement.addEventListener("pointermove", onPointerMove);
renderer.domElement.addEventListener("pointerup", onPointerUp);
renderer.domElement.addEventListener("pointercancel", onPointerUp);
window.addEventListener("keydown", (event) => {
  if (event.key === "Delete" && tool === "boundary" && selectedHandle != null && project.block.polygon.length > 3) {
    pushHistory();
    project.block.polygon.splice(selectedHandle, 1);
    selectedHandle = null;
    buildOverlays();
    markDirty();
  }
});
window.addEventListener("resize", resize);
resize();
animate();
init();
