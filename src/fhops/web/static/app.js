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

async function renderMap(encoded) {
  const [time, layerPayload] = await Promise.all([
    fetchJson(`api/runs/${encoded}/time`),
    fetchJson(`api/runs/${encoded}/layers`),
  ]);
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
  svg.id = "svg-map";
  const mapDiv = el("div");
  mapDiv.id = "maplibre-map";
  mapDiv.className = state.mapRenderer === "maplibre" ? "" : "hidden";
  svg.className = state.mapRenderer === "svg" ? "" : "hidden";
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
    renderTree();
    note.textContent = "loading map…";
    const params = new URLSearchParams();
    if (time.unit === "period") params.set("period", state.mapStep);
    else params.set("day", state.mapStep);
    if (state.mapShift) params.set("shift", state.mapShift);
    if (state.mapSelected.size) params.set("layers", Array.from(state.mapSelected).join(","));
    try {
      const data = await fetchJson(`api/runs/${encoded}/map?${params.toString()}`);
      state.mapData = data;
      note.textContent = `${data.features.length} feature(s)`;
      detail.hidden = true;
      if (state.mapRenderer === "maplibre" && window.maplibregl) {
        await updateMapLibre(data, detail);
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
      note.textContent = error.message;
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

async function updateMapLibre(data, detail) {
  if (!window.maplibregl) return;
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
  if (!map.isStyleLoaded()) {
    map.once("load", () => updateMapLibre(data, detail));
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
