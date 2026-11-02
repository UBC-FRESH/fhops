import { createViewer } from "../lab/viewer.js";

const API = new URL("api/", location.href).pathname;
const params = new URLSearchParams(location.search);
const projectId = params.get("project") || "";
const runId = params.get("run") || "";
const scene = document.getElementById("scene");
const status = document.getElementById("status");
const machines = document.getElementById("machines");
const play = document.getElementById("play");
const scrub = document.getElementById("scrub");
const clock = document.getElementById("title");
const download = document.getElementById("download");
const timelinePanel = document.getElementById("timeline-panel");
const timelineCanvas = document.getElementById("timeline-canvas");
const timelineToggle = document.getElementById("timeline-toggle");
const timelineCursor = document.getElementById("timeline-cursor");
const staleBanner = document.getElementById("stale-banner");
const staleText = document.getElementById("stale-text");
const rerunButton = document.getElementById("rerun");
let events = null;
let duration = 1;
let currentTime = 0;
let hoverTime = null;
let seekingTimeline = false;
let timelineLanes = [];

const TIMELINE_COLORS = {
  process: "#f08a24",
  travel: "#68b6ff",
  load: "#69d18c",
  unload: "#69d18c",
  truck_load: "#d6b45a",
  truck_return: "#a58b5a",
  repair: "#ff6b6b",
  wait: "#52656b",
};

const viewer = createViewer(scene, {
  onTime: (t) => {
    if (!events) return;
    currentTime = t;
    const processed = (events.trees || []).filter((tree) => (tree.processed_s ?? Infinity) <= t).length;
    const volume = (events.trees || []).filter((tree) => (tree.processed_s ?? Infinity) <= t).reduce((sum, tree) => sum + (Number(tree.volume_m3) || 0), 0);
    status.textContent = `T+${fmt(t)} · ${processed.toLocaleString()} / ${(events.trees || []).length.toLocaleString()} trees · ${volume.toFixed(0)} m³`;
    scrub.value = Math.round((t / duration) * 1000);
    const states = viewer.machineStates();
    for (const [id, state] of Object.entries(states)) {
      const node = document.querySelector(`[data-machine="${id}"] span`);
      if (node) node.textContent = state;
    }
    if (!timelinePanel.hidden) drawTimeline();
  },
});

function fmt(t) {
  const s = Math.max(0, Math.floor(t));
  return `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`;
}

function buildTimeline() {
  const machineIds = new Set(Object.keys(events?.machines || {}));
  for (const item of events?.timeline || []) machineIds.add(item.machine);
  timelineLanes = [...machineIds].sort().map((id) => ({
    id,
    type: events?.machines?.[id]?.type || "machine",
  }));
  drawTimeline();
}

function timelineGeometry() {
  const rect = timelineCanvas.getBoundingClientRect();
  return {
    rect,
    left: 106,
    right: 12,
    top: 17,
    bottom: 20,
    width: Math.max(1, rect.width),
    height: Math.max(1, rect.height),
  };
}

function timelineTimeAt(clientX) {
  const { rect, left, right, width } = timelineGeometry();
  const plotWidth = Math.max(1, width - left - right);
  const x = Math.max(0, Math.min(plotWidth, clientX - rect.left - left));
  return (x / plotWidth) * duration;
}

function seekTimeline(clientX) {
  viewer.seek(Math.max(0, Math.min(duration, timelineTimeAt(clientX))));
}

