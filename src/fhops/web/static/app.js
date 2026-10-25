const state = { runs: [], skins: [], skin: null, run: null, panel: null };

const els = {
  skin: document.getElementById("skin"),
  run: document.getElementById("run"),
  domain: document.getElementById("domain"),
  status: document.getElementById("status"),
  refresh: document.getElementById("refresh"),
  tabs: document.getElementById("tabs"),
  skinMeta: document.getElementById("skin-meta"),
  runMeta: document.getElementById("run-meta"),
  empty: document.getElementById("empty"),
  assistant: document.getElementById("assistant"),
  assistantInput: document.getElementById("assistant-input"),
  assistantAsk: document.getElementById("assistant-ask"),
  assistantOutput: document.getElementById("assistant-output"),
  title: document.getElementById("panel-title"),
  body: document.getElementById("panel-body"),
};

const PANEL_LABELS = {
  legend: "Legend",
  map: "Map",
  schedule: "Schedule",
  haul: "Haul",
  tactical: "Tactical",
  kpis: "KPIs",
  reports: "Reports",
  compare: "Compare",
  scenario: "Scenario",
  run: "Run",
};
const DOMAIN_PANELS = {
  operational: "schedule",
  hauling: "haul",
  tactical_operational: "tactical",
};
const DOMAIN_SKINS = {
  operational: "operational-planner",
  hauling: "hauling-planner",
  tactical_operational: "tactical-planner",
};

function api(path) {
  return new URL(path, document.baseURI).toString();
}

async function putJson(path, payload) {
  const response = await fetch(api(path), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch (_error) { /* keep status */ }
    throw new Error(detail);
  }
  return response.json();
}

async function postJson(path, payload) {
  const response = await fetch(api(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch (_error) { /* keep status */ }
    throw new Error(detail);
  }
  if (response.status === 204) return {};
  return response.json();
}

async function fetchJson(path) {
  const response = await fetch(api(path));
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      if (payload.detail) detail = payload.detail;
    } catch (_error) { /* keep the status */ }
    throw new Error(detail);
  }
  return response.json();
}

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function badge(domain) {
  const node = el("span", domain === "tactical_operational" ? "tactical" : (domain || "unknown"));
  node.className = `badge ${domain || "unknown"}`;
  return node;
}

function renderSkins() {
  els.skin.innerHTML = "";
  for (const skin of state.skins) {
    const option = el("option", skin.title);
    option.value = skin.id;
    els.skin.appendChild(option);
  }
  if (state.skin) els.skin.value = state.skin.id;
}

function renderRuns() {
  els.run.innerHTML = "";
  for (const run of state.runs) {
    const option = el("option", `${run.run_id} · ${run.run_type || "unclassified"}`);
    option.value = run.run_id;
    els.run.appendChild(option);
  }
  if (state.run) els.run.value = state.run.run_id;
  els.empty.hidden = state.runs.length > 0;
}

function renderTabs() {
  els.tabs.innerHTML = "";
  if (!state.skin) return;
  for (const panel of state.skin.panels) {
    const button = el("button", PANEL_LABELS[panel] || panel);
    button.type = "button";
    button.className = panel === state.panel ? "active" : "";
    button.addEventListener("click", () => setPanel(panel));
    els.tabs.appendChild(button);
  }
  els.skinMeta.textContent = state.skin.read_only
    ? "Read-only skin. Panels: " + state.skin.panels.join(", ")
    : "Skin: " + state.skin.title + ". Panels: " + state.skin.panels.join(", ");
}

function renderRunMeta() {
  els.runMeta.innerHTML = "";
  if (!state.run) return;
  const run = state.run;
  const line = (label, value) => {
    const b = el("b", label + ": ");
    els.runMeta.appendChild(b);
    els.runMeta.appendChild(document.createTextNode(String(value ?? "—")));
    els.runMeta.appendChild(document.createElement("br"));
  };
  line("domain", run.domain);
  line("type", run.run_type);
  line("status", run.status);
  line("path", run.path);
  if (run.warnings && run.warnings.length) {
    const warning = el("div", run.warnings.join(" "), "warnings");
    els.runMeta.appendChild(warning);
  }
  els.domain.className = `badge ${run.domain || "unknown"}`;
  els.domain.textContent = run.domain === "tactical_operational" ? "tactical" : (run.domain || "unknown");
}

function setPanel(panel) {
  state.panel = panel;
  renderTabs();
  renderPanel().catch((error) => showError(error));
}

function showError(error) {
  els.title.textContent = "Could not load";
  els.body.innerHTML = "";
  els.body.appendChild(el("p", error.message, "warnings"));
}

function destroyMap() {
  if (!state.mapInstance) return;
  try {
    state.mapInstance.remove();
  } catch (_error) { /* already gone */ }
  state.mapInstance = null;
}

function renderPanel() {
  if (!state.run || !state.skin) return Promise.resolve();
  if (state.panel !== "map") destroyMap();
  els.body.innerHTML = "";
  els.title.textContent = PANEL_LABELS[state.panel] || state.panel;
  const run = state.run;
  const encoded = encodeURIComponent(run.run_id);
  switch (state.panel) {
    case "legend":
      return renderLegend(run);
    case "schedule":
      return renderSchedule(encoded);
    case "haul":
      return renderHaul(encoded);
    case "tactical":
      return renderTactical(encoded);
    case "kpis":
      return renderKpis(encoded);
    case "reports":
      return renderReports(encoded);
    case "compare":
      return renderCompare(encoded);
    case "scenario":
      return renderScenario(encoded);
    case "run":
      return renderRunPanel();
    case "map":
      return renderMap(encoded);
    default:
      return renderPlaceholder("Panel", "This panel is not implemented yet.");
  }
}

function renderLegend(run) {
  const files = el("div", null, "files");
  for (const [name, filename] of Object.entries(run.files || {})) {
    const card = el("div", null, "file");
    card.appendChild(el("b", name));
    card.appendChild(document.createTextNode(filename));
    card.title = filename;
    files.appendChild(card);
  }
  if (!Object.keys(run.files || {}).length) {
    els.body.appendChild(el("p", "No known artefacts were discovered.", "hint"));
  } else {
    els.body.appendChild(files);
  }
  return Promise.resolve();
}

function renderChooser(kind, entries) {
  const controls = el("div", null, "controls");
  const label = el("label", "Dataset ");
  const select = document.createElement("select");
  for (const [title, path, view] of entries) {
    const option = el("option", title);
    option.value = path;
    option.dataset.view = view || "table";
    select.appendChild(option);
  }
  label.appendChild(select);
  controls.appendChild(label);
  els.body.appendChild(controls);
  const target = el("div");
  els.body.appendChild(target);
  const load = () => {
    target.innerHTML = "";
    const view = select.selectedOptions[0]?.dataset.view || "table";
    fetchJson(`api/runs/${select.value}`)
      .then((payload) => {
        if (view === "haul-gantt") target.appendChild(renderHaulGantt(payload));
        else if (view === "tactical-gantt") target.appendChild(renderTacticalGantt(payload));
        else if (view === "workload-bars") target.appendChild(renderBars(payload, "day", ["truckloads", "preferred_truckloads"]));
        else if (view === "inventory-bars") target.appendChild(renderBars(payload, "day", ["unsorted_inventory_m3", "water_inventory_m3"]));
        else target.appendChild(renderTable(payload));
      })
      .catch((error) => target.appendChild(el("p", error.message, "warnings")));
  };
  select.addEventListener("change", load);
  load();
  return Promise.resolve();
}

async function renderSchedule(encoded) {
  const [time, payload] = await Promise.all([
    fetchJson(`api/runs/${encoded}/time`),
    fetchJson(`api/runs/${encoded}/assignments?limit=5000`),
  ]);
  els.body.appendChild(renderOperationalGantt(payload, time));
  els.body.appendChild(renderTable(payload));
}

