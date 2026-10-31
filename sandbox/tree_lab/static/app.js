import { createViewer } from './viewer.js?v=20261031-camera3';

const state = {
  cases: [],
  currentCase: null,
  currentRun: null,
  currentEvents: null,
  currentSummary: null,
  agentEnabled: false,
  polling: null,
};

const viewer = createViewer(document.getElementById('scene-canvas'), {
  onTime: (t) => updateSceneHud(t),
});

const $ = (sel) => document.querySelector(sel);
const el = (tag, attrs = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') node.className = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) {
    if (child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
};

// Resolve API calls relative to the document so the app also works behind a
// path-prefixing proxy such as JupyterHub/code-server.
const BASE = new URL('.', document.baseURI).pathname;

async function api(path, options = {}) {
  const url = BASE + String(path).replace(/^\/+/, '');
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch { /* keep statusText */ }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

const fmtM3 = (v) => (v === null || v === undefined ? '—' : `${Number(v).toFixed(1)} m³`);
const fmtHours = (s) => (s === null || s === undefined ? '—' : `${(Number(s) / 3600).toFixed(1)} h`);
const pct = (v) => (v === null || v === undefined ? '—' : `${(Number(v) * 100).toFixed(0)}%`);

function setView(name) {
  document.querySelectorAll('#nav button').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === name);
  });
  document.querySelectorAll('.view').forEach((section) => {
    section.classList.toggle('active', section.id === `view-${name}`);
  });
  if (name === 'scene') viewer.resize();
}

async function refreshHealth() {
  try {
    const health = await api('/api/health');
    $('#health-dot').className = 'dot ok';
    $('#health-text').textContent = `fhops ${health.fhops_version} · ${health.cases} cases · agent ${health.agent_enabled ? 'enabled' : 'disabled'}`;
    state.agentEnabled = health.agent_enabled;
    const buildPill = document.getElementById('build-pill');
    if (buildPill) buildPill.textContent = `build ${health.build || 'unknown'}`;
    const quality = health.quality;
    let qualityPill = document.getElementById('quality-pill');
    if (!qualityPill) {
      qualityPill = el('span', { class: 'pill', id: 'quality-pill' });
      $('#health').append(qualityPill);
    }
    if (quality) {
      qualityPill.replaceChildren(
        el('span', { class: `dot ${quality.green ? 'ok' : 'bad'}` }),
        quality.green ? 'quality green' : `quality red: ${(quality.failed || []).join(', ')}`,
      );
    } else {
      qualityPill.replaceChildren(el('span', { class: 'dot warn' }), 'quality: not run');
    }
  } catch (error) {
    $('#health-dot').className = 'dot bad';
    $('#health-text').textContent = `offline: ${error.message}`;
  }
}

function harvestTag(harvest) {
  if (!harvest || harvest.type === 'clear_cut') return el('span', { class: 'tag' }, 'harvest: clear cut');
  const target = Number(harvest.target_basal_area_fraction || 0) * 100;
  return el('span', { class: 'tag' }, `harvest: ${target.toFixed(0)}% BA ${String(harvest.marking_rule || '').replace('_', ' ')}`);
}