function drawTimeline() {
  if (!events || timelinePanel.hidden) return;
  const { rect, left, right, top, bottom, width, height } = timelineGeometry();
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const pixelWidth = Math.max(1, Math.round(width * dpr));
  const pixelHeight = Math.max(1, Math.round(height * dpr));
  if (timelineCanvas.width !== pixelWidth || timelineCanvas.height !== pixelHeight) {
    timelineCanvas.width = pixelWidth;
    timelineCanvas.height = pixelHeight;
  }
  const ctx = timelineCanvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const plotWidth = Math.max(1, width - left - right);
  const plotHeight = Math.max(1, height - top - bottom);
  const laneHeight = Math.max(13, plotHeight / Math.max(1, timelineLanes.length));

  ctx.fillStyle = "#0c1113";
  ctx.fillRect(left, top, plotWidth, plotHeight);
  ctx.font = "10px system-ui, sans-serif";
  ctx.textBaseline = "middle";
  for (let tick = 0; tick <= 5; tick += 1) {
    const x = left + (plotWidth * tick) / 5;
    ctx.strokeStyle = "#263237";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, top + plotHeight);
    ctx.stroke();
    ctx.fillStyle = "#93a6ae";
    ctx.textAlign = tick === 0 ? "left" : tick === 5 ? "right" : "center";
    ctx.fillText(fmt((duration * tick) / 5), x, height - 8);
  }

  timelineLanes.forEach((lane, index) => {
    const y = top + index * laneHeight;
    if (index % 2 === 0) {
      ctx.fillStyle = "#11181b";
      ctx.fillRect(left, y, plotWidth, laneHeight);
    }
    const short = lane.id.length > 15 ? `${lane.id.slice(0, 14)}…` : lane.id;
    ctx.fillStyle = "#d7e3e7";
    ctx.textAlign = "right";
    ctx.fillText(short, left - 7, y + laneHeight / 2);
    ctx.fillStyle = "#7f9299";
    ctx.textAlign = "left";
    ctx.font = "8px system-ui, sans-serif";
    ctx.fillText(lane.type.replaceAll("_", " "), 4, y + laneHeight / 2);
    ctx.font = "10px system-ui, sans-serif";
  });

  ctx.save();
  ctx.beginPath();
  ctx.rect(left, top, plotWidth, plotHeight);
  ctx.clip();
  for (const item of events.timeline || []) {
    const index = timelineLanes.findIndex((lane) => lane.id === item.machine);
    if (index < 0) continue;
    const y = top + index * laneHeight + 2;
    const start = Math.max(0, Number(item.start_s) || 0);
    const end = Math.max(start + 0.001, Number(item.end_s) || start + 0.001);
    const x0 = left + (start / duration) * plotWidth;
    const x1 = left + (Math.min(duration, end) / duration) * plotWidth;
    ctx.fillStyle = TIMELINE_COLORS[item.type] || "#8fa6ae";
    ctx.fillRect(x0, y, Math.max(1, x1 - x0), Math.max(2, laneHeight - 4));
  }
  ctx.restore();

  const cursor = Math.max(0, Math.min(duration, hoverTime ?? currentTime));
  const cursorX = left + (cursor / duration) * plotWidth;
  ctx.strokeStyle = "#f08a24";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(cursorX, top - 7);
  ctx.lineTo(cursorX, top + plotHeight + 3);
  ctx.stroke();
  ctx.fillStyle = "#f08a24";
  ctx.beginPath();
  ctx.moveTo(cursorX - 5, top - 13);
  ctx.lineTo(cursorX + 5, top - 13);
  ctx.lineTo(cursorX, top - 5);
  ctx.closePath();
  ctx.fill();
  timelineCursor.textContent = `T+${fmt(cursor)}`;
}

function replayRoadSegments(project) {
  const road = project?.road || {};
  const segments = (road.segments || [])
    .filter((segment) => Array.isArray(segment.points) && segment.points.length >= 2)
    .map((segment) => ({
      id: segment.id || "road",
      label: segment.label || "Road",
      points: segment.points,
    }));
  if (segments.length) return segments;
  if (Array.isArray(road.points) && road.points.length >= 2) {
    return [{ id: "road-main", label: "Main road", points: road.points }];
  }
  return [];
}