async function renderHaul(encoded) {
  try {
    const summary = await fetchJson(`api/runs/${encoded}/summary`);
    els.body.appendChild(renderProvenance(summary, "Hauling run"));
  } catch (_error) { /* summary is optional */ }
  await renderChooser("haul", [
      ["Flows", `${encoded}/hauling/flows`, "table"],
      ["Truckloads", `${encoded}/hauling/truckloads`, "table"],
      ["Truck / loader schedule", `${encoded}/hauling/schedule`, "haul-gantt"],
      ["Yard inventory", `${encoded}/hauling/yard-inventory`, "inventory-bars"],
      ["Contractor workload", `${encoded}/hauling/contractor-workload`, "workload-bars"],
      ["Trucks", `${encoded}/hauling/trucks`, "table"],
      ["Loaders", `${encoded}/hauling/loaders`, "table"],
    ]);
}

async function renderTactical(encoded) {
  const time = await fetchJson(`api/runs/${encoded}/time`);
  state.tacticalTime = time;
  await renderChooser("tactical", [
      ["Harvest decisions", `${encoded}/tactical/harvest`, "tactical-gantt"],
      ["Production", `${encoded}/tactical/production`, "table"],
      ["Flows", `${encoded}/tactical/flows`, "table"],
      ["Inventory", `${encoded}/tactical/inventory`, "table"],
      ["Purchases", `${encoded}/tactical/purchases`, "table"],
      ["Roads", `${encoded}/tactical/roads`, "table"],
      ["Silviculture", `${encoded}/tactical/silviculture`, "table"],
      ["Fleet", `${encoded}/tactical/fleet`, "table"],
    ]);
}

async function renderKpis(encoded) {
  const payload = await fetchJson(`api/runs/${encoded}/kpis`);
  try {
    const summary = await fetchJson(`api/runs/${encoded}/summary`);
    els.body.appendChild(renderProvenance(summary, "Run summary"));
  } catch (_error) { /* optional */ }
  els.body.appendChild(renderKpiCards(payload));
  els.body.appendChild(renderKeyValues(payload));
}

function renderDataset(path, title) {
  els.body.appendChild(el("p", "Loading " + title + "…", "hint"));
  return fetchJson(path).then((payload) => {
    els.body.innerHTML = "";
    els.body.appendChild(renderTable(payload));
  });
}