function caseCard(item) {
  const stand = item.stand || {};
  const provenance = item.provenance || {};
  const latest = item.latest_run;
  const card = el('div', { class: 'card' });
  card.append(
    el('header', {},
      el('span', { class: 'title' }, item.label),
    ),
    el('div', { class: 'sub' }, `${item.block_id} · ${stand.area_ha ?? '—'} ha · age ${stand.age_years ?? '—'} · ${stand.bec_zone ?? '—'}`),
    el('div', { style: 'margin-top:6px;display:flex;gap:5px;flex-wrap:wrap' },
      el('span', { class: 'tag synthetic' }, `tree list: ${provenance.tree_list || 'unknown'}`),
      el('span', { class: 'tag' }, `review: ${provenance.review_status || 'unknown'}`),
      stand.slope_percent ? el('span', { class: 'tag synthetic' }, `slope ${stand.slope_percent}% concept`) : null,
      stand.operability ? el('span', { class: 'tag' }, `FEMIC: ${stand.operability}`) : null,
      harvestTag(item.harvest),
    ),
    el('dl', {},
      el('dt', {}, 'Trees'), el('dd', {}, stand.tree_count?.toLocaleString?.() ?? '—'),
      el('dt', {}, 'Volume'), el('dd', {}, fmtM3(stand.merchantable_volume_m3)),
      el('dt', {}, 'Volume / ha'), el('dd', {}, stand.volume_per_ha_m3 ? `${Number(stand.volume_per_ha_m3).toFixed(0)} m³/ha` : '—'),
      el('dt', {}, 'Latest run'), el('dd', {}, latest ? `${latest.status} · ${latest.run_id}` : 'never'),
    ),
    el('div', { class: 'actions' },
      el('button', { class: 'btn primary', onclick: () => startRun(item.case_id) }, 'Run'),
      el('button', { class: 'btn', onclick: () => openRun(item.case_id, latest?.run_id) }, 'Run view'),
      el('button', { class: 'btn', onclick: () => openScene(item.case_id, latest?.run_id) }, '3D'),
      el('button', { class: 'btn ghost', onclick: () => validateCase(item.case_id) }, 'Validate'),
      el('button', { class: 'btn ghost', onclick: () => openData(item.case_id) }, 'Data'),
    ),
  );
  return card;
}

async function loadCases() {
  const payload = await api('/api/cases');
  state.cases = payload.cases;
  const grid = $('#cases-grid');
  grid.replaceChildren(...state.cases.map(caseCard));
  if (!state.currentCase && state.cases.length) state.currentCase = state.cases[0].case_id;
  await loadCandidatesSummary();
}

async function loadCandidatesSummary() {
  const payload = await api('/api/agent/candidates');
  const target = $('#candidates-summary');
  if (!payload.candidates.length) {
    target.textContent = 'No candidates yet. Ask the Agent view to generate one.';
    return;
  }
  target.replaceChildren(...payload.candidates.map((candidate) =>
    el('div', { class: 'banner' },
      el('b', {}, candidate.candidate_id), ' — ',
      candidate.valid ? 'schema ok' : `invalid: ${candidate.error || 'see Agent view'}`,
    ),
  ));
}

async function validateCase(caseId) {
  try {
    const report = await api(`/api/cases/${caseId}/validate`, { method: 'POST' });
    if (report.valid) alert(`${caseId}: valid.\nTrees: ${report.inventory?.tree_count ?? '—'}\nBlock: ${report.scenario?.block_ids?.join(', ')}`);
    else alert(`${caseId}: INVALID\n${report.errors.join('\n')}`);
  } catch (error) {
    alert(`Validation failed: ${error.message}`);
  }
}

async function startRun(caseId) {
  try {
    const record = await api(`/api/cases/${caseId}/run`, { method: 'POST' });
    state.currentCase = caseId;
    state.currentRun = record.run_id;
    setView('run');
    renderRun(record);
    pollRun(caseId, record.run_id);
  } catch (error) {
    alert(`Run failed to start: ${error.message}`);
  }
}

function pollRun(caseId, runId) {
  clearInterval(state.polling);
  state.polling = setInterval(async () => {
    try {
      const record = await api(`/api/cases/${caseId}/runs/${runId}`);
      renderRun(record);
      if (record.status !== 'running') {
        clearInterval(state.polling);
        await loadCases();
        if (record.status === 'completed') await openScene(caseId, runId);
      }
    } catch (error) {
      clearInterval(state.polling);
      $('#run-status').textContent = `polling failed: ${error.message}`;
    }
  }, 1200);
}