function replayTerrain(project) {
  const terrain = project?.terrain;
  if (!terrain || !Array.isArray(terrain.heights) || !terrain.heights.length) return null;
  const polygon = project.block?.polygon || [];
  const polygonXs = polygon.map((point) => Number(point[0])).filter(Number.isFinite);
  const polygonYs = polygon.map((point) => Number(point[1])).filter(Number.isFinite);
  const sourceBounds = Array.isArray(terrain.bounds) && terrain.bounds.length === 4
    ? terrain.bounds.map(Number)
    : [
        Math.min(...polygonXs),
        Math.min(...polygonYs),
        Math.max(...polygonXs),
        Math.max(...polygonYs),
      ];
  const [sourceMinX, sourceMinY, sourceMaxX, sourceMaxY] = sourceBounds;
  const sourceRes = Math.max(2, Number(terrain.resolution) || 24);
  const sampleSource = (x, y) => {
    const fx = Math.max(0, Math.min(sourceRes - 1, ((x - sourceMinX) / Math.max(1e-9, sourceMaxX - sourceMinX)) * (sourceRes - 1)));
    const fy = Math.max(0, Math.min(sourceRes - 1, ((y - sourceMinY) / Math.max(1e-9, sourceMaxY - sourceMinY)) * (sourceRes - 1)));
    const x0 = Math.floor(fx), y0 = Math.floor(fy);
    const x1 = Math.min(sourceRes - 1, x0 + 1), y1 = Math.min(sourceRes - 1, y0 + 1);
    const dx = fx - x0, dy = fy - y0;
    const h00 = Number(terrain.heights[y0 * sourceRes + x0]) || 0;
    const h10 = Number(terrain.heights[y0 * sourceRes + x1]) || 0;
    const h01 = Number(terrain.heights[y1 * sourceRes + x0]) || 0;
    const h11 = Number(terrain.heights[y1 * sourceRes + x1]) || 0;
    return (h00 * (1 - dx) + h10 * dx) * (1 - dy) + (h01 * (1 - dx) + h11 * dx) * dy;
  };

  const xs = [...polygonXs];
  const ys = [...polygonYs];
  const landing = project.landing || {};
  if (Number.isFinite(Number(landing.x))) xs.push(Number(landing.x));
  if (Number.isFinite(Number(landing.y))) ys.push(Number(landing.y));
  for (const segment of replayRoadSegments(project)) {
    for (const point of segment.points) {
      if (Number.isFinite(Number(point[0]))) xs.push(Number(point[0]));
      if (Number.isFinite(Number(point[1]))) ys.push(Number(point[1]));
    }
  }
  xs.push(sourceMinX, sourceMaxX);
  ys.push(sourceMinY, sourceMaxY);
  const margin = 60;
  const bounds = [
    Math.min(...xs) - margin,
    Math.min(...ys) - margin,
    Math.max(...xs) + margin,
    Math.max(...ys) + margin,
  ];
  const resolution = Math.max(sourceRes, 40);
  const heights = new Array(resolution * resolution);
  const [minX, minY, maxX, maxY] = bounds;
  for (let row = 0; row < resolution; row += 1) {
    const y = minY + ((row + 0.5) / resolution) * (maxY - minY);
    for (let col = 0; col < resolution; col += 1) {
      const x = minX + ((col + 0.5) / resolution) * (maxX - minX);
      heights[row * resolution + col] = sampleSource(x, y);
    }
  }
  return { bounds, resolution, heights };
}

