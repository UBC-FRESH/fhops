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
  clumpDraft: [],
  streamDraft: [],
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

function projectLandings(project = state.project) {
  const items = (project?.landings || []).filter(
    (landing) => Number.isFinite(Number(landing.x)) && Number.isFinite(Number(landing.y)),
  );
  if (items.length) return items;
  if (project?.landing) {
    return [{ id: "landing-main", label: "Landing", x: project.landing.x, y: project.landing.y }];
  }
  return [];
}

function roadSegments(project = state.project) {
  const road = project?.road || {};
  const segments = (road.segments || []).filter((segment) => Array.isArray(segment.points) && segment.points.length >= 2);
  if (segments.length) return segments;
  if (Array.isArray(road.points) && road.points.length >= 2) {
    return [{ id: "road-main", label: "Main road", points: road.points }];
  }
  return [];
}

function ensureRoadSegments(project) {
  if (!project.road) project.road = { points: [] };
  if (!Array.isArray(project.road.segments) || !project.road.segments.length) {
    project.road.segments = [{
      id: "road-main",
      label: "Main road",
      points: Array.isArray(project.road.points) ? project.road.points.slice() : [],
    }];
  }
  return project.road.segments;
}

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
  for (const landing of projectLandings()) points.push([Number(landing.x), Number(landing.y)]);
  for (const segment of roadSegments()) {
    for (const point of segment.points || []) points.push([Number(point[0]), Number(point[1])]);
  }
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

  for (const segment of roadSegments()) {
    const road = segment.points || [];
    if (road.length < 2) continue;
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

  const clumps = state.project.retention?.clumps || [];
  for (const clump of clumps) {
    const polygon = clump.polygon || [];
    if (polygon.length < 3) continue;
    ctx.beginPath();
    polygon.forEach((point, index) => {
      const [sx, sy] = worldToScreen(Number(point[0]), Number(point[1]));
      if (index === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
    });
    ctx.closePath();
    ctx.fillStyle = clump.kind === "riparian" ? "rgba(74,159,216,0.16)" : "rgba(47,191,176,0.14)";
    ctx.fill();
    ctx.strokeStyle = clump.kind === "riparian" ? "#4a9fd8" : "#2fbfb0";
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  if (state.clumpDraft.length) {
    ctx.beginPath();
    state.clumpDraft.forEach((point, index) => {
      const [sx, sy] = worldToScreen(Number(point[0]), Number(point[1]));
      if (index === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
    });
    ctx.strokeStyle = "#8ff0e5";
    ctx.setLineDash([5, 4]);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  if (state.streamDraft.length) {
    ctx.beginPath();
    state.streamDraft.forEach((point, index) => {
      const [sx, sy] = worldToScreen(Number(point[0]), Number(point[1]));
      if (index === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
    });
    ctx.strokeStyle = "#68b6ff";
    ctx.lineWidth = Math.max(2, Number($("#stream-width")?.value || 30) * state.scale * 0.35);
    ctx.lineCap = "round";
    ctx.globalAlpha = 0.55;
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = "#b9e1ff";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 4]);
    ctx.stroke();
    ctx.setLineDash([]);
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

  const landings = projectLandings();
  for (const [landingIndex, landing] of landings.entries()) {
    const [sx, sy] = worldToScreen(Number(landing.x), Number(landing.y));
    const landingRadius = Math.max(7, 18 * Math.min(state.scale, 2.5));
    ctx.beginPath();
    ctx.arc(sx, sy, landingRadius, 0, Math.PI * 2);
    ctx.fillStyle = landingIndex === 0 ? "rgba(240,138,36,0.35)" : "rgba(240,138,36,0.2)";
    ctx.fill();
    ctx.strokeStyle = COLORS.landing;
    ctx.lineWidth = landingIndex === 0 ? 2 : 1.2;
    ctx.stroke();
    ctx.fillStyle = "#f3c795";
    ctx.font = "11px system-ui";
    ctx.fillText(landingIndex === 0 ? "landing" : landing.label || landing.id, sx + landingRadius + 4, sy + 4);
  }

  if (state.project.machines && landings.length) {
    let index = 0;
    for (const machine of state.project.machines) {
      if (!["feller", "loader", "processor", "skidder", "yarder"].some((role) => machine.role.includes(role))) continue;
      const [sx, sy] = worldToScreen(Number(landings[0].x) + (index - 1) * 2.8, Number(landings[0].y));
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
  renderMachineSpecs();
  renderTruckSpecs();
  renderRoadWarning();
  renderProjectMeta();
  $("#notes").value = state.project?.notes || "";
  $("#retention-target").value = Math.round((Number(state.project?.retention?.target_fraction_basal_area) || 0) * 100);
}

function recomputeStats() {
  if (!state.project) return;
  const polygon = state.project.block.polygon;
  const retained = new Set(state.project.retention?.tree_ids || []);
  const clumps = state.project.retention?.clumps || [];
  let insideCount = 0;
  let retainedCount = 0;
  let totalBa = 0;
  let retainedBa = 0;
  for (const tree of state.trees) {
    tree.inside = pointInPolygon(tree.x, tree.y, polygon);
    tree.retained = retained.has(tree.tree_id) || clumps.some((clump) => pointInPolygon(tree.x, tree.y, clump.polygon || []));
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
    clump_count: clumps.length,
    clump_area_ha: clumps.reduce((sum, clump) => sum + polygonAreaHa(clump.polygon || []), 0),
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
    [(stats.clump_count || 0).toLocaleString(), "clumps"],
  ];
  $("#stand-stats").innerHTML = items.map(([value, label]) => `<div class="stat"><b>${value}</b><span>${label}</span></div>`).join("");
  $("#boundary-info").innerHTML = `${state.project.block.polygon.length} vertices · ${stats.block_area_ha.toFixed(2)} ha<br><span class="muted">Drag vertices; double-click an edge to add one; Delete removes the selected vertex.</span>`;
}

function renderLandingList() {
  const node = $("#landing-list");
  if (!node || !state.project) return;
  const landings = projectLandings();
  state.project.landings = landings;
  node.innerHTML = "";
  landings.forEach((landing, index) => {
    const row = document.createElement("div");
    row.className = "landing-row";
    const label = document.createElement("input");
    label.value = landing.label || landing.id || `Landing ${index + 1}`;
    label.title = "Landing label";
    const x = document.createElement("input");
    x.type = "number";
    x.step = "0.1";
    x.value = Number(landing.x).toFixed(1);
    x.title = "Easting (m)";
    const y = document.createElement("input");
    y.type = "number";
    y.step = "0.1";
    y.value = Number(landing.y).toFixed(1);
    y.title = "Northing (m)";
    const trucks = document.createElement("input");
    trucks.type = "number";
    trucks.min = "0";
    trucks.step = "1";
    trucks.placeholder = "trucks";
    trucks.value = state.project.landing_trucks?.[landing.id] ?? "";
    trucks.title = "Dedicated truck count; blank uses the shared fleet";
    const actions = document.createElement("div");
    const primary = document.createElement("button");
    primary.className = "btn small";
    primary.textContent = index === 0 ? "primary" : "set";
    primary.title = index === 0 ? "Primary landing" : "Make this the primary landing";
    primary.disabled = index === 0;
    primary.addEventListener("click", () => {
      pushHistory();
      const [chosen] = landings.splice(index, 1);
      landings.unshift(chosen);
      state.project.landings = landings;
      state.project.landing = { x: Number(chosen.x), y: Number(chosen.y) };
      markDirty();
      render();
      renderLandingList();
    });
    const remove = document.createElement("button");
    remove.className = "btn small";
    remove.textContent = "×";
    remove.title = "Remove landing";
    remove.disabled = landings.length < 2;
    remove.addEventListener("click", () => {
      if (landings.length < 2) return;
      pushHistory();
      landings.splice(index, 1);
      state.project.landings = landings;
      state.project.landing = { x: Number(landings[0].x), y: Number(landings[0].y) };
      markDirty();
      render();
      renderLandingList();
    });
    actions.append(primary, remove);
    const update = () => {
      pushHistory();
      landing.label = label.value.trim() || `Landing ${index + 1}`;
      landing.x = Number(x.value);
      landing.y = Number(y.value);
      state.project.landings = landings;
      if (index === 0) state.project.landing = { x: landing.x, y: landing.y };
      markDirty();
      render();
    };
    label.addEventListener("change", update);
    x.addEventListener("change", update);
    y.addEventListener("change", update);
    trucks.addEventListener("change", () => {
      pushHistory();
      const counts = state.project.landing_trucks || {};
      if (trucks.value === "") delete counts[landing.id];
      else counts[landing.id] = Math.max(0, Number(trucks.value));
      state.project.landing_trucks = Object.keys(counts).length ? counts : undefined;
      if (!state.project.landing_trucks) delete state.project.landing_trucks;
      markDirty();
    });
    row.append(label, x, y, trucks, actions);
    node.append(row);
  });
}

function renderRoadWarning() {
  const node = $("#road-warning");
  if (!node) return;
  const warnings = state.dataset?.road_validation?.warnings || [];
  node.hidden = !warnings.length;
  node.innerHTML = warnings.length
    ? `<b>Road check</b><ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>`
    : "";
}

function renderTruckSpecs() {
  const node = $("#truck-spec-list");
  if (!node || !state.project) return;
  node.innerHTML = "";
  const specs = state.project.landing_truck_specs || {};
  const fields = [
    ["capacity_m3", "payload (m³)"],
    ["cycle_time_s", "cycle (s)"],
    ["load_time_s", "load time (s)"],
  ];
  for (const landing of projectLandings()) {
    const group = document.createElement("div");
    group.className = "spec-group";
    group.innerHTML = `<div class="spec-title">${escapeHtml(landing.label || landing.id)} · truck spec</div>`;
    for (const [key, label] of fields) {
      const row = document.createElement("div");
      row.className = "spec-field";
      const text = document.createElement("label");
      text.textContent = label;
      const input = document.createElement("input");
      input.type = "number";
      input.step = "any";
      input.placeholder = "global";
      input.value = specs[landing.id]?.[key] ?? "";
      input.addEventListener("change", () => {
        pushHistory();
        const next = state.project.landing_truck_specs || {};
        const current = next[landing.id] || {};
        if (input.value === "") delete current[key];
        else current[key] = Number(input.value);
        if (Object.keys(current).length) next[landing.id] = current;
        else delete next[landing.id];
        state.project.landing_truck_specs = Object.keys(next).length ? next : undefined;
        if (!state.project.landing_truck_specs) delete state.project.landing_truck_specs;
        markDirty();
      });
      row.append(text, input);
      group.append(row);
    }
    node.append(group);
  }
}

function addLanding() {
  if (!state.project) return;
  pushHistory();
  const polygon = state.project.block?.polygon || [];
  const xs = polygon.map((point) => Number(point[0]));
  const ys = polygon.map((point) => Number(point[1]));
  const landings = projectLandings();
  const x = (xs.length ? Math.max(...xs) : 0) - 30 - landings.length * 12;
  const y = (ys.length ? Math.min(...ys) : 0) - 20 - landings.length * 10;
  landings.push({
    id: `landing-${Date.now().toString(36)}`,
    label: `Landing ${landings.length + 1}`,
    x,
    y,
  });
  state.project.landings = landings;
  markDirty();
  render();
  renderLandingList();
}

function renderProjectMeta() {
  if (!state.project) {
    $("#project-meta").textContent = "Open or create a project.";
    return;
  }
  const base = state.cases.find((item) => item.case_id === state.project.base_case_id);
  $("#project-meta").innerHTML = `<b>${escapeHtml(state.project.label)}</b><br><span class="muted">${escapeHtml(base?.label || state.project.base_case_id)} · revision ${state.project.revision || 1}${state.dirty ? " · unsaved" : ""}</span>`;
  const edit3d = $("#edit-3d");
  if (edit3d) edit3d.href = `3d?project=${encodeURIComponent(state.project.project_id)}`;
  const exportLink = $("#export");
  if (exportLink) exportLink.href = `${API}projects/${encodeURIComponent(state.project.project_id)}/project.json`;
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
  const landings = projectLandings();
  for (const machine of state.project.machines) {
    const row = document.createElement("div");
    row.className = "machine";
    const fleetRole = ["loader", "roadside_processor", "processor"].includes(machine.role);
    const landingSelect = fleetRole
      ? `<select data-landing="${escapeHtml(machine.id)}">${landings.map((landing) => `<option value="${escapeHtml(landing.id)}" ${landing.id === (machine.landing_id || landings[0]?.id) ? "selected" : ""}>${escapeHtml(landing.label || landing.id)}</option>`).join("")}</select>`
      : "";
    row.innerHTML = `<div><div class="id">${escapeHtml(machine.id)}</div><div class="role">${escapeHtml(machine.role)}</div></div>
      ${landingSelect}
      <select data-machine="${escapeHtml(machine.id)}">${policyOptions(machine.policy || "steady")}</select>
      <button title="Remove machine" data-remove="${escapeHtml(machine.id)}">×</button>`;
    list.append(row);
  }
  for (const select of list.querySelectorAll("select[data-landing]")) {
    select.addEventListener("change", () => {
      pushHistory();
      const machine = state.project.machines.find((item) => item.id === select.dataset.landing);
      machine.landing_id = select.value;
      markDirty();
    });
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

const SPEC_FIELDS = {
  loader: [
    ["process_fixed_s", "fixed process time (s)"],
    ["process_per_log_s", "process time per log (s)"],
  ],
  roadside_processor: [
    ["seconds_per_m3", "seconds per m³"],
    ["fixed_s", "fixed setup (s)"],
    ["per_log_s", "per log (s)"],
  ],
  processor: [
    ["seconds_per_m3", "seconds per m³"],
    ["fixed_s", "fixed setup (s)"],
    ["per_log_s", "per log (s)"],
  ],
  grapple_skidder: [
    ["capacity_m3", "payload (m³)"],
    ["empty_speed_mps", "empty speed (m/s)"],
    ["loaded_speed_mps", "loaded speed (m/s)"],
    ["load_fixed_s", "load fixed (s)"],
    ["load_per_log_s", "load per log (s)"],
    ["unload_fixed_s", "unload fixed (s)"],
    ["unload_per_log_s", "unload per log (s)"],
  ],
  skidder: [
    ["capacity_m3", "payload (m³)"],
    ["empty_speed_mps", "empty speed (m/s)"],
    ["loaded_speed_mps", "loaded speed (m/s)"],
    ["load_fixed_s", "load fixed (s)"],
    ["load_per_log_s", "load per log (s)"],
    ["unload_fixed_s", "unload fixed (s)"],
    ["unload_per_log_s", "unload per log (s)"],
  ],
};

function renderMachineSpecs() {
  const node = $("#spec-list");
  if (!node || !state.project) return;
  node.innerHTML = "";
  for (const machine of state.project.machines) {
    const fields = SPEC_FIELDS[machine.role];
    if (!fields) continue;
    const group = document.createElement("div");
    group.className = "spec-group";
    group.innerHTML = `<div class="spec-title">${escapeHtml(machine.id)} · ${escapeHtml(machine.role)}</div>`;
    const spec = machine.spec || {};
    for (const [key, label] of fields) {
      const row = document.createElement("div");
      row.className = "spec-field";
      const text = document.createElement("label");
      text.textContent = label;
      const input = document.createElement("input");
      input.type = "number";
      input.step = "any";
      input.placeholder = "default";
      input.value = spec[key] ?? "";
      input.addEventListener("change", () => {
        pushHistory();
        const next = machine.spec || {};
        if (input.value === "") delete next[key];
        else next[key] = Number(input.value);
        if (Object.keys(next).length) machine.spec = next;
        else delete machine.spec;
        markDirty();
      });
      row.append(text, input);
      group.append(row);
    }
    node.append(group);
  }
  if (!node.children.length) node.textContent = "No editable fleet machines.";
}

function addMachine() {
  const id = $("#machine-catalog").value;
  if (!id || !state.project) return;
  const catalog = state.project.catalog || [];
  const source = catalog.find((machine) => machine.id === id);
  if (!source) return;
  pushHistory();
  state.project.machines.push({
    id: source.id,
    role: source.role,
    type: source.role,
    policy: "steady",
    source: "added",
    landing_id: ["loader", "roadside_processor", "processor"].includes(source.role)
      ? projectLandings()[0]?.id || "landing-main"
      : null,
  });
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
  if (tool !== "clump") state.clumpDraft = [];
  if (tool !== "stream") state.streamDraft = [];
  state.tool = tool;
  state.selectedVertex = null;
  document.querySelectorAll("#tools [data-tool]").forEach((button) => button.classList.toggle("active", button.dataset.tool === tool));
  const hints = {
    select: "Inspect trees. Drag empty space to pan.",
    landing: "Click to move the primary landing; use the Landings panel to add or promote others.",
    boundary: "Drag boundary vertices; double-click an edge to insert; Delete removes selected vertex.",
    retain: "Paint retention trees. Hold Shift to clear retention.",
    clump: "Click to draw a retention clump. Double-click to close it. Trees inside are retained.",
    stream: "Click along the stream centreline. Double-click to generate a riparian buffer clump.",
    road: "Click to append road points; Shift-click starts a new road branch.",
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
    let best = null;
    let bestDistance = 45;
    for (const segment of roadSegments()) {
      const road = segment.points || [];
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
    }
    if (best) next = best;
    state.project.landing = { x: next[0], y: next[1] };
    const landings = projectLandings();
    if (landings.length) {
      landings[0].x = next[0];
      landings[0].y = next[1];
      state.project.landings = landings;
    }
    markDirty();
    render();
    renderLandingList();
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
  if (state.tool === "clump") {
    state.clumpDraft.push([world[0], world[1]]);
    render();
    return;
  }
  if (state.tool === "stream") {
    state.streamDraft.push([world[0], world[1]]);
    render();
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
    const segments = ensureRoadSegments(state.project);
    if (event.shiftKey || !segments.length) {
      segments.push({
        id: `road-${Date.now().toString(36)}`,
        label: `Road ${segments.length + 1}`,
        points: [],
      });
    }
    const segment = segments[segments.length - 1];
    segment.points.push([world[0], world[1]]);
    state.project.road.points = segments[0].points;
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

async function finishStream() {
  if (!state.project || state.streamDraft.length < 2) return;
  const width = Math.max(1, Number($("#stream-width")?.value || 30));
  const centerline = state.streamDraft.slice();
  try {
    const result = await api("geometry/stream-buffer", {
      method: "POST",
      body: JSON.stringify({ points: centerline, width_m: width }),
    });
    pushHistory();
    state.project.retention.clumps = state.project.retention.clumps || [];
    state.project.retention.clumps.push({
      id: `stream-${Date.now().toString(36)}`,
      label: `stream riparian buffer (${width} m)`,
      kind: "riparian",
      source: "stream",
      buffer_m: width,
      centerline,
      polygon: result.polygon,
    });
    state.streamDraft = [];
    recomputeStats();
    markDirty();
    render();
    setStatus(`Added ${width} m stream riparian buffer`);
  } catch (error) {
    setStatus(`Stream buffer failed: ${error.message}`, true);
  }
}

async function onDoubleClick(event) {
  if (state.tool === "stream" && state.project && state.streamDraft.length >= 2) {
    await finishStream();
    return;
  }
  if (state.tool === "clump" && state.project && state.clumpDraft.length >= 3) {
    pushHistory();
    state.project.retention.clumps = state.project.retention.clumps || [];
    const kind = $("#clump-kind")?.value || "retention";
    state.project.retention.clumps.push({
      id: `clump-${Date.now().toString(36)}`,
      label: kind === "riparian" ? "riparian buffer" : kind === "corridor" ? "no-harvest corridor" : "retention clump",
      kind,
      polygon: state.clumpDraft.slice(),
    });
    state.clumpDraft = [];
    recomputeStats();
    markDirty();
    render();
    return;
  }
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
    api(`projects/${encodeURIComponent(saved.project_id)}/dataset`)
      .then((dataset) => {
        state.dataset.road_validation = dataset.road_validation;
        renderRoadWarning();
      })
      .catch(() => { /* non-critical */ });
  }).catch((error) => setStatus(`Save failed: ${error.message}`, true));
}

function renameProject() {
  if (!state.project) return;
  const next = prompt("Project name", state.project.label || "");
  if (next === null || !next.trim()) return;
  pushHistory();
  state.project.label = next.trim();
  markDirty();
  renderProjectMeta();
}

async function duplicateProject() {
  if (!state.project) return;
  try {
    const copied = await api(`projects/${encodeURIComponent(state.project.project_id)}/duplicate`, { method: "POST" });
    await refreshProjectSelect();
    await loadProject(copied.project_id);
  } catch (error) { setStatus(`Duplicate failed: ${error.message}`, true); }
}

function formatDuration(seconds) {
  if (seconds == null || !Number.isFinite(Number(seconds))) return "—";
  return `${(Number(seconds) / 3600).toFixed(1)} h`;
}

function formatValue(value, digits = 1) {
  return value == null || !Number.isFinite(Number(value)) ? "—" : Number(value).toFixed(digits);
}

function renderRunComparison(runs) {
  const node = $("#run-compare");
  if (!runs || runs.length < 2) {
    node.textContent = "Need two runs to compare.";
    return;
  }
  const latest = runs[0];
  const previous = runs[1];
  const lk = latest.kpis || {};
  const pk = previous.kpis || {};
  const rows = [
    ["volume m³", Number(pk.processed_volume_m3), Number(lk.processed_volume_m3), "higher"],
    ["makespan", Number(pk.makespan_s) / 3600, Number(lk.makespan_s) / 3600, "lower"],
    ["trees", Number(pk.tree_count), Number(lk.tree_count), "higher"],
    ["warnings", (previous.warnings || []).length, (latest.warnings || []).length, "lower"],
  ];
  let html = `<b>${escapeHtml(latest.run_id)}</b> vs ${escapeHtml(previous.run_id)}<div class="compare-grid" style="margin-top:6px">`;
  for (const [label, before, after, direction] of rows) {
    if (!Number.isFinite(before) || !Number.isFinite(after)) continue;
    const delta = after - before;
    const good = direction === "higher" ? delta >= 0 : delta <= 0;
    html += `<span>${label}</span><span class="${good ? "delta-ok" : "delta-bad"}">${delta >= 0 ? "+" : ""}${label === "makespan" ? delta.toFixed(1) : delta.toFixed(0)}</span>`;
  }
  html += "</div>";
  node.innerHTML = html;
}

async function loadRunHistory() {
  if (!state.project) return;
  try {
    const payload = await api(`projects/${encodeURIComponent(state.project.project_id)}/runs`);
    const runs = payload.runs || [];
    const node = $("#run-history");
    if (!runs.length) { node.textContent = "No runs yet."; renderRunComparison([]); return; }
    renderRunComparison(runs);
    node.innerHTML = "";
    for (const run of runs.slice(0, 8)) {
      const row = document.createElement("div");
      row.className = "run-row";
      const link = document.createElement("a");
      link.href = `replay?project=${encodeURIComponent(state.project.project_id)}&run=${encodeURIComponent(run.run_id)}`;
      link.target = "_blank";
      link.textContent = `${run.run_id} · ${run.status || "unknown"}`;
      link.style.color = "var(--accent)";
      link.style.fontSize = "11px";
      const stale = run.freshness?.stale;
      let staleBadge = null;
      if (stale) {
        staleBadge = document.createElement("span");
        staleBadge.className = "stale-badge";
        staleBadge.textContent = "stale";
        staleBadge.title = (run.freshness?.reasons || ["Project edits changed after this run."]).join(" ");
      }
      const rerun = document.createElement("button");
      rerun.className = "btn small";
      rerun.textContent = "Rerun";
      rerun.title = "Run the current project edits and create a fresh run";
      rerun.hidden = !stale;
      rerun.addEventListener("click", async () => {
        rerun.disabled = true;
        rerun.textContent = "Running…";
        try {
          const record = await api(`projects/${encodeURIComponent(state.project.project_id)}/run`, { method: "POST" });
          setStatus(`Fresh run complete · ${record.run_id}`);
          await loadRunHistory();
        } catch (error) {
          setStatus(`Rerun failed: ${error.message}`, true);
          rerun.disabled = false;
          rerun.textContent = "Rerun";
        }
      });
      const promote = document.createElement("button");
      promote.className = "btn small";
      promote.textContent = "Tree Lab";
      promote.title = "Copy this run into the Tree Lab case run list";
      promote.addEventListener("click", async () => {
        try {
          const result = await api(`projects/${encodeURIComponent(state.project.project_id)}/runs/${encodeURIComponent(run.run_id)}/promote`, { method: "POST" });
          setStatus(`Promoted to Tree Lab · ${result.path}`);
          promote.textContent = "Promoted";
          promote.disabled = true;
        } catch (error) { setStatus(`Promote failed: ${error.message}`, true); }
      });
      row.append(link);
      if (staleBadge) row.append(staleBadge);
      row.append(rerun, promote);
      node.append(row);
    }
  } catch (_error) { /* history is non-critical */ }
}

function importProjectFile(file) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async () => {
    try {
      const payload = JSON.parse(String(reader.result));
      const project = await api("projects/import", { method: "POST", body: JSON.stringify(payload) });
      await refreshProjectSelect();
      await loadProject(project.project_id);
    } catch (error) { setStatus(`Import failed: ${error.message}`, true); }
  };
  reader.readAsText(file);
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
    renderLandingList();
    resizeCanvas();
    fitView();
    setStatus(`Loaded ${state.project.label}`);
    history.replaceState(null, "", `?project=${encodeURIComponent(projectId)}`);
    await loadRunHistory();
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
    const warnings = Array.isArray(record.warnings) ? record.warnings : [];
    const warningHtml = warnings.length
      ? `<div class="banner warn"><b>Blocked / warnings</b><ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></div>`
      : "";
    $("#run-result").innerHTML = `<b>Run ${escapeHtml(record.run_id)}</b><div class="stat-grid" style="margin-top:7px">${rows.map(([label, value]) => `<div class="stat"><b>${value}</b><span>${label}</span></div>`).join("")}</div>${warningHtml}<p><a class="back" href="replay?project=${encodeURIComponent(state.project.project_id)}&run=${encodeURIComponent(record.run_id)}" target="_blank">Open 3D replay →</a></p>`;
    setStatus(`Run complete · ${record.run_id}`);
    renderProjectMeta();
    await loadRunHistory();
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
  $("#stream-width").addEventListener("input", () => {
    $("#stream-width-output").textContent = `${Number($("#stream-width").value)} m`;
    render();
  });
  $("#undo").addEventListener("click", undo);
  $("#redo").addEventListener("click", redo);
  $("#save").addEventListener("click", saveProject);
  $("#run").addEventListener("click", runScenario);
  $("#rename").addEventListener("click", renameProject);
  $("#duplicate").addEventListener("click", duplicateProject);
  $("#add-machine").addEventListener("click", addMachine);
  $("#add-landing").addEventListener("click", addLanding);
  $("#new-project").addEventListener("click", openNewDialog);
  $("#import").addEventListener("click", () => $("#import-file").click());
  $("#import-file").addEventListener("change", (event) => { importProjectFile(event.target.files?.[0]); event.target.value = ""; });
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