function machineTimeline(events) {
  const machines = Object.keys(events.machines || {});
  const colors = {
    feller_buncher: 'var(--feller)',
    harvester: 'var(--feller)',
    grapple_skidder: 'var(--skidder)',
    skidder: 'var(--skidder)',
    roadside_processor: 'var(--processor)',
    processor: 'var(--processor)',
    loader: 'var(--loader)',
    cable_yarder: '#c678dd',
  };
  const duration = Math.max(1, events.duration_s || 1);
  const wrap = el('div', {});
  for (const machine of machines) {
    const segments = (events.timeline || []).filter((item) => item.machine === machine);
    const track = el('div', { class: 'tl-track' });
    track.dataset.duration = String(duration);
    for (const segment of segments) {
      const left = (segment.start_s / duration) * 100;
      const width = Math.max(0.15, ((segment.end_s - segment.start_s) / duration) * 100);
      track.append(el('div', {
        class: 'tl-seg',
        title: `${segment.type} ${segment.start_s.toFixed(0)}–${segment.end_s.toFixed(0)} s`,
        style: `left:${left}%;width:${width}%;background:${colors[events.machines[machine].type] || '#888'}`,
      }));
    }
    track.append(el('div', { class: 'tl-playhead' }));
    wrap.append(el('div', { class: 'tl-row' }, el('span', { class: 'id' }, machine), track));
  }
  return wrap;
}

function renderRun(record) {
  $('#run-title').textContent = `${record.case_label || record.case_id}`;
  $('#run-subtitle').textContent = `run ${record.run_id}`;
  const statusDot = record.status === 'completed' ? 'ok' : record.status === 'failed' ? 'bad' : 'warn';
  $('#run-status').replaceChildren(el('span', { class: 'pill' }, el('span', { class: `dot ${statusDot}` }), record.status));

  const body = $('#run-body');
  if (record.status === 'running') {
    body.replaceChildren(el('p', { class: 'lede' }, 'Running fhops tree system and fhops tree scene…'));
    return;
  }
  if (record.status === 'failed') {
    body.replaceChildren(el('div', { class: 'banner bad' }, el('b', {}, 'Run failed'), el('pre', {}, record.error || 'unknown error')));
    return;
  }

  const kpis = record.kpis || {};
  const derived = record.harvest?.derived;
  const harvestBanner = derived
    ? el('div', { class: 'banner ok' },
        el('b', {}, 'Harvest prescription: '),
        `${derived.cut_count} of ${derived.cut_count + derived.residual_count} stems cut` +
        ` · ${(derived.removed_basal_area_fraction * 100).toFixed(1)}% of basal area` +
        ` · ${derived.residual_count} residual standing` +
        ` · rule: ${record.harvest?.prescription?.marking_rule || 'all'}`)
    : null;
  const machineRows = Object.entries(kpis.machine_summaries || {}).map(([id, value]) =>
    el('tr', {},
      el('td', {}, id),
      el('td', { class: 'right' }, fmtHours(value.busy_s)),
      el('td', { class: 'right' }, pct(value.utilisation)),
      el('td', { class: 'right' }, value.events),
    ),
  );
  const commands = (record.commands || []).map((command) => el('pre', {}, `$ ${command.command.join(' ')}\nexit ${command.returncode} · ${command.duration_s}s`));

  body.replaceChildren(
    harvestBanner,
    el('div', { class: 'kpis' },
      kpi('Trees cut', kpis.tree_count ?? '—'),
      kpi('Stand', derived ? derived.cut_count + derived.residual_count : '—'),
      kpi('BA removed', derived ? `${(derived.removed_basal_area_fraction * 100).toFixed(1)}%` : '—'),
      kpi('Residual', derived ? derived.residual_count : '—'),
      kpi('Processed volume', fmtM3(kpis.processed_volume_m3)),
      kpi('Makespan', fmtHours(kpis.makespan_s)),
      kpi('Landing peak', fmtM3(kpis.landing_inventory_max_m3)),
      kpi('Unreachable', kpis.unreachable_count ?? '—'),
      kpi('Events', record.event_count ?? '—'),
    ),
    el('div', { class: 'split' },
      el('div', { class: 'card' },
        el('h3', {}, 'Machine utilisation'),
        el('table', {},
          el('thead', {}, el('tr', {}, el('th', {}, 'Machine'), el('th', { class: 'right' }, 'Busy'), el('th', { class: 'right' }, 'Utilisation'), el('th', { class: 'right' }, 'Events'))),
          el('tbody', {}, ...machineRows),
        ),
      ),
      el('div', { class: 'card' },
        el('h3', {}, 'Warnings and caveats'),
        (record.warnings || []).length
          ? el('div', { class: 'banner warn' }, el('b', {}, 'Warnings'), el('ul', {}, ...record.warnings.map((w) => el('li', {}, w))))
          : el('div', { class: 'banner ok' }, 'No model warnings.'),
        el('ul', { class: 'muted' }, ...(record.caveats || []).slice(0, 4).map((c) => el('li', {}, c))),
      ),
    ),
    el('div', { class: 'card', style: 'margin-top:14px' },
      el('h3', {}, 'Exact commands'),
      el('div', { class: 'muted' }, `fhops ${record.fhops_version} · commit ${(record.fhops_commit || '').slice(0, 12)} · ${record.duration_s}s`),
      ...commands,
    ),
  );

  if (record.artifacts) {
    api(`/api/cases/${record.case_id}/runs/${record.run_id}/events`).then((events) => {
      state.currentEvents = events;
      const container = el('div', { class: 'card', style: 'margin-top:14px' },
        el('h3', {}, 'Machine timeline'),
        machineTimeline(events),
      );
      body.append(container);
    }).catch(() => {});
  }
}