async function load() {
  if (!projectId || !runId) throw new Error("Missing project or run id.");
  download.href = `${API}projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/events`;
  download.hidden = false;
  document.getElementById("run-label").textContent = `${projectId} · ${runId}`;
  const [loadedEvents, project, dataset, runMetadata] = await Promise.all([
    fetch(`${API}projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/events`).then((response) => {
      if (!response.ok) throw new Error(`events ${response.status}`);
      return response.json();
    }),
    fetch(`${API}projects/${encodeURIComponent(projectId)}`).then((response) => response.json()),
    fetch(`${API}projects/${encodeURIComponent(projectId)}/dataset`).then((response) => response.json()),
    fetch(`${API}projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}`).then((response) => (
      response.ok ? response.json() : null
    )),
  ]);
  events = loadedEvents;
  events.terrain = replayTerrain(project);
  events.road_segments = replayRoadSegments(project);
  const freshness = runMetadata?.freshness;
  if (freshness?.stale) {
    staleText.textContent = ` ${freshness.reasons?.join(" ") || "Project edits changed after this run."}`;
    staleBanner.hidden = false;
  }
  const landingInventory = events.landing_inventory || {};
  const inventoryText = Object.entries(landingInventory)
    .map(([id, info]) => `${id}: ${Number(info.final_m3 || 0).toFixed(1)} / ${Number(info.max_m3 || 0).toFixed(1)} m³`)
    .join(" · ");
  document.getElementById("landing-inventory").textContent = inventoryText
    ? `landing stockpiles (final / peak): ${inventoryText}`
    : "";
  const retainedTrees = (dataset.trees || []).filter((tree) => tree.retained);
  document.getElementById("run-label").textContent += ` · ${retainedTrees.length} retained`;
  if (events.terrain) document.getElementById("run-label").textContent += " · terrain";
  const residual = {
    clumps: project?.retention?.clumps || [],
    trees: retainedTrees
      .map((tree) => ({
        tree_id: tree.tree_id, x: tree.x, y: tree.y, dbh_cm: tree.dbh_cm,
        height_m: tree.height_m, crown_radius_m: Math.max(1, tree.dbh_cm / 30),
      })),
  };
  duration = Math.max(1, Number(events.duration_s) || 1);
  buildTimeline();
  machines.innerHTML = "";
  for (const [id, spec] of Object.entries(events.machines || {})) {
    const card = document.createElement("div");
    card.className = "mcard";
    card.dataset.machine = id;
    card.innerHTML = `<b>${id} · ${spec.type}</b><span>idle</span>`;
    machines.append(card);
  }
  await viewer.load({
    sceneUrl: `${API}projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/scene.gltf`,
    events,
    residual,
  });
  clock.textContent = `${events.block_id || "Edited scenario"} · ${events.tree_count || 0} trees · ${(Number(events.processed_volume_m3) || 0).toFixed(0)} m³`;
  status.textContent = "ready";
}

play.addEventListener("click", () => {
  const playing = viewer.toggle();
  play.textContent = playing ? "pause" : "play";
});
document.getElementById("reset").addEventListener("click", () => viewer.reset());
document.getElementById("fit").addEventListener("click", () => viewer.fit());
scrub.addEventListener("input", () => viewer.seek((Number(scrub.value) / 1000) * duration));
document.getElementById("speed").addEventListener("change", (event) => viewer.setSpeed(Number(event.target.value)));
timelineToggle.addEventListener("click", () => {
  timelinePanel.hidden = !timelinePanel.hidden;
  timelineToggle.classList.toggle("active", !timelinePanel.hidden);
  if (!timelinePanel.hidden) drawTimeline();
});
timelineCanvas.addEventListener("mousemove", (event) => {
  hoverTime = timelineTimeAt(event.clientX);
  if (seekingTimeline) seekTimeline(event.clientX);
  drawTimeline();
});
timelineCanvas.addEventListener("mouseleave", () => {
  hoverTime = null;
  drawTimeline();
});
timelineCanvas.addEventListener("mousedown", (event) => {
  seekingTimeline = true;
  seekTimeline(event.clientX);
  event.preventDefault();
});
window.addEventListener("mouseup", () => { seekingTimeline = false; });
window.addEventListener("resize", () => {
  viewer.resize();
  if (!timelinePanel.hidden) drawTimeline();
});
rerunButton.addEventListener("click", async () => {
  rerunButton.disabled = true;
  rerunButton.textContent = "Running…";
  try {
    const response = await fetch(`${API}projects/${encodeURIComponent(projectId)}/run`, { method: "POST" });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || response.statusText);
    }
    const record = await response.json();
    const next = new URL(location.href);
    next.searchParams.set("run", record.run_id);
    location.href = next.toString();
  } catch (error) {
    staleText.textContent = ` Rerun failed: ${error.message}`;
    rerunButton.disabled = false;
    rerunButton.textContent = "Rerun project";
  }
});
load().catch((error) => { status.textContent = `failed: ${error.message}`; });
