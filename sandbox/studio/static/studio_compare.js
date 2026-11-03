const API = new URL("api/", document.baseURI).pathname;
const $ = (selector) => document.querySelector(selector);
const params = new URLSearchParams(location.search);
let projects = [];

async function api(path) {
  const response = await fetch(API + path.replace(/^\/+/, ""));
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch (_error) { /* ignore */ }
    throw new Error(detail);
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function fmt(value, digits = 1) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "—";
}

function freshnessLabel(freshness) {
  return freshness?.stale ? "stale" : "fresh";
}

async function loadProjects() {
  const payload = await api("projects");
  projects = payload.projects || [];
  for (const id of ["left-project", "right-project"]) {
    const select = $(`#${id}`);
    select.innerHTML = projects.map((project) => (
      `<option value="${escapeHtml(project.project_id)}">${escapeHtml(project.label || project.project_id)}</option>`
    )).join("");
  }
}

async function loadRuns(side, projectId) {
  const select = $(`#${side}-run`);
  select.innerHTML = "<option value=\"\">Loading…</option>";
  if (!projectId) {
    select.innerHTML = "<option value=\"\">No project</option>";
    return;
  }
  const payload = await api(`projects/${encodeURIComponent(projectId)}/runs`);
  const runs = payload.runs || [];
  select.innerHTML = runs.length
    ? runs.map((run) => `<option value="${escapeHtml(run.run_id)}">${escapeHtml(run.run_id)}${run.freshness?.stale ? " · stale" : ""}</option>`).join("")
    : "<option value=\"\">No runs</option>";
}

async function initSelectors() {
  await loadProjects();
  if (!projects.length) {
    $("#status").textContent = "No projects";
    return;
  }
  const leftProject = params.get("left_project") || projects[0]?.project_id || "";
  const rightProject = params.get("right_project") || projects[1]?.project_id || projects[0]?.project_id || "";
  $("#left-project").value = leftProject;
  $("#right-project").value = rightProject;
  await Promise.all([loadRuns("left", leftProject), loadRuns("right", rightProject)]);
  if (params.get("left_run")) $("#left-run").value = params.get("left_run");
  if (params.get("right_run")) $("#right-run").value = params.get("right_run");
}

async function runData(projectId, runId) {
  const [meta, events, dataset] = await Promise.all([
    api(`projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}`),
    api(`projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/events`).catch(() => null),
    api(`projects/${encodeURIComponent(projectId)}/dataset`).catch(() => null),
  ]);
  return { projectId, runId, meta, events, dataset };
}

function economics(data) {
  const run = data.meta.run;
  const makespanH = Number(run.kpis?.makespan_s || 0) / 3600;
  const catalog = new Map((data.dataset?.project?.catalog || []).map((item) => [item.id, item]));
  const machineIds = Object.keys(run.kpis?.machine_summaries || {});
  let cost = 0;
  let priced = 0;
  for (const id of machineIds) {
    const item = catalog.get(id);
    const daily = Number(item?.operating_cost || 0);
    const hours = Number(item?.daily_hours || 24);
    if (daily > 0) {
      priced += 1;
      cost += daily * (makespanH / Math.max(1, hours));
    }
  }
  const volume = Number(run.kpis?.processed_volume_m3 || 0);
  return {
    machineCount: machineIds.length,
    pricedMachineCount: priced,
    makespanH,
    cost,
    costPerM3: volume > 0 && priced > 0 ? cost / volume : null,
  };
}

function economicsRows(left, right) {
  const a = economics(left);
  const b = economics(right);
  const rows = [
    ["Active machines", a.machineCount, b.machineCount],
    ["Costed machines", a.pricedMachineCount, b.pricedMachineCount],
    ["Machine operating cost", a.pricedMachineCount ? `$${a.cost.toFixed(0)}` : "unavailable", b.pricedMachineCount ? `$${b.cost.toFixed(0)}` : "unavailable"],
    ["Cost per m³", a.costPerM3 == null ? "unavailable" : `$${a.costPerM3.toFixed(2)}`, b.costPerM3 == null ? "unavailable" : `$${b.costPerM3.toFixed(2)}`],
  ];
  return rows.map(([label, av, bv]) => `<tr><th>${label}</th><td class="num">${av}</td><td class="num">${bv}</td></tr>`).join("");
}

function comparisonRows(left, right) {
  const l = left.meta.run;
  const r = right.meta.run;
  const rows = [
    ["Project", left.projectId, right.projectId],
    ["Run", l.run_id, r.run_id],
    ["Freshness", freshnessLabel(left.meta.freshness), freshnessLabel(right.meta.freshness)],
    ["Trees", l.kpis?.tree_count, r.kpis?.tree_count],
    ["Volume m³", fmt(l.kpis?.processed_volume_m3), fmt(r.kpis?.processed_volume_m3)],
    ["Makespan h", fmt(Number(l.kpis?.makespan_s) / 3600), fmt(Number(r.kpis?.makespan_s) / 3600)],
    ["Warnings", (l.warnings || []).length, (r.warnings || []).length],
  ];
  return rows.map(([label, a, b]) => {
    const klass = label === "Freshness" && (a === "stale" || b === "stale") ? "bad" : "";
    return `<tr><th>${escapeHtml(label)}</th><td class="${klass} num">${escapeHtml(a)}</td><td class="${klass} num">${escapeHtml(b)}</td></tr>`;
  }).join("");
}