function kpi(label, value) {
  return el('div', { class: 'kpi' }, el('div', { class: 'v' }, value), el('div', { class: 'k' }, label));
}

async function openRun(caseId, runId) {
  if (!runId) { alert('No run yet for this case. Press Run first.'); return; }
  state.currentCase = caseId;
  state.currentRun = runId;
  setView('run');
  try {
    const record = await api(`/api/cases/${caseId}/runs/${runId}`);
    renderRun(record);
    if (record.status === 'running') pollRun(caseId, runId);
  } catch (error) {
    $('#run-body').replaceChildren(el('div', { class: 'banner bad' }, error.message));
  }
}

async function openScene(caseId, runId) {
  if (!runId) { alert('No completed run yet for this case. Press Run first.'); return; }
  state.currentCase = caseId;
  state.currentRun = runId;
  setView('scene');
  $('#scene-title').textContent = `${caseId} · ${runId}`;
  $('#scene-subtitle').textContent = 'loading scene and events…';
  try {
    const [events, summary, residual] = await Promise.all([
      api(`/api/cases/${caseId}/runs/${runId}/events`),
      api(`/api/cases/${caseId}/runs/${runId}/summary`),
      api(`/api/cases/${caseId}/residual`).catch(() => null),
    ]);
    state.currentEvents = events;
    state.currentSummary = summary;
    await viewer.load({
      sceneUrl: `${BASE}api/cases/${caseId}/runs/${runId}/scene.gltf`,
      events,
      summary,
      residual,
    });
    renderMachineCards(events);
    renderTimelineStrip(events);
    const residualNote = residual?.count ? ` · ${residual.count} residual standing` : '';
    $('#scene-subtitle').textContent = `${events.block_id} · ${events.tree_count} cut trees${residualNote} · makespan ${fmtHours(events.makespan_s)} · ${events.rate_model} rates`;
    $('#scene-scrub').value = 0;
    updateSceneHud(0);
  } catch (error) {
    $('#scene-subtitle').textContent = `failed to load scene: ${error.message}`;
  }
}

function renderMachineCards(events) {
  const target = $('#machine-cards');
  target.replaceChildren();
  const labels = { feller_buncher: 'Feller', harvester: 'Harvester', hand_faller: 'Hand faller', grapple_skidder: 'Skidder', skidder: 'Skidder', roadside_processor: 'Processor', processor: 'Processor', loader: 'Loader', cable_yarder: 'Cable yarder' };
  for (const [id, spec] of Object.entries(events.machines || {})) {
    target.append(el('div', { class: 'mcard' },
      el('b', {}, `${labels[spec.type] || spec.type} · ${id}`),
      el('span', { id: `mcard-${id}` }, 'idle'),
    ));
  }
}

