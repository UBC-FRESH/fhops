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

function renderPanel() {
  if (!state.run || !state.skin) return Promise.resolve();
  els.body.innerHTML = "";
  els.title.textContent = PANEL_LABELS[state.panel] || state.panel;
  const run = state.run;
  const encoded = encodeURIComponent(run.run_id);
  switch (state.panel) {
    case "legend":
      return renderLegend(run);
    case "schedule":
      return renderDataset(`api/runs/${encoded}/assignments?limit=5000`, "Assignments");
    case "haul":
      return renderChooser("haul", [
        ["Flows", `${encoded}/hauling/flows`],
        ["Truckloads", `${encoded}/hauling/truckloads`],
        ["Truck / loader schedule", `${encoded}/hauling/schedule`],
        ["Yard inventory", `${encoded}/hauling/yard-inventory`],
        ["Contractor workload", `${encoded}/hauling/contractor-workload`],
        ["Trucks", `${encoded}/hauling/trucks`],
        ["Loaders", `${encoded}/hauling/loaders`],
      ]);
    case "tactical":
      return renderChooser("tactical", [
        ["Harvest decisions", `${encoded}/tactical/harvest`],
        ["Production", `${encoded}/tactical/production`],
        ["Flows", `${encoded}/tactical/flows`],
        ["Inventory", `${encoded}/tactical/inventory`],
        ["Purchases", `${encoded}/tactical/purchases`],
        ["Roads", `${encoded}/tactical/roads`],
        ["Silviculture", `${encoded}/tactical/silviculture`],
        ["Fleet", `${encoded}/tactical/fleet`],
      ]);
    case "kpis":
      return fetchJson(`api/runs/${encoded}/kpis`).then(renderKeyValues);
    case "reports":
      return renderReports(encoded);
    case "compare":
      return renderPlaceholder("Run comparison", "Two-run map, KPI, and assignment deltas arrive in P12.4.");
    case "scenario":
      return renderPlaceholder("Scenario editing", "Validated operational/hauling/tactical edits arrive in P12.6.");
    case "map":
      return renderPlaceholder("Map", "The map, layer tree, and day/shift/period control arrive in P12.3.");
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
  for (const [title, path] of entries) {
    const option = el("option", title);
    option.value = path;
    select.appendChild(option);
  }
  label.appendChild(select);
  controls.appendChild(label);
  els.body.appendChild(controls);
  const target = el("div");
  els.body.appendChild(target);
  const load = () => {
    target.innerHTML = "";
    fetchJson(`api/runs/${select.value}`).then((payload) => target.appendChild(renderTable(payload)))
      .catch((error) => target.appendChild(el("p", error.message, "warnings")));
  };
  select.addEventListener("change", load);
  load();
  return Promise.resolve();
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
  container.appendChild(note);
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
  els.body.appendChild(grid);
}

function renderReports(encoded) {
  return fetchJson(`api/runs/${encoded}/reports`).then((payload) => {
    if (!payload.reports.length) {
      els.body.appendChild(el("p", "No report files were found.", "hint"));
      return;
    }
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
    els.body.appendChild(list);
  });
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

async function boot() {
  try {
    const [skins, runs] = await Promise.all([fetchJson("api/skins"), fetchJson("api/runs")]);
    state.skins = skins;
    state.runs = runs;
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