function renderTable(payload) {
  const wrap = el("div", null, "table-wrap");
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const column of payload.columns || []) headRow.appendChild(el("th", column));
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  const rows = payload.rows || [];
  for (const row of rows.slice(0, 500)) {
    const tr = document.createElement("tr");
    for (const column of payload.columns || []) {
      const value = row[column];
      const td = el("td", value === null || value === undefined ? "—" : value);
      td.title = value === null || value === undefined ? "" : String(value);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  const note = el(
    "p",
    `${payload.returned ?? rows.length} shown of ${payload.total ?? rows.length} rows` +
      (rows.length > 500 ? " (first 500 rendered)" : ""),
    "hint",
  );
  const container = el("div");
  const head = el("div", null, "table-head");
  head.appendChild(note);
  const exportButton = el("button", "Download CSV", "export-button");
  exportButton.type = "button";
  exportButton.addEventListener("click", () => downloadCsv(payload));
  head.appendChild(exportButton);
  container.appendChild(head);
  container.appendChild(wrap);
  return container;
}

function renderKeyValues(payload) {
  const grid = el("div", null, "kv");
  for (const [key, value] of Object.entries(payload).sort(([a], [b]) => a.localeCompare(b))) {
    if (value !== null && typeof value === "object") continue;
    grid.appendChild(el("b", key));
    grid.appendChild(el("span", value === null ? "—" : value));
  }
  return grid;
}

function downloadCsv(payload) {
  const columns = payload.columns || Object.keys(payload.rows?.[0] || {});
  const escape = (value) => {
    if (value === null || value === undefined) return "";
    const text = String(value);
    return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  const lines = [columns.map(escape).join(",")];
  for (const row of payload.rows || []) {
    lines.push(columns.map((column) => escape(row[column])).join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${payload.run_id || "fhops"}-${payload.artefact || "table"}.csv`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

async function renderReports(encoded) {
  const payload = await fetchJson(`api/runs/${encoded}/reports`);
  const list = el("ul");
  for (const report of payload.reports) {
    const item = document.createElement("li");
    const link = el("a", report.path);
    const safePath = report.path.split("/").map(encodeURIComponent).join("/");
    link.href = api(`api/runs/${encoded}/reports/${safePath}`);
    item.appendChild(link);
    item.appendChild(document.createTextNode(` · ${report.size} bytes`));
    list.appendChild(item);
  }
  els.body.appendChild(el("h3", "Run files"));
  if (payload.reports.length) els.body.appendChild(list);
  else els.body.appendChild(el("p", "No report files were found.", "hint"));

  const builder = el("div", null, "report-builder");
  builder.appendChild(el("h3", "Build a report"));
  const controls = el("div", null, "controls");
  const select = document.createElement("select");
  const entries = reportEntries(encoded);
  for (const [label, path] of entries) {
    const option = el("option", label);
    option.value = path;
    select.appendChild(option);
  }
  const button = el("button", "Build");
  button.type = "button";
  controls.appendChild(select);
  controls.appendChild(button);
  builder.appendChild(controls);
  const target = el("div");
  builder.appendChild(target);
  button.addEventListener("click", () => {
    target.innerHTML = "";
    fetchJson(`api/runs/${select.value}`)
      .then((table) => target.appendChild(renderTable(table)))
      .catch((error) => target.appendChild(el("p", error.message, "warnings")));
  });
  els.body.appendChild(builder);
}

function reportEntries(encoded) {
  const common = {
    operational: [
      ["Assignments", `${encoded}/assignments?limit=5000`],
      ["Day playback", `${encoded}/playback?scope=day`],
      ["Shift playback", `${encoded}/playback?scope=shift`],
    ],
    hauling: [
      ["Flows", `${encoded}/hauling/flows`],
      ["Truckloads", `${encoded}/hauling/truckloads`],
      ["Truck schedule", `${encoded}/hauling/schedule`],
      ["Yard inventory", `${encoded}/hauling/yard-inventory`],
      ["Contractor workload", `${encoded}/hauling/contractor-workload`],
    ],
    tactical_operational: [
      ["Harvest decisions", `${encoded}/tactical/harvest`],
      ["Production", `${encoded}/tactical/production`],
      ["Product flows", `${encoded}/tactical/flows`],
      ["Inventory", `${encoded}/tactical/inventory`],
    ],
  };
  return common[state.run?.domain] || [];
}

function renderPlaceholder(title, text) {
  els.body.innerHTML = "";
  const box = el("div", null, "placeholder");
  box.appendChild(el("h3", title));
  box.appendChild(el("p", text));
  els.body.appendChild(box);
  return Promise.resolve();
}

function chooseSkinForRun(run) {
  if (!run || !state.skin || state.skin.id === "reviewer") return;
  const needed = DOMAIN_PANELS[run.domain];
  if (!needed || state.skin.panels.includes(needed)) return;
  const target = DOMAIN_SKINS[run.domain];
  const skin = state.skins.find((candidate) => candidate.id === target);
  if (skin) {
    state.skin = skin;
    els.skin.value = skin.id;
    renderTabs();
  }
}

function selectRun(runId) {
  state.run = state.runs.find((run) => run.run_id === runId) || null;
  state.runScenarioOverride = null;
  renderRuns();
  renderRunMeta();
  chooseSkinForRun(state.run);
  if (state.run && state.skin && !state.skin.panels.includes(state.panel)) {
    state.panel = DOMAIN_PANELS[state.run.domain] || state.skin.panels[0] || "legend";
  }
  renderTabs();
  renderPanel().catch((error) => showError(error));
}

function selectSkin(skinId) {
  state.skin = state.skins.find((skin) => skin.id === skinId) || state.skins[0] || null;
  if (state.skin) els.skin.value = state.skin.id;
  if (!state.skin || !state.skin.panels.includes(state.panel)) {
    state.panel = (state.run && DOMAIN_PANELS[state.run.domain]) || (state.skin && state.skin.panels[0]) || "legend";
  }
  renderTabs();
  renderPanel().catch((error) => showError(error));
}

function renderAssistant() {
  if (!els.assistant || !els.assistantAsk) return;
  els.assistantAsk.addEventListener("click", async () => {
    const message = els.assistantInput.value.trim();
    if (!message) return;
    els.assistantAsk.disabled = true;
    els.assistantOutput.textContent = "thinking…";
    try {
      const response = await postJson("api/agent", { message });
      els.assistantOutput.textContent = response.response || "(empty response)";
    } catch (error) {
      els.assistantOutput.textContent = error.message;
    } finally {
      els.assistantAsk.disabled = false;
    }
  });
}

async function boot() {
  try {
    const [skins, runs, health] = await Promise.all([
      fetchJson("api/skins"),
      fetchJson("api/runs"),
      fetchJson("api/health"),
    ]);
    state.skins = skins;
    state.runs = runs;
    state.health = health;
    if (els.assistant) els.assistant.hidden = !health.agent_enabled;
    state.skin = skins.find((skin) => skin.id === "operational-planner") || skins[0] || null;
    state.run = runs[0] || null;
    state.panel = (state.run && DOMAIN_PANELS[state.run.domain]) || (state.skin && state.skin.panels[0]) || "legend";
    renderSkins();
    renderRuns();
    renderRunMeta();
    renderTabs();
    if (state.run) chooseSkinForRun(state.run);
    if (!state.skin || !state.skin.panels.includes(state.panel)) {
      state.panel = (state.skin && state.skin.panels[0]) || "legend";
      renderTabs();
    }
    els.status.textContent = `${runs.length} run(s)`;
    await renderPanel();
  } catch (error) {
    els.status.textContent = "error";
    showError(error);
  }
}

els.skin.addEventListener("change", () => selectSkin(els.skin.value));
els.run.addEventListener("change", () => selectRun(els.run.value));
els.refresh.addEventListener("click", boot);
boot();

async function renderMap(encoded) {
  // The panel body is replaced on every skin/run/panel change. Drop the previous MapLibre
  // instance so the new container gets a live map instead of a detached one.
  destroyMap();
  const token = (state.mapRenderToken || 0) + 1;
  state.mapRenderToken = token;
  const [time, layerPayload] = await Promise.all([
    fetchJson(`api/runs/${encoded}/time`),
    fetchJson(`api/runs/${encoded}/layers`),
  ]);
  if (token !== state.mapRenderToken) return;
  state.mapTime = time;
  state.mapLayers = layerPayload.layers;
  state.mapSelected = new Set(
    layerPayload.layers
      .filter((layer) => layer.available && (state.skin.layers || []).includes(layer.name))
      .map((layer) => layer.name),
  );
  if (!state.mapSelected.size) {
    layerPayload.layers.filter((layer) => layer.available).forEach((layer) => state.mapSelected.add(layer.name));
  }
  state.mapStep = time.unit === "period" ? time.values[0] : time.min;
  state.mapShift = (time.shifts && time.shifts[0]) || "";
  state.mapData = null;
  els.body.innerHTML = "";

  const controls = el("div", null, "controls");
  const timeLabel = el("label", time.unit === "period" ? "Period " : "Day ");
  const timeSelect = document.createElement("select");
  for (const value of time.values) {
    const option = el("option", value);
    option.value = value;
    timeSelect.appendChild(option);
  }
  timeSelect.value = state.mapStep;
  timeLabel.appendChild(timeSelect);
  controls.appendChild(timeLabel);

  let shiftSelect = null;
  if (time.shifts && time.shifts.length > 1) {
    const shiftLabel = el("label", "Shift ");
    shiftSelect = document.createElement("select");
    for (const shift of time.shifts) {
      const option = el("option", shift);
      option.value = shift;
      shiftSelect.appendChild(option);
    }
    shiftSelect.value = state.mapShift;
    shiftLabel.appendChild(shiftSelect);
    controls.appendChild(shiftLabel);
  }

  const rendererLabel = el("label", "Renderer ");
  const rendererSelect = document.createElement("select");
  for (const [value, label] of [["maplibre", "MapLibre"], ["svg", "SVG"]]) {
    const option = el("option", label);
    option.value = value;
    rendererSelect.appendChild(option);
  }
  rendererSelect.value = window.maplibregl ? "maplibre" : "svg";
  state.mapRenderer = rendererSelect.value;
  rendererLabel.appendChild(rendererSelect);
  controls.appendChild(rendererLabel);

  const fitButton = el("button", "Fit");
  fitButton.type = "button";
  controls.appendChild(fitButton);
  els.body.appendChild(controls);

  const note = el("p", "", "map-note");
  els.body.appendChild(note);

  const layout = el("div", null, "map-layout");
  const tree = el("div", null, "layer-tree");
  const mapWrap = el("div", null, "map-wrap");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("id", "svg-map");
  const mapDiv = el("div");
  mapDiv.id = "maplibre-map";
  mapDiv.className = state.mapRenderer === "maplibre" ? "" : "hidden";
  svg.setAttribute("class", state.mapRenderer === "svg" ? "" : "hidden");
  const detail = el("div", null, "map-detail");
  detail.hidden = true;
  mapWrap.appendChild(svg);
  mapWrap.appendChild(mapDiv);
  mapWrap.appendChild(detail);
  layout.appendChild(tree);
  layout.appendChild(mapWrap);
  els.body.appendChild(layout);
  els.body.appendChild(renderMapLegend());

  const renderTree = () => {
    tree.innerHTML = "";
    tree.appendChild(el("h3", "Layers"));
    for (const layer of state.mapLayers) {
      const row = el("label", null, "layer-option" + (layer.available ? "" : " disabled"));
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = state.mapSelected.has(layer.name);
      checkbox.disabled = !layer.available;
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) state.mapSelected.add(layer.name);
        else state.mapSelected.delete(layer.name);
        refreshMap();
      });
      const text = el("span");
      text.appendChild(document.createTextNode(layer.label));
      const reason = el("span", layer.available ? layer.legend : layer.reason, "reason");
      text.appendChild(reason);
      row.appendChild(checkbox);
      row.appendChild(text);
      tree.appendChild(row);
    }
  };

  const refreshMap = async () => {
    if (token !== state.mapRenderToken) return;
    renderTree();
    note.textContent = "loading map…";
    const params = new URLSearchParams();
    if (time.unit === "period") params.set("period", state.mapStep);
    else params.set("day", state.mapStep);
    if (state.mapShift) params.set("shift", state.mapShift);
    if (state.mapSelected.size) params.set("layers", Array.from(state.mapSelected).join(","));
    try {
      const data = await fetchJson(`api/runs/${encoded}/map?${params.toString()}`);
      if (token !== state.mapRenderToken) return;
      state.mapData = data;
      note.textContent = `${data.features.length} feature(s)`;
      detail.hidden = true;
      if (state.mapRenderer === "maplibre" && window.maplibregl) {
        await updateMapLibre(data, detail, token);
        if (token !== state.mapRenderToken) return;
        svg.classList.add("hidden");
        mapDiv.classList.remove("hidden");
      } else {
        if (state.mapRenderer === "maplibre" && !window.maplibregl) {
          note.textContent = "MapLibre is unavailable; using the SVG fallback.";
        }
        renderSVG(data, svg, detail);
        mapDiv.classList.add("hidden");
        svg.classList.remove("hidden");
      }
    } catch (error) {
      if (token === state.mapRenderToken) note.textContent = error.message;
    }
  };

  timeSelect.addEventListener("change", () => {
    state.mapStep = timeSelect.value;
    refreshMap();
  });
  if (shiftSelect) {
    shiftSelect.addEventListener("change", () => {
      state.mapShift = shiftSelect.value;
      refreshMap();
    });
  }
  rendererSelect.addEventListener("change", () => {
    state.mapRenderer = rendererSelect.value;
    refreshMap();
  });
  fitButton.addEventListener("click", () => {
    if (state.mapData) {
      if (state.mapRenderer === "maplibre" && state.mapInstance) fitMapLibre(state.mapData);
      else renderSVG(state.mapData, svg, detail);
    }
  });

  await refreshMap();
}

function renderMapLegend() {
  const legend = el("div", null, "map-legend");
  const entries = [
    ["#c0392b", "current / treated"],
    ["#d9a066", "earlier cumulative"],
    ["#2f7d4f", "untreated"],
    ["#1f6feb", "machine / tactical unit"],
  ];
  for (const [color, label] of entries) {
    const item = el("span");
    const swatch = el("span", null, "swatch");
    swatch.style.background = color;
    item.appendChild(swatch);
    item.appendChild(document.createTextNode(label));
    legend.appendChild(item);
  }
  return legend;
}

function renderSVG(data, svg, detail) {
  svg.innerHTML = "";
  svg.setAttribute("viewBox", "0 0 1000 600");
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  const bbox = featureBounds(data);
  if (!bbox) return;
  const [minX, minY, maxX, maxY] = bbox;
  const width = Math.max(maxX - minX, 1e-9);
  const height = Math.max(maxY - minY, 1e-9);
  const scale = Math.min(960 / width, 560 / height);
  const offsetX = 20 - minX * scale;
  const offsetY = 20 - minY * scale;
  const project = ([x, y]) => [x * scale + offsetX, 600 - (y * scale + offsetY)];
  for (const feature of data.features) {
    const geometry = feature.geometry || {};
    const props = feature.properties || {};
    const layer = props.layer;
    if (geometry.type === "Polygon" || geometry.type === "MultiPolygon") {
      const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
      for (const polygon of polygons) {
        for (const ring of polygon) {
          if (!ring.length) continue;
          const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
          const d = ring.map((point, index) => `${index ? "L" : "M"}${project(point).join(",")}`).join(" ") + " Z";
          path.setAttribute("d", d);
          path.setAttribute("fill", layerColor(layer, props));
          path.setAttribute("fill-opacity", layer === "blocks" || layer === "tactical_units" ? ".6" : ".85");
          path.setAttribute("stroke", "#1f2933");
          path.setAttribute("stroke-width", ".6");
          path.addEventListener("click", () => showFeatureDetail(detail, props));
          svg.appendChild(path);
        }
      }
    } else if (geometry.type === "LineString") {
      const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      line.setAttribute("points", geometry.coordinates.map((point) => project(point).join(",")).join(" "));
      line.setAttribute("fill", "none");
      line.setAttribute("stroke", layerColor(layer, props));
      line.setAttribute("stroke-width", "1.2");
      svg.appendChild(line);
    } else if (geometry.type === "Point") {
      const [x, y] = project(geometry.coordinates);
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", x);
      circle.setAttribute("cy", y);
      circle.setAttribute("r", "4.5");
      circle.setAttribute("fill", layerColor(layer, props));
      circle.setAttribute("stroke", "#fff");
      circle.setAttribute("stroke-width", "1");
      circle.addEventListener("click", () => showFeatureDetail(detail, props));
      svg.appendChild(circle);
    }
  }
}

function layerColor(layer, props) {
  if (layer === "machines") return "#1f6feb";
  if (layer === "tactical_units") return props.harvested_area_ha > 0 ? "#1f6feb" : "#2f7d4f";
  if (layer === "treatments") return props.current ? "#c0392b" : (props.cumulative ? "#d9a066" : "#2f7d4f");
  return props.treated ? "#c0392b" : "#2f7d4f";
}

function showFeatureDetail(detail, props) {
  detail.hidden = false;
  detail.textContent = Object.entries(props)
    .map(([key, value]) => `${key}: ${value}`)
    .join("\n");
}

function featureBounds(data) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const visit = (coords) => {
    if (typeof coords[0] === "number") {
      minX = Math.min(minX, coords[0]); maxX = Math.max(maxX, coords[0]);
      minY = Math.min(minY, coords[1]); maxY = Math.max(maxY, coords[1]);
    } else {
      coords.forEach(visit);
    }
  };
  for (const feature of data.features || []) {
    if (feature.geometry && feature.geometry.coordinates) visit(feature.geometry.coordinates);
  }
  if (!isFinite(minX)) return null;
  return [minX, minY, maxX, maxY];
}

async function updateMapLibre(data, detail, token) {
  if (!window.maplibregl || token !== state.mapRenderToken) return;
  if (!state.mapInstance) {
    state.mapInstance = new maplibregl.Map({
      container: "maplibre-map",
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: [0, 0],
      zoom: 2,
    });
    state.mapInstance.addControl(new maplibregl.NavigationControl(), "top-right");
    state.mapInstance.on("click", (event) => {
      const feature = state.mapInstance.queryRenderedFeatures(event.point)[0];
      if (feature) showFeatureDetail(detail, feature.properties || {});
    });
  }
  const map = state.mapInstance;
  window.requestAnimationFrame(() => map.resize());
  if (!map.isStyleLoaded()) {
    map.once("load", () => updateMapLibre(data, detail, token));
    return;
  }
  if (!map.getSource("features")) {
    map.addSource("features", { type: "geojson", data: data });
  } else {
    map.getSource("features").setData(data);
  }
  const ensureLayer = (id, definition) => {
    if (!map.getLayer(id)) map.addLayer(definition);
    else {
      map.removeLayer(id);
      map.addLayer(definition);
    }
  };
  ensureLayer("blocks-fill", {
    id: "blocks-fill", type: "fill", source: "features",
    filter: ["==", ["get", "layer"], "blocks"],
    paint: {
      "fill-color": ["case", ["==", ["get", "treated"], true], "#c0392b", "#2f7d4f"],
      "fill-opacity": 0.55,
    },
  });
  ensureLayer("blocks-line", {
    id: "blocks-line", type: "line", source: "features",
    filter: ["==", ["get", "layer"], "blocks"],
    paint: { "line-color": "#1f2933", "line-width": 0.7 },
  });
  ensureLayer("treatments-fill", {
    id: "treatments-fill", type: "fill", source: "features",
    filter: ["==", ["get", "layer"], "treatments"],
    paint: {
      "fill-color": ["case", ["==", ["get", "current"], true], "#c0392b",
        ["==", ["get", "cumulative"], true], "#d9a066", "#2f7d4f"],
      "fill-opacity": 0.6,
    },
  });
  ensureLayer("machines-circle", {
    id: "machines-circle", type: "circle", source: "features",
    filter: ["==", ["get", "layer"], "machines"],
    paint: { "circle-radius": 5, "circle-color": "#1f6feb", "circle-stroke-color": "#fff",
             "circle-stroke-width": 1 },
  });
  ensureLayer("tactical-fill", {
    id: "tactical-fill", type: "fill", source: "features",
    filter: ["==", ["get", "layer"], "tactical_units"],
    paint: { "fill-color": "#1f6feb", "fill-opacity": 0.55 },
  });
  fitMapLibre(data);
}

function fitMapLibre(data) {
  const map = state.mapInstance;
  const bbox = featureBounds(data);
  if (!map || !bbox) return;
  map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 24, maxZoom: 14 });
}

function renderProvenance(summary, title) {
  const box = el("div", null, "provenance");
  box.appendChild(el("b", title));
  for (const [key, value] of Object.entries(summary)) {
    if (["files", "flow", "schedule"].includes(key)) continue;
    if (value !== null && typeof value === "object") continue;
    const item = el("span", `${key}: ${value === null ? "—" : value}`);
    box.appendChild(item);
  }
  return box;
}

function renderKpiCards(payload) {
  const grid = el("div", null, "cards");
  for (const [key, value] of Object.entries(payload).sort(([a], [b]) => a.localeCompare(b))) {
    if (value !== null && typeof value === "object") continue;
    const card = el("div", null, "card");
    card.appendChild(el("span", key.replaceAll("_", " "), "card-label"));
    const display = typeof value === "number"
      ? (Number.isInteger(value) ? value.toString() : value.toFixed(3))
      : (value === null ? "—" : String(value));
    card.appendChild(el("strong", display, "card-value"));
    grid.appendChild(card);
  }
  return grid;
}

function renderOperationalGantt(payload, time) {
  const days = (time.values || []).map(String);
  const shifts = time.shifts && time.shifts.length ? time.shifts : ["S1"];
  const total = Math.max(days.length * shifts.length, 1);
  const groups = new Map();
  for (const row of payload.rows || []) {
    if (row.assigned !== undefined && Number(row.assigned) === 0) continue;
    const machine = row.machine_id || "machine";
    const dayIndex = Math.max(0, days.indexOf(String(row.day)));
    const shiftIndex = Math.max(0, shifts.indexOf(String(row.shift_id || shifts[0])));
    const start = dayIndex * shifts.length + shiftIndex;
    const bar = {
      start,
      end: start + 1,
      label: row.block_id || "",
      color: barColor(row.block_id || machine),
      title: `${machine} · ${row.block_id} · day ${row.day} ${row.shift_id || ""}`,
    };
    if (!groups.has(machine)) groups.set(machine, []);
    groups.get(machine).push(bar);
  }
  return renderGantt("Machine / shift", groups, total, days, "Operational schedule");
}

function renderHaulGantt(payload) {
  const groups = new Map();
  let maxTime = 1;
  for (const row of payload.rows || []) {
    const start = Number(row.pickup_start ?? row.arrival_pickup ?? 0);
    const end = Number(row.delivery_finish ?? row.delivery_start ?? start + 1);
    maxTime = Math.max(maxTime, end, Number(row.truck_return_time ?? end));
    const truck = row.truck_id || "truck";
    const bar = {
      start,
      end,
      label: `${row.block_id || ""}→${row.yard_id || ""}`,
      color: barColor(row.contractor_id || truck),
      title: `${truck} · ${row.load_id} · ${start.toFixed(0)}–${end.toFixed(0)} min`,
    };
    if (!groups.has(truck)) groups.set(truck, []);
    groups.get(truck).push(bar);
  }
  const ticks = [0, Math.round(maxTime / 2), Math.round(maxTime)];
  return renderGantt("Truck / minute", groups, maxTime, ticks.map(String), "Truck and loader schedule");
}

function renderTacticalGantt(payload) {
  const periods = (state.tacticalTime?.values || []).map(String);
  const groups = new Map();
  for (const row of payload.rows || []) {
    const area = Number(row.harvested_area_ha ?? row.area_ha ?? 0);
    if (area <= 0) continue;
    const block = row.block_id || "block";
    const index = Math.max(0, periods.indexOf(String(row.period_id)));
    const bar = {
      start: index,
      end: index + 1,
      label: row.system_id || "",
      color: barColor(row.system_id || block),
      title: `${block} · ${row.period_id} · ${area.toFixed(2)} ha`,
    };
    if (!groups.has(block)) groups.set(block, []);
    groups.get(block).push(bar);
  }
  return renderGantt("Planning unit / period", groups, Math.max(periods.length, 1), periods, "Harvest decisions");
}

function renderGantt(axisLabel, groups, total, ticks, title) {
  const wrap = el("div", null, "gantt-wrap");
  wrap.appendChild(el("h3", title));
  if (!groups.size) {
    wrap.appendChild(el("p", "No rows for this view.", "hint"));
    return wrap;
  }
  const gantt = el("div", null, "gantt");
  for (const [label, bars] of [...groups.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    const row = el("div", null, "gantt-row");
    row.appendChild(el("div", label, "gantt-label"));
    const track = el("div", null, "gantt-track");
    for (const bar of bars) {
      const node = el("div", null, "gantt-bar");
      node.style.left = `${(bar.start / total) * 100}%`;
      node.style.width = `${Math.max(((bar.end - bar.start) / total) * 100, 0.4)}%`;
      node.style.background = bar.color;
      node.title = bar.title;
      if ((bar.end - bar.start) / total > 0.08) node.textContent = bar.label;
      track.appendChild(node);
    }
    row.appendChild(track);
    gantt.appendChild(row);
  }
  wrap.appendChild(gantt);
  const axis = el("div", null, "gantt-axis");
  axis.appendChild(el("span", axisLabel, "gantt-axis-label"));
  for (const tick of ticks) axis.appendChild(el("span", tick));
  wrap.appendChild(axis);
  return wrap;
}

function renderBars(payload, xKey, series) {
  const rows = payload.rows || [];
  const wrap = el("div", null, "bar-chart");
  if (!rows.length) {
    wrap.appendChild(el("p", "No rows for this view.", "hint"));
    return wrap;
  }
  const values = rows.flatMap((row) => series.map((key) => Number(row[key] ?? 0)));
  const max = Math.max(...values, 1);
  for (const row of rows) {
    const group = el("div", null, "bar-group");
    group.appendChild(el("div", `${row[xKey] ?? ""}`, "bar-group-label"));
    for (const key of series) {
      const value = Number(row[key] ?? 0);
      const item = el("div", null, "bar-item");
      item.appendChild(el("span", key.replaceAll("_", " "), "bar-name"));
      const track = el("div", null, "bar-track");
      const bar = el("div", null, "bar-fill");
      bar.style.width = `${Math.max((value / max) * 100, 0)}%`;
      bar.style.background = barColor(key);
      track.appendChild(bar);
      item.appendChild(track);
      item.appendChild(el("b", typeof value === "number" ? value.toFixed(2) : value));
      group.appendChild(item);
    }
    wrap.appendChild(group);
  }
  const table = renderTable(payload);
  table.classList.add("bar-table");
  wrap.appendChild(table);
  return wrap;
}

function renderCompare(encoded) {
  const controls = el("div", null, "compare-controls");
  const a = document.createElement("select");
  const b = document.createElement("select");
  for (const run of state.runs) {
    for (const select of [a, b]) {
      const option = el("option", run.run_id);
      option.value = run.run_id;
      select.appendChild(option);
    }
  }
  a.value = state.run.run_id;
  b.value = (state.runs.find((run) => run.run_id !== state.run.run_id) || state.run).run_id;
  const loadButton = el("button", "Compare");
  loadButton.type = "button";
  controls.appendChild(el("label", "A "));
  controls.appendChild(a);
  controls.appendChild(el("label", " B "));
  controls.appendChild(b);
  controls.appendChild(loadButton);
  els.body.appendChild(controls);
  const target = el("div");
  els.body.appendChild(target);

  const load = async () => {
    target.innerHTML = "";
    try {
      const [kpisA, kpisB, summaryA, summaryB] = await Promise.all([
        fetchJson(`api/runs/${encodeURIComponent(a.value)}/kpis`).catch(() => ({})),
        fetchJson(`api/runs/${encodeURIComponent(b.value)}/kpis`).catch(() => ({})),
        fetchJson(`api/runs/${encodeURIComponent(a.value)}/summary`).catch(() => ({})),
        fetchJson(`api/runs/${encodeURIComponent(b.value)}/summary`).catch(() => ({})),
      ]);
      target.appendChild(renderProvenance(summaryA, `A · ${a.value}`));
      target.appendChild(renderProvenance(summaryB, `B · ${b.value}`));
      const keys = [...new Set([...Object.keys(kpisA), ...Object.keys(kpisB)])]
        .filter((key) => typeof kpisA[key] !== "object" && typeof kpisB[key] !== "object")
        .sort();
      const payload = {
        columns: ["metric", "A", "B", "B-A"],
        rows: keys.map((key) => {
          const av = kpisA[key];
          const bv = kpisB[key];
          const delta = typeof av === "number" && typeof bv === "number" ? bv - av : "";
          return { metric: key, A: av ?? "—", B: bv ?? "—", "B-A": delta };
        }),
        total: keys.length,
        returned: keys.length,
        run_id: "compare",
        artefact: "kpis",
      };
      target.appendChild(renderTable(payload));
    } catch (error) {
      target.appendChild(el("p", error.message, "warnings"));
    }
  };
  loadButton.addEventListener("click", load);
  return load();
}

function barColor(key) {
  const palette = ["#2f7d4f", "#b45309", "#1f6feb", "#6b4c9a", "#c0392b", "#0f766e", "#7c3aed"];
  let hash = 0;
  for (const char of String(key)) hash = (hash * 31 + char.charCodeAt(0)) | 0;
  return palette[Math.abs(hash) % palette.length];
}


function editStatus() {
  return el("div", "", "edit-status");
}

function setEditStatus(node, text, kind = "") {
  node.textContent = text;
  node.className = `edit-status ${kind}`.trim();
}

function numberInput(value, step = "any") {
  const input = document.createElement("input");
  input.type = "number";
  input.step = step;
  if (value !== undefined && value !== null) input.value = String(value);
  return input;
}

function textInput(value, size = 18) {
  const input = document.createElement("input");
  input.type = "text";
  input.value = value ?? "";
  input.size = size;
  return input;
}

function labelInput(label, input) {
  const wrapper = el("label", label);
  wrapper.appendChild(input);
  return wrapper;
}

async function renderScenario(encoded) {
  const payload = await fetchJson(`api/scenarios/${encoded}`);
  const domain = payload.domain || domainForSkin();
  const head = el("div", "", "scenario-head");
  head.appendChild(el("b", "Scenario: "));
  head.appendChild(document.createTextNode(payload.path));
  els.body.appendChild(head);
  if (state.skin?.read_only) {
    els.body.appendChild(el("p", "This skin is read-only.", "hint"));
    return;
  }
  if (domain === "operational") return renderOperationalScenario(encoded, payload);
  if (domain === "hauling") return renderHaulingScenario(encoded, payload);
  if (domain === "tactical_operational") return renderTacticalScenario(encoded, payload);
  els.body.appendChild(el("p", "No editor is available for this scenario.", "hint"));
}

function renderOperationalScenario(encoded, payload) {
  const status = editStatus();
  const weights = payload.objective_weights || {
    production: 1.0,
    mobilisation: 1.0,
    transitions: 0.0,
    landing_surplus: 0.0,
  };
  const objectiveForm = el("div", null, "edit-form");
  const objectiveInputs = {};
  for (const key of ["production", "mobilisation", "transitions", "landing_surplus"]) {
    objectiveInputs[key] = numberInput(weights[key] ?? 0);
    objectiveForm.appendChild(labelInput(key, objectiveInputs[key]));
  }
  const saveObjective = el("button", "Save objective");
  saveObjective.type = "button";
  objectiveForm.appendChild(saveObjective);
  els.body.appendChild(el("h3", "Objective weights"));
  els.body.appendChild(objectiveForm);
  els.body.appendChild(status);
  saveObjective.addEventListener("click", async () => {
    const weightsPayload = {};
    for (const [key, input] of Object.entries(objectiveInputs)) weightsPayload[key] = Number(input.value);
    try {
      await putJson(`api/scenarios/${encoded}/objective`, { weights: weightsPayload });
      setEditStatus(status, "Objective saved.", "ok");
    } catch (error) {
      setEditStatus(status, error.message, "error");
    }
  });

  let locks = (payload.locked_assignments || []).map((lock) => ({ ...lock }));
  els.body.appendChild(el("h3", "Schedule locks"));
  const table = el("table", null, "data-table edit-table");
  table.innerHTML = "<thead><tr><th>Machine</th><th>Block</th><th>Day</th><th>Shift</th><th>Production</th><th></th></tr></thead><tbody></tbody>";
  const tbody = table.querySelector("tbody");
  const addLockRow = (lock = {}) => {
    const row = document.createElement("tr");
    const machine = textInput(lock.machine_id, 10);
    const block = textInput(lock.block_id, 10);
    const day = numberInput(lock.day, "1");
    const shift = textInput(lock.shift_id, 6);
    const production = numberInput(lock.production);
    for (const input of [machine, block, day, shift, production]) {
      const cell = document.createElement("td");
      cell.appendChild(input);
      row.appendChild(cell);
    }
    const remove = el("button", "Remove");
    remove.type = "button";
    remove.addEventListener("click", () => row.remove());
    const cell = document.createElement("td");
    cell.appendChild(remove);
    row.appendChild(cell);
    tbody.appendChild(row);
  };
  locks.forEach(addLockRow);
  els.body.appendChild(table);
  const lockControls = el("div", null, "edit-controls");
  const addLock = el("button", "Add lock");
  addLock.type = "button";
  addLock.addEventListener("click", () => addLockRow());
  const saveLocks = el("button", "Save locks");
  saveLocks.type = "button";
  saveLocks.addEventListener("click", async () => {
    const rows = [];
    for (const row of tbody.querySelectorAll("tr")) {
      const inputs = row.querySelectorAll("input");
      if (!inputs[0].value || !inputs[1].value || !inputs[2].value) continue;
      rows.push({
        machine_id: inputs[0].value,
        block_id: inputs[1].value,
        day: Number(inputs[2].value),
        shift_id: inputs[3].value || null,
        production: inputs[4].value === "" ? null : Number(inputs[4].value),
      });
    }
    try {
      await putJson(`api/scenarios/${encoded}/locks`, { locks: rows });
      setEditStatus(status, "Locks saved.", "ok");
    } catch (error) {
      setEditStatus(status, error.message, "error");
    }
  });
  lockControls.appendChild(addLock);
  lockControls.appendChild(saveLocks);
  els.body.appendChild(lockControls);
}

function renderHaulingScenario(encoded, payload) {
  const status = editStatus();
  const hauling = payload.hauling;
  if (!hauling) {
    els.body.appendChild(el("p", "This scenario has no hauling section.", "hint"));
    return;
  }
  const policy = hauling.driver_policy || {};
  const policyForm = el("div", null, "edit-form");
  const policyInputs = {
    regular_minutes: numberInput(policy.regular_minutes ?? 510),
    max_overtime_minutes: numberInput(policy.max_overtime_minutes ?? 150),
    overtime_violation_penalty_per_minute: numberInput(policy.overtime_violation_penalty_per_minute ?? 0),
  };
  for (const [key, input] of Object.entries(policyInputs)) {
    policyForm.appendChild(labelInput(key, input));
  }
  const savePolicy = el("button", "Save driver policy");
  savePolicy.type = "button";
  policyForm.appendChild(savePolicy);
  els.body.appendChild(el("h3", "Driver policy"));
  els.body.appendChild(policyForm);
  els.body.appendChild(status);

  const contractors = (hauling.contractors || []).map((row) => ({ ...row }));
  const table = el("table", null, "data-table edit-table");
  table.innerHTML = "<thead><tr><th>Contractor</th><th>Name</th><th>Preferred truckloads/day</th></tr></thead><tbody></tbody>";
  const tbody = table.querySelector("tbody");
  for (const contractor of contractors) {
    const row = document.createElement("tr");
    const id = textInput(contractor.id, 10);
    id.disabled = true;
    const name = textInput(contractor.name, 18);
    const preferred = numberInput(contractor.preferred_daily_truckloads);
    for (const input of [id, name, preferred]) {
      const cell = document.createElement("td");
      cell.appendChild(input);
      row.appendChild(cell);
    }
    tbody.appendChild(row);
  }
  els.body.appendChild(el("h3", "Contractor preferences"));
  els.body.appendChild(table);
  const saveAll = el("button", "Save hauling edits");
  saveAll.type = "button";
  saveAll.addEventListener("click", async () => {
    const contractorRows = [];
    for (const row of tbody.querySelectorAll("tr")) {
      const inputs = row.querySelectorAll("input");
      contractorRows.push({
        id: inputs[0].value,
        name: inputs[1].value,
        preferred_daily_truckloads: inputs[2].value === "" ? null : Number(inputs[2].value),
      });
    }
    try {
      await putJson(`api/scenarios/${encoded}/hauling`, {
        driver_policy: {
          regular_minutes: Number(policyInputs.regular_minutes.value),
          max_overtime_minutes: Number(policyInputs.max_overtime_minutes.value),
          overtime_violation_penalty_per_minute: Number(policyInputs.overtime_violation_penalty_per_minute.value),
        },
        contractors: contractorRows,
      });
      setEditStatus(status, "Hauling edits saved.", "ok");
    } catch (error) {
      setEditStatus(status, error.message, "error");
    }
  });
  els.body.appendChild(saveAll);
}

function renderTacticalScenario(encoded, payload) {
  const status = editStatus();
  const tactical = payload.tactical || {};
  els.body.appendChild(el("p", "Demand envelopes are written as a validated overlay; the base tactical bundle is not modified.", "hint"));
  const rows = (tactical.facility_demand || []).map((row) => ({ ...row }));
  const table = el("table", null, "data-table edit-table tactical-edit-table");
  table.innerHTML = "<thead><tr><th>Facility</th><th>Product</th><th>Period</th><th>Minimum m³</th><th>Target m³</th><th>Maximum m³</th><th>Value/m³</th></tr></thead><tbody></tbody>";
  const tbody = table.querySelector("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    const identity = [row.facility_id, row.product_id, row.period_id];
    identity.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value ?? "";
      tr.appendChild(cell);
    });
    for (const key of ["minimum_m3", "target_m3", "maximum_m3", "value_per_m3"]) {
      const cell = document.createElement("td");
      const input = numberInput(row[key]);
      input.dataset.key = key;
      cell.appendChild(input);
      tr.appendChild(cell);
    }
    tbody.appendChild(tr);
  }
  els.body.appendChild(table);
  const controls = el("div", null, "edit-controls");
  const save = el("button", "Validate and save overlay");
  save.type = "button";
  const useDerived = el("button", "Use derived scenario in Run");
  useDerived.type = "button";
  useDerived.disabled = true;
  useDerived.addEventListener("click", () => {
    if (!state.runScenarioOverride) return;
    setPanel("run");
  });
  controls.appendChild(save);
  controls.appendChild(useDerived);
  els.body.appendChild(controls);
  els.body.appendChild(status);

  const overlayRows = () => {
    const output = [];
    for (const tr of tbody.querySelectorAll("tr")) {
      const cells = tr.querySelectorAll("td");
      const row = {
        facility_id: cells[0].textContent,
        product_id: cells[1].textContent,
        period_id: cells[2].textContent,
      };
      for (const input of tr.querySelectorAll("input")) {
        row[input.dataset.key] = input.value === "" ? null : Number(input.value);
      }
      output.push(row);
    }
    return output;
  };

  save.addEventListener("click", async () => {
    try {
      const response = await putJson(`api/scenarios/${encoded}/tactical`, {
        overlay: { facility_demand: overlayRows() },
      });
      const tactical = response.tactical || {};
      state.runScenarioOverride = tactical.derived_path || null;
      useDerived.disabled = !state.runScenarioOverride;
      setEditStatus(
        status,
        `Overlay saved: ${tactical.overlay_path}. Derived scenario: ${tactical.derived_path}`,
        "ok",
      );
    } catch (error) {
      setEditStatus(status, error.message, "error");
    }
  });
}

function domainForSkin() {
  if (!state.skin) return "operational";
  if (state.skin.id === "hauling-planner") return "hauling";
  if (state.skin.id === "tactical-planner") return "tactical_operational";
  return "operational";
}

function renderRunPanel() {
  const domain = domainForSkin();
  const defaults = {
    operational: "examples/tiny7/scenario.yaml",
    hauling: "examples/hauling/scenario.yaml",
    tactical_operational: "tests/fixtures/tactical_operational/practitioner-case/scenario.yaml",
  };
  const scenarioDefault =
    state.runScenarioOverride ||
    (state.run?.domain === domain && state.run?.manifest?.scenario
      ? state.run.manifest.scenario
      : defaults[domain] || "");
  const runTypes = {
    operational: [
      ["Heuristic SA", "solve_heur"],
      ["Iterated local search", "solve_ils"],
      ["Tabu search", "solve_tabu"],
      ["Operational MIP", "solve_mip_operational"],
      ["Playback", "eval_playback"],
      ["Rolling horizon", "plan_rolling"],
    ],
    hauling: [
      ["Haul solve", "haul_solve"],
      ["Phase I plan", "haul_plan"],
      ["Phase II/III schedule", "haul_schedule"],
    ],
    tactical_operational: [
      ["Tactical-operational", "tactical_operational"],
      ["Tactical report", "tactical_report"],
    ],
  }[domain];
  const currentAssignments =
    state.run?.domain === "operational" && state.run?.files?.assignments
      ? `${state.run.path}/${state.run.files.assignments}`
      : "";
  const currentSummary =
    state.run?.domain === "tactical_operational" && state.run?.files?.summary
      ? `${state.run.path}/${state.run.files.summary}`
      : "";

  const form = el("div", null, "run-form");
  const scenarioLabel = el("label", "Scenario");
  const scenario = document.createElement("input");
  scenario.type = "text";
  scenario.value = scenarioDefault;
  scenario.size = 56;
  scenarioLabel.appendChild(scenario);
  form.appendChild(scenarioLabel);

  const typeLabel = el("label", "Run type");
  const runType = document.createElement("select");
  for (const [label, value] of runTypes) {
    const option = el("option", label);
    option.value = value;
    runType.appendChild(option);
  }
  typeLabel.appendChild(runType);
  form.appendChild(typeLabel);

  const assignmentsLabel = el("label", "Assignments CSV");
  const assignments = document.createElement("input");
  assignments.type = "text";
  assignments.value = currentAssignments;
  assignments.size = 48;
  assignments.placeholder = "assignments.csv";
  assignmentsLabel.appendChild(assignments);
  assignmentsLabel.hidden = true;
  form.appendChild(assignmentsLabel);

  const resultLabel = el("label", "Result JSON");
  const resultJson = document.createElement("input");
  resultJson.type = "text";
  resultJson.value = currentSummary;
  resultJson.size = 48;
  resultJson.placeholder = "summary.json";
  resultLabel.appendChild(resultJson);
  resultLabel.hidden = true;
  form.appendChild(resultLabel);

  const iterationsLabel = el("label", "Iterations");
  const iterations = document.createElement("input");
  iterations.type = "number";
  iterations.value = "500";
  iterations.min = "1";
  iterationsLabel.appendChild(iterations);
  form.appendChild(iterationsLabel);

  const seedLabel = el("label", "Seed");
  const seed = document.createElement("input");
  seed.type = "number";
  seed.value = "42";
  seedLabel.appendChild(seed);
  form.appendChild(seedLabel);

  const dayLabel = el("label", "Day");
  const day = document.createElement("input");
  day.type = "number";
  day.value = "1";
  day.min = "1";
  dayLabel.appendChild(day);
  form.appendChild(dayLabel);

  const solverLabel = el("label", "Solver");
  const solver = document.createElement("select");
  solverLabel.appendChild(solver);
  form.appendChild(solverLabel);

  const masterLabel = el("label", "Master days");
  const masterDays = document.createElement("input");
  masterDays.type = "number";
  masterDays.value = "84";
  masterDays.min = "1";
  masterLabel.appendChild(masterDays);
  masterLabel.hidden = true;
  form.appendChild(masterLabel);

  const subLabel = el("label", "Window days");
  const subDays = document.createElement("input");
  subDays.type = "number";
  subDays.value = "28";
  subDays.min = "1";
  subLabel.appendChild(subDays);
  subLabel.hidden = true;
  form.appendChild(subLabel);

  const lockLabel = el("label", "Lock days");
  const lockDays = document.createElement("input");
  lockDays.type = "number";
  lockDays.value = "14";
  lockDays.min = "1";
  lockLabel.appendChild(lockDays);
  lockLabel.hidden = true;
  form.appendChild(lockLabel);

  const timeLabel = el("label", "Time limit (s)");
  const timeLimit = document.createElement("input");
  timeLimit.type = "number";
  timeLimit.min = "0";
  timeLimit.placeholder = "none";
  timeLabel.appendChild(timeLimit);
  form.appendChild(timeLabel);

  const solverChoices = (type) => {
    if (type === "haul_plan") return ["highs"];
    if (type === "plan_rolling") return ["sa", "mip", "stub"];
    return ["sa", "mip"];
  };
  const setSolverChoices = () => {
    const previous = solver.value;
    solver.innerHTML = "";
    for (const value of solverChoices(runType.value)) {
      const option = el("option", value);
      option.value = value;
      solver.appendChild(option);
    }
    if ([...solver.options].some((option) => option.value === previous)) solver.value = previous;
  };
  const updateVisibility = () => {
    const type = runType.value;
    assignmentsLabel.hidden = type !== "eval_playback";
    resultLabel.hidden = type !== "tactical_report";
    const rolling = type === "plan_rolling";
    masterLabel.hidden = !rolling;
    subLabel.hidden = !rolling;
    lockLabel.hidden = !rolling;
    setSolverChoices();
  };
  runType.addEventListener("change", updateVisibility);
  updateVisibility();

  const start = el("button", "Start run");
  start.type = "button";
  form.appendChild(start);
  els.body.appendChild(form);

  const status = el("div", "No live run.", "run-status");
  const metrics = el("div", "", "run-metrics");
  const controls = el("div", null, "run-controls");
  const pause = el("button", "Pause");
  const resume = el("button", "Resume");
  const stop = el("button", "Stop");
  for (const button of [pause, resume, stop]) {
    button.type = "button";
    button.disabled = true;
    controls.appendChild(button);
  }
  const spark = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  spark.setAttribute("class", "sparkline");
  spark.setAttribute("viewBox", "0 0 320 64");
  els.body.appendChild(status);
  els.body.appendChild(metrics);
  els.body.appendChild(controls);
  els.body.appendChild(spark);

  let liveId = null;
  let source = null;
  let pollTimer = null;
  let points = [];
  let objectiveText = "";
  let kpiText = "";
  let assignmentText = "";

  const setStatus = (text, kind = "") => {
    status.textContent = text;
    status.className = `run-status ${kind}`.trim();
  };
  const setButtons = (enabled) => {
    for (const button of [pause, resume, stop]) button.disabled = !enabled;
  };
  const renderMetrics = () => {
    metrics.textContent = [objectiveText, kpiText, assignmentText].filter(Boolean).join(" · ");
  };
  const drawSpark = () => {
    spark.innerHTML = "";
    if (points.length < 2) return;
    const values = points.map((point) => Number(point.objective)).filter((value) => Number.isFinite(value));
    if (values.length < 2) return;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = Math.max(max - min, 1e-9);
    const path = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    const coords = values.map((value, index) => {
      const x = 6 + (index / (values.length - 1)) * 308;
      const y = 58 - ((value - min) / span) * 52;
      return `${x},${y}`;
    }).join(" ");
    path.setAttribute("points", coords);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "#1f6feb");
    path.setAttribute("stroke-width", "1.5");
    spark.appendChild(path);
  };
  const updateProgress = (payload) => {
    if (payload.objective !== undefined && payload.objective !== null) {
      points.push(payload);
      if (points.length > 400) points.shift();
      const label = payload.window ? `window ${payload.iteration ?? "—"}` : `step ${payload.iteration ?? payload.step ?? "—"}`;
      objectiveText = `${label} · objective ${payload.objective} · best ${payload.best ?? "—"}`;
      renderMetrics();
      drawSpark();
    } else if (payload.elapsed_seconds !== undefined && !objectiveText) {
      objectiveText = `elapsed ${Number(payload.elapsed_seconds).toFixed(1)} s`;
      renderMetrics();
    }
  };
  const closeLive = () => {
    if (source) source.close();
    source = null;
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
    setButtons(false);
  };
  const pollStatus = async () => {
    if (!liveId) return;
    try {
      const payload = await fetchJson(`api/runs/${encodeURIComponent(liveId)}/status`);
      setStatus(`${payload.status} · ${payload.finished ? "finished" : "running"}`, payload.status);
      if (payload.finished) {
        closeLive();
        await refreshRuns();
        setStatus(`finished: ${payload.status}`, payload.status);
      }
    } catch (error) {
      setStatus(error.message, "error");
    }
  };
  const watch = (runId) => {
    closeLive();
    liveId = runId;
    points = [];
    objectiveText = "";
    kpiText = "";
    assignmentText = "";
    metrics.textContent = "";
    setButtons(true);
    setStatus(`running ${runId}`, "running");
    pollTimer = setInterval(pollStatus, 1000);
    if (window.EventSource) {
      source = new EventSource(api(`api/runs/${encodeURIComponent(runId)}/events`));
      source.addEventListener("progress", (event) => {
        try { updateProgress(JSON.parse(event.data)); } catch (_error) { /* ignore */ }
      });
      source.addEventListener("kpis", (event) => {
        try {
          const payload = JSON.parse(event.data);
          const keys = ["total_production", "mobilisation_cost", "utilisation_ratio_mean_day", "objective"];
          kpiText = keys
            .filter((key) => payload[key] !== undefined && payload[key] !== null)
            .map((key) => `${key} ${Number(payload[key]).toFixed(2)}`)
            .join(" · ");
          renderMetrics();
        } catch (_error) { /* ignore */ }
      });
      source.addEventListener("assignment", (event) => {
        try {
          const payload = JSON.parse(event.data);
          assignmentText = `last ${payload.machine_id ?? "?"}@${payload.block_id ?? "?"} d${payload.day ?? "?"} ${payload.shift_id ?? ""}`.trim();
          renderMetrics();
        } catch (_error) { /* ignore */ }
      });
      source.addEventListener("done", (event) => {
        setStatus(`done: ${runId}`, "ok");
        closeLive();
        refreshRuns();
      });
      source.addEventListener("error", () => {
        if (source && source.readyState === EventSource.CLOSED) {
          setStatus(`stream closed: ${runId}`, "error");
        }
      });
    }
    pollStatus();
  };

  start.addEventListener("click", async () => {
    const options = {
      iterations: Number(iterations.value) || 500,
      seed: Number(seed.value) || 42,
      day: Number(day.value) || 1,
      solver: solver.value,
      master_days: Number(masterDays.value) || 84,
      sub_days: Number(subDays.value) || 28,
      lock_days: Number(lockDays.value) || 14,
    };
    if (timeLimit.value) options.time_limit = Number(timeLimit.value);
    if (assignments.value) options.assignments = assignments.value;
    if (resultJson.value) options.result_json = resultJson.value;
    setStatus("starting…", "running");
    start.disabled = true;
    try {
      const response = await postJson("api/runs", {
        domain,
        run_type: runType.value,
        scenario: scenario.value,
        options,
      });
      watch(response.run_id);
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      start.disabled = false;
    }
  });

  const control = async (action) => {
    if (!liveId) return;
    try {
      const payload = await postJson(`api/runs/${encodeURIComponent(liveId)}/control`, { action });
      setStatus(`${action}: ${payload.status}`, payload.status);
      if (payload.finished) {
        closeLive();
        await refreshRuns();
      }
    } catch (error) {
      setStatus(error.message, "error");
    }
  };
  pause.addEventListener("click", () => control("pause"));
  resume.addEventListener("click", () => control("resume"));
  stop.addEventListener("click", () => control("stop"));
  return Promise.resolve();
}

async function refreshRuns() {
  state.runs = await fetchJson("api/runs");
  renderRuns();
}

renderAssistant();
