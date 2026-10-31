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
let events = null;
let duration = 1;

const viewer = createViewer(scene, {
  onTime: (t) => {
    if (!events) return;
    const processed = (events.trees || []).filter((tree) => (tree.processed_s ?? Infinity) <= t).length;
    const volume = (events.trees || []).filter((tree) => (tree.processed_s ?? Infinity) <= t).reduce((sum, tree) => sum + (Number(tree.volume_m3) || 0), 0);
    status.textContent = `T+${fmt(t)} · ${processed.toLocaleString()} / ${(events.trees || []).length.toLocaleString()} trees · ${volume.toFixed(0)} m³`;
    scrub.value = Math.round((t / duration) * 1000);
    const states = viewer.machineStates();
    for (const [id, state] of Object.entries(states)) {
      const node = document.querySelector(`[data-machine="${id}"] span`);
      if (node) node.textContent = state;
    }
  },
});

function fmt(t) {
  const s = Math.max(0, Math.floor(t));
  return `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`;
}

async function load() {
  if (!projectId || !runId) throw new Error("Missing project or run id.");
  download.href = `${API}projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/events`;
  download.hidden = false;
  document.getElementById("run-label").textContent = `${projectId} · ${runId}`;
  events = await fetch(`${API}projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/events`).then((response) => {
    if (!response.ok) throw new Error(`events ${response.status}`);
    return response.json();
  });
  duration = Math.max(1, Number(events.duration_s) || 1);
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
    residual: null,
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
window.addEventListener("resize", () => viewer.resize());
load().catch((error) => { status.textContent = `failed: ${error.message}`; });