function machineRows(left, right) {
  const lm = left.meta.run.kpis?.machine_summaries || {};
  const rm = right.meta.run.kpis?.machine_summaries || {};
  const ids = [...new Set([...Object.keys(lm), ...Object.keys(rm)])].sort();
  return ids.map((id) => {
    const a = lm[id] || {};
    const b = rm[id] || {};
    return `<tr><th>${escapeHtml(id)}</th><td class="num">${fmt(Number(a.busy_s) / 3600)} h · ${fmt(Number(a.utilisation) * 100, 0)}%</td><td class="num">${fmt(Number(b.busy_s) / 3600)} h · ${fmt(Number(b.utilisation) * 100, 0)}%</td></tr>`;
  }).join("");
}

function truckRows(left, right) {
  const a = left.meta.run.kpis?.truck_summary || {};
  const b = right.meta.run.kpis?.truck_summary || {};
  const rows = [
    ["Dispatched loads", a.dispatched_loads, b.dispatched_loads],
    ["Dispatched m³", fmt(a.dispatched_volume_m3), fmt(b.dispatched_volume_m3)],
    ["Final landing m³", fmt(a.landing_inventory_final_m3), fmt(b.landing_inventory_final_m3)],
    ["Peak landing m³", fmt(a.landing_inventory_max_m3), fmt(b.landing_inventory_max_m3)],
    ["Mill wait s", fmt(a.mill_wait_s), fmt(b.mill_wait_s)],
  ];
  return rows.map(([label, av, bv]) => `<tr><th>${label}</th><td class="num">${av ?? "—"}</td><td class="num">${bv ?? "—"}</td></tr>`).join("");
}

function landingRows(left, right) {
  const a = left.events?.landing_inventory || {};
  const b = right.events?.landing_inventory || {};
  const ids = [...new Set([...Object.keys(a), ...Object.keys(b)])].sort();
  if (!ids.length) return "";
  return ids.map((id) => {
    const av = a[id] || {};
    const bv = b[id] || {};
    return `<tr><th>${escapeHtml(id)}</th><td class="num">${fmt(av.final_m3)} / ${fmt(av.max_m3)} m³</td><td class="num">${fmt(bv.final_m3)} / ${fmt(bv.max_m3)} m³</td></tr>`;
  }).join("");
}

function render(left, right) {
  $("#summary").innerHTML = `<h2>Summary</h2><table><thead><tr><th>Metric</th><th>${escapeHtml(left.projectId)}<br><span class="muted">${escapeHtml(left.runId)}</span></th><th>${escapeHtml(right.projectId)}<br><span class="muted">${escapeHtml(right.runId)}</span></th></tr></thead><tbody>${comparisonRows(left, right)}</tbody></table>`;
  $("#economics").innerHTML = `<h2>Economics <span class="muted">(proportional makespan × daily operating cost)</span></h2><table><thead><tr><th>Metric</th><th>Left</th><th>Right</th></tr></thead><tbody>${economicsRows(left, right)}</tbody></table>`;
  $("#machines").innerHTML = `<h2>Machine utilization</h2><table><thead><tr><th>Machine</th><th>Left</th><th>Right</th></tr></thead><tbody>${machineRows(left, right)}</tbody></table>`;
  $("#trucks").innerHTML = `<h2>Trucking</h2><table><thead><tr><th>Metric</th><th>Left</th><th>Right</th></tr></thead><tbody>${truckRows(left, right)}</tbody></table>`;
  $("#landings").innerHTML = `<h2>Landing stockpiles (final / peak)</h2><table><thead><tr><th>Landing</th><th>Left</th><th>Right</th></tr></thead><tbody>${landingRows(left, right)}</tbody></table>`;
  $("#status").textContent = "comparison ready";
}

async function compare() {
  const leftProject = $("#left-project").value;
  const rightProject = $("#right-project").value;
  const leftRun = $("#left-run").value;
  const rightRun = $("#right-run").value;
  if (!leftProject || !rightProject || !leftRun || !rightRun) {
    $("#status").textContent = "Choose two projects and runs.";
    return;
  }
  $("#status").textContent = "loading runs…";
  try {
    const [left, right] = await Promise.all([
      runData(leftProject, leftRun),
      runData(rightProject, rightRun),
    ]);
    render(left, right);
    const url = new URL(location.href);
    url.searchParams.set("left_project", leftProject);
    url.searchParams.set("left_run", leftRun);
    url.searchParams.set("right_project", rightProject);
    url.searchParams.set("right_run", rightRun);
    history.replaceState(null, "", url);
  } catch (error) {
    $("#status").textContent = `Comparison failed: ${error.message}`;
  }
}

$("#left-project").addEventListener("change", (event) => loadRuns("left", event.target.value));
$("#right-project").addEventListener("change", (event) => loadRuns("right", event.target.value));
$("#compare").addEventListener("click", compare);

initSelectors().then(compare).catch((error) => {
  $("#status").textContent = `Load failed: ${error.message}`;
});