function renderTimelineStrip(events) {
  const strip = $('#timeline-strip');
  strip.replaceChildren(machineTimeline(events));
  state.timelinePlayheads = [...strip.querySelectorAll('.tl-playhead')];
  for (const track of strip.querySelectorAll('.tl-track')) {
    track.style.cursor = 'ew-resize';
    track.addEventListener('pointerdown', (event) => {
      const duration = Number(track.dataset.duration) || state.currentEvents?.duration_s || 1;
      const rect = track.getBoundingClientRect();
      const fraction = Math.min(1, Math.max(0, (event.clientX - rect.left) / Math.max(1, rect.width)));
      viewer.pause();
      $('#scene-play').textContent = 'play';
      viewer.seek(fraction * duration);
      updateSceneHud(fraction * duration);
      track.setPointerCapture?.(event.pointerId);
    });
    track.addEventListener('pointermove', (event) => {
      if (!event.buttons) return;
      const duration = Number(track.dataset.duration) || state.currentEvents?.duration_s || 1;
      const rect = track.getBoundingClientRect();
      const fraction = Math.min(1, Math.max(0, (event.clientX - rect.left) / Math.max(1, rect.width)));
      viewer.seek(fraction * duration);
      updateSceneHud(fraction * duration);
    });
  }
}

function updateSceneHud(t) {
  const events = state.currentEvents;
  if (!events) return;
  const duration = Math.max(1, events.duration_s || 1);
  const processed = (events.trees || []).filter((tree) => (tree.processed_s ?? Infinity) <= t).length;
  const volume = (events.trees || [])
    .filter((tree) => (tree.processed_s ?? Infinity) <= t)
    .reduce((sum, tree) => sum + (tree.volume_m3 || 0), 0);
  $('#scene-status').textContent = `T+${fmtClock(t)} · ${processed.toLocaleString()} / ${(events.trees || []).length.toLocaleString()} trees · ${fmtM3(volume)}`;
  const progress = Math.min(100, Math.max(0, (t / duration) * 100));
  $('#scene-bar').firstElementChild.style.width = `${progress}%`;
  $('#scene-scrub').value = Math.round(progress * 10);
  for (const playhead of state.timelinePlayheads || []) playhead.style.left = `${progress}%`;
  const active = viewer.machineStates();
  for (const [id, status] of Object.entries(active)) {
    const node = document.getElementById(`mcard-${id}`);
    if (node) node.textContent = status;
  }
}

