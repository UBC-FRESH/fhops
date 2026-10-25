const state = { runs: [], selected: null };

const statusEl = document.getElementById("status");
const runsEl = document.getElementById("runs");
const emptyEl = document.getElementById("empty");
const filterEl = document.getElementById("domain-filter");
const titleEl = document.getElementById("run-title");
const metaEl = document.getElementById("run-meta");
const filesEl = document.getElementById("run-files");
const warningsEl = document.getElementById("run-warnings");

function badge(domain) {
  const label = domain === "tactical_operational" ? "tactical" : (domain || "unknown");
  return `<span class="badge ${domain || "unknown"}">${label}</span>`;
}

function renderRuns() {
  const domain = filterEl.value;
  const runs = state.runs.filter((run) => !domain || run.domain === domain);
  runsEl.innerHTML = "";
  emptyEl.hidden = runs.length > 0;
  for (const run of runs) {
    const li = document.createElement("li");
    li.className = "run" + (state.selected === run.run_id ? " active" : "");
    li.innerHTML = `<div class="name">${run.run_id}</div>
      <div class="meta">${badge(run.domain)}<span>${run.run_type || "unclassified"}</span>
      <span>·</span><span>${run.status || "unknown"}</span></div>`;
    li.addEventListener("click", () => selectRun(run.run_id));
    runsEl.appendChild(li);
  }
}

function selectRun(runId) {
  state.selected = runId;
  const run = state.runs.find((item) => item.run_id === runId);
  if (!run) return;
  renderRuns();
  titleEl.textContent = run.run_id;
  metaEl.innerHTML = `${badge(run.domain)}<span>${run.run_type || "unclassified"}</span>
    <span>${run.status || "unknown"}</span><span>${run.path}</span>`;
  filesEl.innerHTML = Object.entries(run.files || {}).map(([name, file]) =>
    `<div class="file" title="${file}"><b>${name}</b>${file}</div>`).join("");
  warningsEl.innerHTML = (run.warnings || []).map((warning) => `<div>${warning}</div>`).join("");
}

async function refresh() {
  statusEl.textContent = "loading…";
  try {
    const response = await fetch("api/runs");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.runs = await response.json();
    statusEl.textContent = `${state.runs.length} run(s)`;
    renderRuns();
  } catch (error) {
    statusEl.textContent = "error";
    emptyEl.hidden = false;
    emptyEl.textContent = `Could not load runs: ${error.message}`;
  }
}

filterEl.addEventListener("change", renderRuns);
document.getElementById("refresh").addEventListener("click", refresh);
refresh();
