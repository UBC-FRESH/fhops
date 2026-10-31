const API = new URL("api/", document.baseURI).pathname;
const $ = (selector) => document.querySelector(selector);
const canvas = $("#map");
const ctx = canvas.getContext("2d");

const state = {
  cases: [],
  projects: [],
  project: null,
  dataset: null,
  trees: [],
  tool: "select",
  selectedTree: null,
  selectedVertex: null,
  brush: 25,
  scale: 1,
  ox: 0,
  oy: 0,
  history: [],
  future: [],
  dirty: false,
  dragging: null,
  panning: null,
  space: false,
  lastStatus: "",
};

const COLORS = {
  block: "#1d3526",
  blockLine: "#f08a24",
  tree: "#4f9a56",
  retained: "#2fbfb0",
  outside: "#476064",
  road: "#77745f",
  landing: "#f08a24",
  grid: "#192226",
};

async function api(path, options = {}) {
  const response = await fetch(API + path.replace(/^\/+/, ""), {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (_error) { /* ignore */ }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

function setStatus(text, error = false) {
  const node = $("#status");
  node.textContent = text;
  node.style.color = error ? "#ff8b80" : "";
  state.lastStatus = text;
}

function markDirty() {
  state.dirty = true;
  setStatus("Unsaved changes");
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.max(1, Math.round(rect.width * dpr));
  canvas.height = Math.max(1, Math.round(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  render();
}

function fitView() {
  if (!state.project) return;
  const points = [];
  for (const point of state.project.block?.polygon || []) points.push([Number(point[0]), Number(point[1])]);
  for (const tree of state.trees) points.push([tree.x, tree.y]);
  if (state.project.landing) points.push([Number(state.project.landing.x), Number(state.project.landing.y)]);
  for (const point of state.project.road?.points || []) points.push([Number(point[0]), Number(point[1])]);
  if (!points.length) return;
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, maxX - minX);
  const height = Math.max(1, maxY - minY);
  state.scale = Math.min(rect.width / width, rect.height / height) * 0.82;
  state.ox = rect.width / 2 - ((minX + maxX) / 2) * state.scale;
  state.oy = rect.height / 2 + ((minY + maxY) / 2) * state.scale;
  render();
}

function screenToWorld(x, y) {
  return [(x - state.ox) / state.scale, (state.oy - y) / state.scale];
}

function worldToScreen(x, y) {
  return [x * state.scale + state.ox, state.oy - y * state.scale];
}

function pointInPolygon(x, y, polygon) {
  let inside = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index++) {
    const xi = Number(polygon[index][0]), yi = Number(polygon[index][1]);
    const xj = Number(polygon[previous][0]), yj = Number(polygon[previous][1]);
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function polygonAreaHa(polygon) {
  let area = 0;
  for (let index = 0; index < polygon.length; index += 1) {
    const next = polygon[(index + 1) % polygon.length];
    area += Number(polygon[index][0]) * Number(next[1]) - Number(next[0]) * Number(polygon[index][1]);
  }
  return Math.abs(area) / 2 / 10000;
}

function treeRadiusPx() {
  return Math.max(1.4, Math.min(3.2, state.scale * 1.2));
}

function drawGrid(rect) {
  const [left, top] = screenToWorld(0, 0);
  const [right, bottom] = screenToWorld(rect.width, rect.height);
  const step = state.scale > 4 ? 10 : state.scale > 1.5 ? 25 : 50;
  ctx.lineWidth = 1;
  ctx.strokeStyle = COLORS.grid;
  ctx.beginPath();
  for (let x = Math.floor(left / step) * step; x <= right; x += step) {
    const [sx] = worldToScreen(x, 0);
    ctx.moveTo(sx, 0); ctx.lineTo(sx, rect.height);
  }
  for (let y = Math.floor(bottom / step) * step; y <= top; y += step) {
    const [, sy] = worldToScreen(0, y);
    ctx.moveTo(0, sy); ctx.lineTo(rect.width, sy);
  }
  ctx.stroke();
}

function drawTerrain(rect) {
  const terrain = state.project?.terrain;
  if (!terrain || !Array.isArray(terrain.heights) || terrain.heights.length === 0) return;
  const res = Number(terrain.resolution) || 24;
  const polygon = state.project.block.polygon;
  const xs = polygon.map((point) => Number(point[0]));
  const ys = polygon.map((point) => Number(point[1]));
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const cellX = (maxX - minX) / res;
  const cellY = (maxY - minY) / res;
  ctx.save();
  ctx.beginPath();
  for (let index = 0; index < polygon.length; index += 1) {
    const [sx, sy] = worldToScreen(Number(polygon[index][0]), Number(polygon[index][1]));
    if (index === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
  }
  ctx.closePath();
  ctx.clip();
  for (let row = 0; row < res; row += 1) {
    for (let col = 0; col < res; col += 1) {
      const height = Number(terrain.heights[row * res + col]) || 0;
      if (Math.abs(height) < 0.01) continue;
      const x0 = minX + col * cellX;
      const y0 = minY + row * cellY;
      const [sx, sy] = worldToScreen(x0, y0 + cellY);
      const width = cellX * state.scale + 1;
      const heightPx = cellY * state.scale + 1;
      const strength = Math.min(0.42, Math.abs(height) / 5);
      ctx.fillStyle = height > 0 ? `rgba(180,128,72,${strength})` : `rgba(55,120,150,${strength})`;
      ctx.fillRect(sx, sy, width, heightPx);
    }
  }
  ctx.restore();
}

function draw() {
  const rect = canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.fillStyle = "#0b0f11";
  ctx.fillRect(0, 0, rect.width, rect.height);
  if (!state.project) return;
  drawGrid(rect);

  const polygon = state.project.block?.polygon || [];
  if (polygon.length >= 3) {
    ctx.beginPath();
    for (let index = 0; index < polygon.length; index += 1) {
      const [sx, sy] = worldToScreen(Number(polygon[index][0]), Number(polygon[index][1]));
      if (index === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
    }
    ctx.closePath();
    ctx.fillStyle = "rgba(33, 62, 43, 0.72)";
    ctx.fill();
    drawTerrain(rect);
    ctx.strokeStyle = COLORS.blockLine;
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  const road = state.project.road?.points || [];
  if (road.length > 1) {
    ctx.beginPath();
    for (let index = 0; index < road.length; index += 1) {
      const [sx, sy] = worldToScreen(Number(road[index][0]), Number(road[index][1]));
      if (index === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
    }
    ctx.strokeStyle = COLORS.road;
    ctx.lineWidth = Math.max(2, 10 * state.scale);
    ctx.lineCap = "round";
    ctx.stroke();
    ctx.strokeStyle = "#9e9a7a";
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  const radius = treeRadiusPx();
  for (const tree of state.trees) {
    const [sx, sy] = worldToScreen(tree.x, tree.y);
    if (sx < -10 || sy < -10 || sx > rect.width + 10 || sy > rect.height + 10) continue;
    ctx.beginPath();
    ctx.arc(sx, sy, tree.tree_id === state.selectedTree ? radius + 2 : radius, 0, Math.PI * 2);
    ctx.fillStyle = tree.tree_id === state.selectedTree
      ? "#f7d08a"
      : tree.retained ? COLORS.retained : tree.inside ? COLORS.tree : COLORS.outside;
    ctx.fill();
    if (tree.retained) {
      ctx.strokeStyle = "#bff8ef";
      ctx.lineWidth = 0.8;
      ctx.stroke();
    }
  }

  if (state.project.landing) {
    const [sx, sy] = worldToScreen(Number(state.project.landing.x), Number(state.project.landing.y));
    const landingRadius = Math.max(7, 18 * Math.min(state.scale, 2.5));
    ctx.beginPath();
    ctx.arc(sx, sy, landingRadius, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(240,138,36,0.35)";
    ctx.fill();
    ctx.strokeStyle = COLORS.landing;
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = "#f3c795";
    ctx.font = "11px system-ui";
    ctx.fillText("landing", sx + landingRadius + 4, sy + 4);
  }

  if (state.project.machines) {
    let index = 0;
    for (const machine of state.project.machines) {
      if (!["feller", "loader", "processor", "skidder", "yarder"].some((role) => machine.role.includes(role))) continue;
      const [sx, sy] = worldToScreen(Number(state.project.landing.x) + (index - 1) * 2.8, Number(state.project.landing.y));
      ctx.fillStyle = machine.role.includes("loader") ? "#27ae60" : machine.role.includes("processor") ? "#f1c40f" : machine.role.includes("yarder") ? "#c678dd" : "#f08a24";
      ctx.fillRect(sx - 3, sy - 3, 6, 6);
      index += 1;
    }
  }

  if (state.tool === "boundary") {
    for (let index = 0; index < polygon.length; index += 1) {
      const [sx, sy] = worldToScreen(Number(polygon[index][0]), Number(polygon[index][1]));
      ctx.beginPath();
      ctx.arc(sx, sy, index === state.selectedVertex ? 7 : 4.5, 0, Math.PI * 2);
      ctx.fillStyle = index === state.selectedVertex ? "#ffe0a3" : COLORS.blockLine;
      ctx.fill();
      ctx.strokeStyle = "#1a1d19";
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  }
}

function render() {
  draw();
  renderStats();
  renderMachines();
  renderProjectMeta();
  $("#notes").value = state.project?.notes || "";
  $("#retention-target").value = Math.round((Number(state.project?.retention?.target_fraction_basal_area) || 0) * 100);
}

function recomputeStats() {
  if (!state.project) return;
  const polygon = state.project.block.polygon;
  const retained = new Set(state.project.retention?.tree_ids || []);
  let insideCount = 0;
  let retainedCount = 0;
  let totalBa = 0;
  let retainedBa = 0;
  for (const tree of state.trees) {
    tree.inside = pointInPolygon(tree.x, tree.y, polygon);
    tree.retained = retained.has(tree.tree_id);
    const ba = Math.PI / 4 * (tree.dbh_cm / 100) ** 2;
    if (tree.inside) {
      insideCount += 1;
      totalBa += ba;
      if (tree.retained) {
        retainedCount += 1;
        retainedBa += ba;
      }
    }
  }
  state.dataset.stats = {
    block_area_ha: polygonAreaHa(polygon),
    tree_count: state.trees.length,
    inside_tree_count: insideCount,
    retained_tree_count: retainedCount,
    retained_basal_area_fraction: totalBa ? retainedBa / totalBa : 0,
    total_basal_area_m2: totalBa,
  };
}

function renderStats() {
  const stats = state.dataset?.stats;
  if (!stats) return;
  const items = [
    [stats.block_area_ha.toFixed(2), "block ha"],
    [stats.inside_tree_count.toLocaleString(), "trees in block"],
    [`${Math.round(stats.retained_basal_area_fraction * 100)}%`, "retained BA"],
    [stats.retained_tree_count.toLocaleString(), "retained trees"],
  ];
  $("#stand-stats").innerHTML = items.map(([value, label]) => `<div class="stat"><b>${value}</b><span>${label}</span></div>`).join("");
  $("#boundary-info").innerHTML = `${state.project.block.polygon.length} vertices · ${stats.block_area_ha.toFixed(2)} ha<br><span class="muted">Drag vertices; double-click an edge to add one; Delete removes the selected vertex.</span>`;
}

function renderProjectMeta() {
  if (!state.project) {
    $("#project-meta").textContent = "Open or create a project.";
    return;
  }
  const base = state.cases.find((item) => item.case_id === state.project.base_case_id);
  $("#project-meta").innerHTML = `<b>${escapeHtml(state.project.label)}</b><br><span class="muted">${escapeHtml(base?.label || state.project.base_case_id)} · revision ${state.project.revision || 1}${state.dirty ? " · unsaved" : ""}</span>`;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
}

function policyOptions(selected) {
  const presets = state.dataset?.policy_presets || {};
  return Object.entries(presets).map(([key, value]) => `<option value="${key}" ${key === selected ? "selected" : ""}>${escapeHtml(value.label)}</option>`).join("");
}

function renderMachines() {
  if (!state.project) return;
  const catalog = state.project.catalog || [];
  const active = new Set(state.project.machines.map((machine) => machine.id));
  const list = $("#machine-list");
  list.innerHTML = "";
  for (const machine of state.project.machines) {
    const row = document.createElement("div");
    row.className = "machine";
    row.innerHTML = `<div><div class="id">${escapeHtml(machine.id)}</div><div class="role">${escapeHtml(machine.role)}</div></div>
      <select data-machine="${escapeHtml(machine.id)}">${policyOptions(machine.policy || "steady")}</select>
      <button title="Remove machine" data-remove="${escapeHtml(machine.id)}">×</button>`;
    list.append(row);
  }
  for (const select of list.querySelectorAll("select[data-machine]")) {
    select.addEventListener("change", () => {
      pushHistory();
      const machine = state.project.machines.find((item) => item.id === select.dataset.machine);
      machine.policy = select.value;
      state.project.operator_policies[machine.id] = select.value;
      markDirty();
    });
  }
  for (const button of list.querySelectorAll("button[data-remove]")) {
    button.addEventListener("click", () => removeMachine(button.dataset.remove));
  }
  const available = catalog.filter((machine) => !active.has(machine.id));
  const catalogNode = $("#machine-catalog");
  catalogNode.innerHTML = available.length
    ? available.map((machine) => `<option value="${escapeHtml(machine.id)}">${escapeHtml(machine.id)} · ${escapeHtml(machine.role)}</option>`).join("")
    : '<option value="">No machines left in catalog</option>';
  $("#add-machine").disabled = !available.length;
}

function addMachine() {
  const id = $("#machine-catalog").value;
  if (!id || !state.project) return;
  const catalog = state.project.catalog || [];
  const source = catalog.find((machine) => machine.id === id);
  if (!source) return;
  pushHistory();
  state.project.machines.push({ id: source.id, role: source.role, type: source.role, policy: "steady", source: "added" });
  state.project.operator_policies[source.id] = "steady";
  markDirty();
  render();
}

function removeMachine(id) {
  pushHistory();
  state.project.machines = state.project.machines.filter((machine) => machine.id !== id);
  delete state.project.operator_policies[id];
  markDirty();
  render();
}

function pushHistory() {
  if (!state.project) return;
  state.history.push(JSON.stringify(state.project));
  if (state.history.length > 60) state.history.shift();
  state.future = [];
}

function restoreHistory(json) {
  state.project = JSON.parse(json);
  state.dataset.project = state.project;
  recomputeStats();
  render();
  markDirty();
}

function undo() {
  if (!state.history.length) return;
  state.future.push(JSON.stringify(state.project));
  restoreHistory(state.history.pop());
}

function redo() {
  if (!state.future.length) return;
  state.history.push(JSON.stringify(state.project));
  restoreHistory(state.future.pop());
}

function setTool(tool) {
  state.tool = tool;
  state.selectedVertex = null;
  document.querySelectorAll("#tools [data-tool]").forEach((button) => button.classList.toggle("active", button.dataset.tool === tool));
  const hints = {
    select: "Inspect trees. Drag empty space to pan.",
    landing: "Click to move the landing.",
    boundary: "Drag boundary vertices; double-click an edge to insert; Delete removes selected vertex.",
    retain: "Paint retention trees. Hold Shift to clear retention.",
    road: "Click to append road points. The road is stored with the project.",
    terraform: "Raise terrain with Terrain selected; hold Shift to lower. Visual prototype.",
  };
  $("#hint").textContent = hints[tool] || "";
  render();
}

function selectTreeAt(x, y) {
  let nearest = null;
  let distance = Infinity;
  for (const tree of state.trees) {
    const [sx, sy] = worldToScreen(tree.x, tree.y);
    const d = Math.hypot(sx - x, sy - y);
    if (d < Math.max(7, treeRadiusPx() + 3) && d < distance) {
      nearest = tree;
      distance = d;
    }
  }
  return nearest;
}

function treeBrush(world, erase = false) {
  if (!state.project) return;
  const radius = state.brush;
  const retained = new Set(state.project.retention.tree_ids || []);
  for (const tree of state.trees) {
    if (Math.hypot(tree.x - world[0], tree.y - world[1]) > radius) continue;
    if (erase) retained.delete(tree.tree_id);
    else retained.add(tree.tree_id);
  }
  state.project.retention.tree_ids = [...retained];
  recomputeStats();
  markDirty();
  render();
}

function ensureTerrain() {
  const project = state.project;
  if (!project) return;
  if (!Array.isArray(project.terrain.heights) || project.terrain.heights.length === 0) {
    const res = Number(project.terrain.resolution) || 24;
    project.terrain.resolution = res;
    const xs = project.block.polygon.map((point) => Number(point[0]));
    const ys = project.block.polygon.map((point) => Number(point[1]));
    project.terrain.bounds = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
    project.terrain.heights = Array(res * res).fill(0);
  }
}

function paintTerrain(world, direction) {
  ensureTerrain();
  const terrain = state.project.terrain;
  const res = terrain.resolution;
  const [minX, minY, maxX, maxY] = terrain.bounds;
  const cellX = (maxX - minX) / res;
  const cellY = (maxY - minY) / res;
  for (let row = 0; row < res; row += 1) {
    for (let col = 0; col < res; col += 1) {
      const cx = minX + (col + 0.5) * cellX;
      const cy = minY + (row + 0.5) * cellY;
      if (Math.hypot(cx - world[0], cy - world[1]) > state.brush) continue;
      const index = row * res + col;
      terrain.heights[index] = Math.max(-5, Math.min(5, Number(terrain.heights[index] || 0) + direction * 0.35));
    }
  }
  markDirty();
  render();
}

function nearestBoundaryVertex(x, y) {
  if (!state.project) return -1;
  let best = -1;
  let bestDistance = 14;
  state.project.block.polygon.forEach((point, index) => {
    const [sx, sy] = worldToScreen(Number(point[0]), Number(point[1]));
    const distance = Math.hypot(sx - x, sy - y);
    if (distance < bestDistance) {
      best = index;
      bestDistance = distance;
    }
  });
  return best;
}

function nearestBoundaryEdge(x, y) {
  const polygon = state.project?.block?.polygon || [];
  let best = null;
  let bestDistance = 12;
  for (let index = 0; index < polygon.length; index += 1) {
    const a = worldToScreen(Number(polygon[index][0]), Number(polygon[index][1]));
    const b = worldToScreen(Number(polygon[(index + 1) % polygon.length][0]), Number(polygon[(index + 1) % polygon.length][1]));
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const length = Math.hypot(dx, dy) || 1;
    const t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / (length * length)));
    const distance = Math.hypot(x - (a[0] + dx * t), y - (a[1] + dy * t));
    if (distance < bestDistance) {
      bestDistance = distance;
      const world = screenToWorld(a[0] + dx * t, a[1] + dy * t);
      best = { index: index + 1, point: [world[0], world[1]] };
    }
  }
  return best;
}

function onPointerDown(event) {
  if (!state.project) return;
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  if (event.button === 1 || state.space) {
    state.panning = { x, y, ox: state.ox, oy: state.oy };
    return;
  }
  const world = screenToWorld(x, y);
  if (state.tool === "select") {
    const tree = selectTreeAt(x, y);
    if (tree) {
      state.selectedTree = tree.tree_id;
      render();
    } else {
      state.panning = { x, y, ox: state.ox, oy: state.oy };
    }
    return;
  }
  if (state.tool === "landing") {
    pushHistory();
    let next = [world[0], world[1]];
    const road = state.project.road?.points || [];
    if (road.length > 1) {
      let best = null;
      let bestDistance = 45;
      for (let index = 0; index < road.length - 1; index += 1) {
        const a = road[index];
        const b = road[index + 1];
        const dx = b[0] - a[0], dy = b[1] - a[1];
        const lengthSq = dx * dx + dy * dy || 1;
        const t = Math.max(0, Math.min(1, ((world[0] - a[0]) * dx + (world[1] - a[1]) * dy) / lengthSq));
        const px = a[0] + dx * t, py = a[1] + dy * t;
        const distance = Math.hypot(world[0] - px, world[1] - py);
        if (distance < bestDistance) { best = [px, py]; bestDistance = distance; }
      }
      if (best) next = best;
    }
    state.project.landing = { x: next[0], y: next[1] };
    markDirty();
    render();
    return;
  }
  if (state.tool === "boundary") {
    const vertex = nearestBoundaryVertex(x, y);
    if (vertex >= 0) {
      pushHistory();
      state.selectedVertex = vertex;
      state.dragging = { type: "vertex", vertex };
      canvas.setPointerCapture(event.pointerId);
      render();
    }
    return;
  }
  if (state.tool === "retain") {
    pushHistory();
    state.dragging = { type: "retain" };
    treeBrush(world, event.shiftKey);
    canvas.setPointerCapture(event.pointerId);
    return;
  }
  if (state.tool === "road") {
    pushHistory();
    if (!state.project.road.points) state.project.road.points = [];
    state.project.road.points.push([world[0], world[1]]);
    markDirty();
    render();
    return;
  }
  if (state.tool === "terraform") {
    pushHistory();
    state.dragging = { type: "terraform", direction: event.shiftKey ? -1 : 1 };
    paintTerrain(world, state.dragging.direction);
    canvas.setPointerCapture(event.pointerId);
  }
}

function onPointerMove(event) {
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  if (state.panning) {
    state.ox = state.panning.ox + (x - state.panning.x);
    state.oy = state.panning.oy + (y - state.panning.y);
    draw();
    return;
  }
  if (!state.dragging) return;
  const world = screenToWorld(x, y);
  if (state.dragging.type === "vertex") {
    state.project.block.polygon[state.dragging.vertex] = [world[0], world[1]];
    recomputeStats();
    markDirty();
    render();
  } else if (state.dragging.type === "retain") {
    treeBrush(world, event.shiftKey);
  } else if (state.dragging.type === "terraform") {
    paintTerrain(world, state.dragging.direction);
  }
}

function onPointerUp() {
  state.panning = null;
  state.dragging = null;
}

function onDoubleClick(event) {
  if (state.tool !== "boundary" || !state.project) return;
  const rect = canvas.getBoundingClientRect();
  const edge = nearestBoundaryEdge(event.clientX - rect.left, event.clientY - rect.top);
  if (!edge) return;
  pushHistory();
  state.project.block.polygon.splice(edge.index, 0, edge.point);
  state.selectedVertex = edge.index;
  recomputeStats();
  markDirty();
  render();
}

function onWheel(event) {
  event.preventDefault();
  if (!state.project) return;
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  const world = screenToWorld(x, y);
  const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
  state.scale = Math.max(0.02, Math.min(30, state.scale * factor));
  state.ox = x - world[0] * state.scale;
  state.oy = y + world[1] * state.scale;
  draw();
}

function saveProject() {
  if (!state.project) return;
  setStatus("Saving…");
  api(`projects/${encodeURIComponent(state.project.project_id)}`, {
    method: "PUT",
    body: JSON.stringify(state.project),
  }).then((saved) => {
    state.project = saved;
    state.dataset.project = saved;
    state.dirty = false;
    render();
    setStatus(`Saved revision ${saved.revision}`);
    refreshProjectSelect();
  }).catch((error) => setStatus(`Save failed: ${error.message}`, true));
}

async function loadProject(projectId) {
  setStatus("Loading project…");
  try {
    const dataset = await api(`projects/${encodeURIComponent(projectId)}/dataset`);
    state.project = dataset.project;
    state.dataset = dataset;
    state.trees = dataset.trees;
    state.history = [];
    state.future = [];
    state.dirty = false;
    state.selectedTree = null;
    state.selectedVertex = null;
    state.scale = 1;
    recomputeStats();
    resizeCanvas();
    fitView();
    setStatus(`Loaded ${state.project.label}`);
    history.replaceState(null, "", `?project=${encodeURIComponent(projectId)}`);
  } catch (error) {
    setStatus(`Load failed: ${error.message}`, true);
  }
}

async function refreshProjectSelect() {
  try {
    const payload = await api("projects");
    state.projects = payload.projects || [];
    const select = $("#project-select");
    const current = state.project?.project_id || "";
    select.innerHTML = '<option value="">Projects…</option>' + state.projects.map((project) => `<option value="${escapeHtml(project.project_id)}" ${project.project_id === current ? "selected" : ""}>${escapeHtml(project.label || project.project_id)}</option>`).join("");
  } catch (_error) { /* ignore */ }
}

async function loadCases() {
  const payload = await api("cases");
  state.cases = payload.cases || [];
  $("#case-select").innerHTML = state.cases.map((item) => `<option value="${escapeHtml(item.case_id)}">${escapeHtml(item.label)} · ${escapeHtml(item.block_id)}</option>`).join("");
}

function openNewDialog() {
  $("#new-dialog").showModal();
}

async function createNew() {
  const caseId = $("#case-select").value;
  if (!caseId) return;
  setStatus("Creating project…");
  try {
    const project = await api("projects", { method: "POST", body: JSON.stringify({ case_id: caseId }) });
    $("#new-dialog").close();
    await refreshProjectSelect();
    await loadProject(project.project_id);
  } catch (error) {
    setStatus(`Create failed: ${error.message}`, true);
  }
}

async function runScenario() {
  if (!state.project) return;
  setStatus("Saving before run…");
  try {
    const saved = await api(`projects/${encodeURIComponent(state.project.project_id)}`, {
      method: "PUT", body: JSON.stringify(state.project),
    });
    state.project = saved;
    state.dataset.project = saved;
    state.dirty = false;
    setStatus("Running edited scenario…");
    $("#run-result").textContent = "Simulation running…";
    const record = await api(`projects/${encodeURIComponent(state.project.project_id)}/run`, { method: "POST" });
    const kpis = record.kpis || {};
    const rows = [
      ["trees", kpis.tree_count ?? "—"],
      ["volume m³", kpis.processed_volume_m3 ? Number(kpis.processed_volume_m3).toFixed(1) : "—"],
      ["makespan h", kpis.makespan_s ? (Number(kpis.makespan_s) / 3600).toFixed(1) : "—"],
      ["unreachable", kpis.unreachable_count ?? "—"],
    ];
    $("#run-result").innerHTML = `<b>Run ${escapeHtml(record.run_id)}</b><div class="stat-grid" style="margin-top:7px">${rows.map(([label, value]) => `<div class="stat"><b>${value}</b><span>${label}</span></div>`).join("")}</div><p><a class="back" href="/replay?project=${encodeURIComponent(state.project.project_id)}&run=${encodeURIComponent(record.run_id)}" target="_blank">Open 3D replay →</a></p>`;
    setStatus(`Run complete · ${record.run_id}`);
    renderProjectMeta();
  } catch (error) {
    setStatus(`Run failed: ${error.message}`, true);
    $("#run-result").textContent = `Run failed: ${error.message}`;
  }
}

function bindEvents() {
  window.addEventListener("resize", resizeCanvas);
  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerUp);
  canvas.addEventListener("pointercancel", onPointerUp);
  canvas.addEventListener("dblclick", onDoubleClick);
  canvas.addEventListener("wheel", onWheel, { passive: false });
  document.querySelectorAll("#tools [data-tool]").forEach((button) => button.addEventListener("click", () => setTool(button.dataset.tool)));
  $("#fit").addEventListener("click", fitView);
  $("#brush-radius").addEventListener("input", () => {
    state.brush = Number($("#brush-radius").value);
    $("#brush-output").textContent = `${state.brush} m`;
  });
  $("#undo").addEventListener("click", undo);
  $("#redo").addEventListener("click", redo);
  $("#save").addEventListener("click", saveProject);
  $("#run").addEventListener("click", runScenario);
  $("#add-machine").addEventListener("click", addMachine);
  $("#new-project").addEventListener("click", openNewDialog);
  $("#project-select").addEventListener("change", (event) => { if (event.target.value) loadProject(event.target.value); });
  $("#retention-target").addEventListener("change", () => {
    if (!state.project) return;
    pushHistory();
    state.project.retention.target_fraction_basal_area = Math.max(0, Math.min(1, Number($("#retention-target").value) / 100));
    markDirty();
  });
  $("#notes").addEventListener("change", () => { if (state.project) { pushHistory(); state.project.notes = $("#notes").value; markDirty(); } });
  $("#reset-boundary").addEventListener("click", () => {
    if (!state.project) return;
    // Base boundary is preserved in the original case; create a rectangular
    // fallback from the current tree bounds if it is not available.
    pushHistory();
    if (Array.isArray(state.project.block.base_polygon)) {
      state.project.block.polygon = JSON.parse(JSON.stringify(state.project.block.base_polygon));
    }
    recomputeStats();
    markDirty();
    render();
  });
  $("#new-form").addEventListener("submit", (event) => {
    event.preventDefault();
    createNew();
  });
  $("#case-select").addEventListener("change", () => { if (!state.project) return; });
  window.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      if (event.shiftKey) redo(); else undo();
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      saveProject();
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
      event.preventDefault();
      redo();
    } else if (event.key === " " && event.target === document.body) {
      event.preventDefault();
      state.space = true;
    } else if (event.key === "Delete" && state.tool === "boundary" && state.selectedVertex != null) {
      if (state.project.block.polygon.length > 3) {
        pushHistory();
        state.project.block.polygon.splice(state.selectedVertex, 1);
        state.selectedVertex = null;
        recomputeStats();
        markDirty();
        render();
      }
    }
  });
  window.addEventListener("keyup", (event) => { if (event.key === " ") state.space = false; });
}

async function init() {
  bindEvents();
  await loadCases();
  await refreshProjectSelect();
  const params = new URLSearchParams(location.search);
  if (params.get("project")) {
    await loadProject(params.get("project"));
  } else if (state.projects.length) {
    await loadProject(state.projects[0].project_id);
  } else {
    openNewDialog();
  }
  resizeCanvas();
}

init().catch((error) => setStatus(`Startup failed: ${error.message}`, true));