function fmtClock(t) {
  const s = Math.max(0, Math.floor(t));
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  return `${days > 0 ? `${days}d ` : ''}${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}

async function openData(caseId) {
  state.currentCase = caseId;
  setView('data');
  $('#data-title').textContent = `Case data · ${caseId}`;
  const body = $('#data-body');
  body.replaceChildren(el('p', { class: 'muted' }, 'loading…'));
  try {
    const data = await api(`/api/cases/${caseId}/data`);
    const validation = data.validation || {};
    const hashes = validation.hashes || {};
    const sample = data.inventory_sample || [];
    const columns = sample.length ? Object.keys(sample[0]) : [];
    body.replaceChildren(
      el('div', { class: validation.valid ? 'banner ok' : 'banner bad' },
        validation.valid ? 'Case validation passed.' : `Case validation failed: ${(validation.errors || []).join('; ')}`),
      el('div', { class: 'split' },
        el('div', { class: 'card' },
          el('h3', {}, 'Provenance'),
          el('dl', {},
            el('dt', {}, 'Tree list'), el('dd', {}, data.manifest.provenance?.tree_list || '—'),
            el('dt', {}, 'Footprint'), el('dd', {}, data.manifest.provenance?.stand_footprint || '—'),
            el('dt', {}, 'Review'), el('dd', {}, data.manifest.provenance?.review_status || '—'),
            el('dt', {}, 'Producer'), el('dd', {}, data.metadata.producer || '—'),
            el('dt', {}, 'Method'), el('dd', {}, data.metadata.method || '—'),
            el('dt', {}, 'CRS'), el('dd', {}, data.metadata.crs || '—'),
            el('dt', {}, 'Trees'), el('dd', {}, data.metadata.tree_count ?? '—'),
          ),
          el('h3', { style: 'margin-top:12px' }, 'Checksums'),
          el('table', {}, el('tbody', {}, ...Object.entries(hashes).map(([key, value]) =>
            el('tr', {}, el('td', {}, key), el('td', { class: 'mono' }, value.slice(0, 32) + '…')),
          ))),
        ),
        el('div', { class: 'card' },
          el('h3', {}, 'Caveats'),
          el('ul', {}, ...(data.manifest.caveats || []).map((c) => el('li', {}, c))),
          el('h3', { style: 'margin-top:12px' }, 'Scenario'),
          el('pre', {}, data.scenario_yaml || ''),
        ),
      ),
      el('div', { class: 'card', style: 'margin-top:14px' },
        el('h3', {}, 'Inventory sample (first 12 rows)'),
        el('div', { class: 'scroll' },
          el('table', {},
            el('thead', {}, el('tr', {}, ...columns.map((column) => el('th', {}, column)))),
            el('tbody', {}, ...sample.map((row) => el('tr', {}, ...columns.map((column) => el('td', {}, row[column]))))),
          ),
        ),
      ),
    );
  } catch (error) {
    body.replaceChildren(el('div', { class: 'banner bad' }, error.message));
  }
}

/* ------------------------------- Agent view ------------------------------- */

const EXAMPLE_PROMPTS = [
  'Create a partial-harvest case with two skidders and 30% of the basal area removed.',
  'Use the MKRF case but lower the processor rate by 20% and add a 2-hour breakdown.',
  'Create a stress case with one truck, small landing capacity, and a steep terrain setting.',
  'Try a cable-assisted variant and explain why the current tree-system model does or does not support it.',
];

function initAgent() {
  $('#agent-examples').replaceChildren(...EXAMPLE_PROMPTS.map((prompt) =>
    el('span', { class: 'chip', onclick: () => { $('#agent-prompt').value = prompt; } }, prompt.slice(0, 46) + '…'),
  ));
  $('#agent-run').addEventListener('click', runAgent);
}

async function refreshAgent() {
  const status = await api('/api/agent/status');
  state.agentEnabled = status.enabled && status.available;
  const banner = $('#agent-banner');
  if (!status.enabled) {
    banner.replaceChildren(el('div', { class: 'banner warn' },
      'Agent bridge is disabled. Restart the app with ', el('code', {}, '--allow-agent'), ' to enable candidate generation.'));
  } else if (!status.available) {
    banner.replaceChildren(el('div', { class: 'banner bad' }, 'opencode CLI was not found on PATH; the console is read-only.'));
  } else {
    const configNote = status.config_model && status.config_model !== status.model
      ? ` (config default: ${status.config_model})`
      : '';
    banner.replaceChildren(el('div', { class: 'banner ok' },
      `Agent ready · opencode ${status.version || '?'} · model ${status.model || 'default'}${configNote} · workspace ${status.workspace}`));
  }
  $('#agent-run').disabled = !state.agentEnabled;
  renderCandidates(status.candidates || []);
}

function renderCandidates(candidates) {
  const target = $('#agent-candidates');
  if (!candidates.length) {
    target.className = 'muted';
    target.textContent = 'No candidates yet.';
    return;
  }
  target.className = '';
  target.replaceChildren(...candidates.map((candidate) =>
    el('div', { class: 'card', style: 'margin-bottom:10px' },
      el('header', {},
        el('span', { class: 'title' }, candidate.candidate_id),
        el('span', { class: 'tag' }, candidate.valid ? 'schema ok' : 'invalid'),
      ),
      candidate.error ? el('div', { class: 'banner bad' }, candidate.error) : null,
      el('div', { class: 'actions' },
        el('button', { class: 'btn', onclick: () => validateCandidate(candidate.candidate_id) }, 'Validate'),
        el('button', { class: 'btn primary', onclick: () => acceptCandidate(candidate.candidate_id) }, 'Accept'),
      ),
    ),
  ));
}

async function runAgent() {
  const message = $('#agent-prompt').value.trim();
  if (!message) return;
  $('#agent-run').disabled = true;
  $('#agent-meta').textContent = 'running opencode…';
  $('#agent-response').replaceChildren(el('p', { class: 'muted' }, 'Waiting for the local agent…'));
  try {
    const result = await api('/api/agent/run', { method: 'POST', body: JSON.stringify({ message }) });
    $('#agent-meta').textContent = `${result.duration_s}s · model ${result.agent?.model || 'default'}`;
    const blocks = [];
    if (result.error) blocks.push(el('div', { class: 'banner bad' }, result.error));
    blocks.push(el('pre', {}, result.response || '(no response)'));
    for (const candidate of result.candidates || []) {
      blocks.push(el('div', { class: candidate.valid ? 'banner ok' : 'banner bad' },
        `${candidate.candidate_id}: ${candidate.valid ? 'validation passed' : 'validation failed'}`,
        candidate.errors?.length ? el('ul', {}, ...candidate.errors.map((e) => el('li', {}, e))) : null,
        candidate.smoke?.ok ? el('div', { class: 'muted' }, `smoke run: ${candidate.smoke.tree_count} trees, ${fmtM3(candidate.smoke.processed_volume_m3)}`) : null,
      ));
    }
    $('#agent-response').replaceChildren(...blocks);
    await refreshAgent();
    await loadCases();
  } catch (error) {
    $('#agent-meta').textContent = '';
    $('#agent-response').replaceChildren(el('div', { class: 'banner bad' }, error.message));
  } finally {
    $('#agent-run').disabled = !state.agentEnabled;
  }
}

async function validateCandidate(candidateId) {
  try {
    const report = await api(`/api/agent/candidates/${candidateId}/validate`, { method: 'POST' });
    alert(report.valid
      ? `${candidateId}: valid.${report.smoke?.ok ? ` Smoke: ${report.smoke.tree_count} trees, ${fmtM3(report.smoke.processed_volume_m3)}.` : ''}`
      : `${candidateId}: INVALID\n${report.errors.join('\n')}`);
  } catch (error) {
    alert(error.message);
  }
}

async function acceptCandidate(candidateId) {
  if (!confirm(`Accept ${candidateId} as a permanent case?`)) return;
  try {
    await api(`/api/agent/candidates/${candidateId}/accept`, { method: 'POST' });
    await refreshAgent();
    await loadCases();
    alert(`${candidateId} accepted. It now appears in the Cases view.`);
  } catch (error) {
    alert(`Accept failed: ${error.message}`);
  }
}

/* ------------------------------- wiring ---------------------------------- */

document.querySelectorAll('#nav button').forEach((button) => {
  button.addEventListener('click', () => setView(button.dataset.view));
});

$('#scene-play').addEventListener('click', () => {
  const playing = viewer.toggle();
  $('#scene-play').textContent = playing ? 'pause' : 'play';
});
$('#scene-reset').addEventListener('click', () => { viewer.reset(); updateSceneHud(0); });
$('#scene-fit').addEventListener('click', () => viewer.fit());
$('#scene-scrub').addEventListener('input', (event) => {
  const duration = state.currentEvents?.duration_s || 1;
  viewer.seek((Number(event.target.value) / 1000) * duration);
});
$('#scene-speed').addEventListener('change', (event) => viewer.setSpeed(Number(event.target.value)));
$('#scene-timeline-toggle').addEventListener('click', () => $('#timeline-strip').classList.toggle('show'));

window.addEventListener('resize', () => viewer.resize());

initAgent();
refreshHealth();
loadCases();
refreshAgent();
setInterval(refreshHealth, 15000);
