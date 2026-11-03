import * as THREE from 'three';
import { GLTFLoader } from './vendor/three/GLTFLoader.js';
import { OrbitControls } from './vendor/three/OrbitControls.js';

const SPECIES_PALETTE = {
  FD: 0x3f7d3f, PL: 0x4f8f4a, SW: 0x2e6b3a, AT: 0x6c9f4a, EP: 0x7aa85a,
  BL: 0x2c5c3a, CW: 0x2f6f4f, HW: 0x3f8f5a, DR: 0x4d7d3a, MB: 0x5a8f4a,
  AC: 0x6a9f4a, W: 0x6f8f5a, BG: 0x4a8a4f, DM: 0x55884a, HM: 0x55884a,
  VB: 0x55884a, MV: 0x55884a, BA: 0x55884a, TW: 0x55884a, PW: 0x55884a,
};

const ROLE_COLORS = {
  feller_buncher: 0xf08a24,
  harvester: 0xf08a24,
  hand_faller: 0xf08a24,
  grapple_skidder: 0x2e86de,
  skidder: 0x2e86de,
  forwarder: 0x2e86de,
  roadside_processor: 0xf1c40f,
  processor: 0xf1c40f,
  loader: 0x27ae60,
  cable_yarder: 0xc678dd,
};
const SKIDDER_COLORS = [0x2e86de, 0x5dade2, 0x85c1e9];
const ROLE_LABELS = {
  feller_buncher: 'FB',
  harvester: 'HV',
  grapple_skidder: 'GS',
  skidder: 'SK',
  forwarder: 'FW',
  roadside_processor: 'P',
  processor: 'P',
  loader: 'L',
  cable_yarder: 'Y',
};
const MACHINE_OFFSETS = { H4: [12, 0], H5: [-12, 0], H6: [0, 12] };
const SWATH_BAND_HEIGHT_M = 24;

function treeBounds(events) {
  const trees = events.trees || [];
  if (!trees.length) return null;
  const xs = trees.map((tree) => Number(tree.x)).filter(Number.isFinite);
  const ys = trees.map((tree) => Number(tree.y)).filter(Number.isFinite);
  if (!xs.length || !ys.length) return null;
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
}

function normalizeLanding(events) {
  const bounds = treeBounds(events);
  const old = events.landing;
  if (!bounds || !old) return;
  const inside = Number(old.x) > bounds.minX && Number(old.x) < bounds.maxX
    && Number(old.y) > bounds.minY && Number(old.y) < bounds.maxY;
  if (!inside) return;
  const next = { x: bounds.maxX - 45, y: bounds.minY - 28 };
  const near = (x, y) => Math.abs(Number(x) - Number(old.x)) < 1.5
    && Math.abs(Number(y) - Number(old.y)) < 1.5;
  for (const event of [...(events.timeline || []), ...(events.truck_events || [])]) {
    if (near(event.x0, event.y0)) { event.x0 = next.x; event.y0 = next.y; }
    if (near(event.x1, event.y1)) { event.x1 = next.x; event.y1 = next.y; }
  }
  events.landing = next;
}

function swathOrder(trees) {
  const valid = trees.filter((tree) => Number.isFinite(Number(tree.x)) && Number.isFinite(Number(tree.y)));
  if (!valid.length) return [];
  const minY = Math.min(...valid.map((tree) => Number(tree.y)));
  const bands = new Map();
  for (const tree of valid) {
    const band = Math.floor((Number(tree.y) - minY) / SWATH_BAND_HEIGHT_M);
    if (!bands.has(band)) bands.set(band, []);
    bands.get(band).push(tree);
  }
  const ordered = [];
  const bandKeys = [...bands.keys()].sort((a, b) => a - b);
  bandKeys.forEach((band, index) => {
    const row = bands.get(band).slice().sort((a, b) => (
      Number(a.x) - Number(b.x) || Number(a.y) - Number(b.y) || String(a.tree_id).localeCompare(String(b.tree_id))
    ));
    if (index % 2) row.reverse();
    ordered.push(...row);
  });
  return ordered;
}

function normalizeFellerSwath(events) {
  if (!events || !Array.isArray(events.timeline) || !Array.isArray(events.trees)) return;
  const feller = events.feller_machine_id || Object.entries(events.machines || {})
    .find(([, machine]) => ['feller_buncher', 'harvester', 'hand_faller'].includes(machine.type))?.[0];
  if (!feller) return;
  const processTypes = new Set(['process', 'fell', 'fall']);
  const fellerSegments = events.timeline
    .filter((segment) => segment.machine === feller)
    .sort((a, b) => a.start_s - b.start_s);
  const processSegments = fellerSegments.filter((segment) => processTypes.has(segment.type));
  if (!processSegments.length || processSegments.length !== events.trees.length) return;
  const ordered = swathOrder(events.trees);
  if (ordered.length !== processSegments.length) return;
  for (let index = 0; index < processSegments.length; index += 1) {
    const segment = processSegments[index];
    const tree = ordered[index];
    const x = Number(tree.x);
    const y = Number(tree.y);
    segment.tree_ids = [tree.tree_id];
    segment.x0 = x; segment.x1 = x; segment.y0 = y; segment.y1 = y;
    if (Number.isFinite(Number(tree.volume_m3))) segment.volume_m3 = Number(tree.volume_m3);
    if (Number.isFinite(Number(tree.logs))) segment.logs = Number(tree.logs);
    tree.processed_s = segment.end_s;
  }
  let previousPoint = null;
  const processSet = new Set(processSegments);
  for (let index = 0; index < fellerSegments.length; index += 1) {
    const segment = fellerSegments[index];
    if (processSet.has(segment)) {
      previousPoint = [Number(segment.x0), Number(segment.y0)];
      continue;
    }
    if (!String(segment.type).startsWith('travel')) continue;
    const next = fellerSegments.slice(index + 1).find((item) => processSet.has(item));
    if (previousPoint) {
      segment.x0 = previousPoint[0]; segment.y0 = previousPoint[1];
    }
    if (next) {
      segment.x1 = Number(next.x0); segment.y1 = Number(next.y0);
    }
  }
}

export function createViewer(container, { onTime } = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0e1214);
  scene.fog = new THREE.Fog(0x0e1214, 900, 2200);

  const camera = new THREE.PerspectiveCamera(52, 1, 0.5, 20000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;

  scene.add(new THREE.HemisphereLight(0xffffff, 0x25302d, 1.5));
  const sun = new THREE.DirectionalLight(0xfff2d8, 2.2);
  sun.position.set(120, 220, 90);
  scene.add(sun);

  let payload = null;
  let duration = 1;
  let currentTime = 0;
  let playing = true;
  let speed = 1;
  let last = performance.now();
  let treeNodes = new Map();
  let machines = {};
  let cards = new Map();
  let timelineByMachine = {};
  let processedTimes = [];
  let cumulativeVolume = [];
  let truckEvents = {};
  let truckSchedules = {};
  let trucks = {};
  let deckCurves = null;
  let decks = {};
  let cableSpec = null;
  let cableYarderId = null;
  let carriage = null;
  let landingPosition = null;
  let roadEndpoints = null;
  let loadedRunKey = null;
  let baseElevation = 0;
  let residualGroup = null;
  let terrain = null;
  let loaded = false;
  let userInteracted = false;
  let blockOutline = null;
  let retainedObstacles = [];
  let retentionClumps = [];
  let machineSpecs = {};
  let routeCache = new WeakMap();

  controls.addEventListener('start', () => { userInteracted = true; });

  function resize() {
    const width = container.clientWidth || window.innerWidth;
    const height = container.clientHeight || window.innerHeight;
    renderer.setSize(width, height, true);
    camera.aspect = width / Math.max(1, height);
    camera.updateProjectionMatrix();
    // The scene view can be created while hidden. Re-fit once the real
    // viewport is known, unless the user has already orbited manually.
    if (loaded && !userInteracted) fitCamera();
  }

  function clearScene() {
    for (const child of [...scene.children]) {
      if (child.isLight) continue;
      scene.remove(child);
    }
    treeNodes = new Map();
    machines = {};
    cards = new Map();
    trucks = {};
    truckEvents = {};
    deckCurves = null;
    decks = {};
    cableSpec = null;
    cableYarderId = null;
    carriage = null;
    landingPosition = null;
    roadEndpoints = null;
    residualGroup = null;
    timelineByMachine = {};
    processedTimes = [];
    cumulativeVolume = [];
    terrain = null;
    blockOutline = null;
    retainedObstacles = [];
    retentionClumps = [];
    machineSpecs = {};
    routeCache = new WeakMap();
    payload = null;
  }

  function terrainHeight(x, y) {
    if (!terrain) return baseElevation;
    if (Array.isArray(terrain.heights) && terrain.heights.length) {
      const bounds = terrain.bounds;
      if (Array.isArray(bounds) && bounds.length === 4) {
        const [minX, minY, maxX, maxY] = bounds.map(Number);
        const res = Math.max(2, Number(terrain.resolution) || 24);
        const fx = Math.max(0, Math.min(res - 1, ((Number(x) - minX) / Math.max(1, maxX - minX)) * (res - 1)));
        const fy = Math.max(0, Math.min(res - 1, ((Number(y) - minY) / Math.max(1, maxY - minY)) * (res - 1)));
        const x0 = Math.floor(fx), y0 = Math.floor(fy);
        const x1 = Math.min(res - 1, x0 + 1), y1 = Math.min(res - 1, y0 + 1);
        const dx = fx - x0, dy = fy - y0;
        const h00 = Number(terrain.heights[y0 * res + x0]) || 0;
        const h10 = Number(terrain.heights[y0 * res + x1]) || 0;
        const h01 = Number(terrain.heights[y1 * res + x0]) || 0;
        const h11 = Number(terrain.heights[y1 * res + x1]) || 0;
        return baseElevation + (h00 * (1 - dx) + h10 * dx) * (1 - dy) + (h01 * (1 - dx) + h11 * dx) * dy;
      }
    }
    const origin = terrain.origin || [0, 0];
    const uphill = terrain.uphill || [0, -1];
    const slope = Number(terrain.slope_percent || 0) / 100;
    const base = Number(terrain.base_m ?? baseElevation);
    return base + slope * ((x - Number(origin[0])) * Number(uphill[0])
      + (y - Number(origin[1])) * Number(uphill[1]));
  }

  function sampleHeight(x, y) {
    return terrainHeight(x, y);
  }

  function segmentAt(machine, t) {
    const segments = timelineByMachine[machine] || [];
    if (!segments.length) return null;
    if (t <= segments[0].start_s) return { segment: segments[0], f: 0 };
    for (const segment of segments) {
      if (t <= segment.end_s) {
        const span = Math.max(0.001, segment.end_s - segment.start_s);
        return { segment, f: Math.max(0, Math.min(1, (t - segment.start_s) / span)) };
      }
    }
    return { segment: segments[segments.length - 1], f: 1 };
  }

  function machineStates() {
    const states = {};
    for (const id of Object.keys(machines)) {
      const state = segmentAt(id, currentTime);
      if (!state) { states[id] = 'idle'; continue; }
      const active = currentTime >= state.segment.start_s && currentTime <= state.segment.end_s;
      states[id] = active ? state.segment.type.replaceAll('_', ' ') : 'idle';
    }
    return states;
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

  function routeAroundObstacles(x0, y0, x1, y1) {
    let best = null;
    let bestDistance = Infinity;
    const dx = x1 - x0;
    const dy = y1 - y0;
    const lengthSq = dx * dx + dy * dy || 1;
    for (const obstacle of retainedObstacles) {
      const t = Math.max(0, Math.min(1, ((obstacle.x - x0) * dx + (obstacle.y - y0) * dy) / lengthSq));
      const px = x0 + dx * t;
      const py = y0 + dy * t;
      const distance = Math.hypot(obstacle.x - px, obstacle.y - py);
      if (distance < obstacle.radius + 4 && distance < bestDistance) {
        best = { obstacle, t, px, py, length: Math.hypot(dx, dy) };
        bestDistance = distance;
      }
    }
    if (!best || bestDistance > best.obstacle.radius + 4) return [[x0, y0], [x1, y1]];
    const normalX = -(dy / Math.max(1, best.length));
    const normalY = dx / Math.max(1, best.length);
    const side = ((x0 - best.obstacle.x) * normalX + (y0 - best.obstacle.y) * normalY) >= 0 ? 1 : -1;
    const offset = best.obstacle.radius + 6;
    const via = [best.obstacle.x + normalX * offset * side, best.obstacle.y + normalY * offset * side];
    return [[x0, y0], via, [x1, y1]];
  }

  function routeGridBounds(x0, y0, x1, y1) {
    let minX = Math.min(x0, x1), maxX = Math.max(x0, x1);
    let minY = Math.min(y0, y1), maxY = Math.max(y0, y1);
    if (Array.isArray(terrain?.bounds) && terrain.bounds.length === 4) {
      minX = Math.min(minX, Number(terrain.bounds[0]));
      minY = Math.min(minY, Number(terrain.bounds[1]));
      maxX = Math.max(maxX, Number(terrain.bounds[2]));
      maxY = Math.max(maxY, Number(terrain.bounds[3]));
    }
    const pad = 20;
    return [minX - pad, minY - pad, maxX + pad, maxY + pad];
  }

  function machineGradeLimit(id) {
    const type = machineSpecs[id]?.type || '';
    if (type.includes('feller') || type.includes('harvester') || type.includes('hand_faller')) return 55;
    if (type.includes('skidder') || type.includes('forwarder') || type.includes('yarder')) return 35;
    return 45;
  }

  function routeSegment(id, segment) {
    if (routeCache.has(segment)) return routeCache.get(segment);
    const x0 = Number(segment.x0), y0 = Number(segment.y0);
    const x1 = Number(segment.x1), y1 = Number(segment.y1);
    if (Math.hypot(x1 - x0, y1 - y0) < 0.5) {
      const direct = [[x0, y0], [x1, y1]];
      routeCache.set(segment, direct);
      return direct;
    }
    if (!terrain || !Array.isArray(terrain.heights) || !terrain.heights.length) {
      const fallback = routeAroundObstacles(x0, y0, x1, y1);
      routeCache.set(segment, fallback);
      return fallback;
    }
    const [minX, minY, maxX, maxY] = routeGridBounds(x0, y0, x1, y1);
    const res = 42;
    const dx = (maxX - minX) / res;
    const dy = (maxY - minY) / res;
    const noGo = retainedObstacles;
    const blocked = (col, row) => {
      const x = minX + (col + 0.5) * dx;
      const y = minY + (row + 0.5) * dy;
      return noGo.some((obstacle) => Math.hypot(obstacle.x - x, obstacle.y - y) < obstacle.radius + 1.5)
        || retentionClumps.some((clump) => pointInPolygon(x, y, clump.polygon || []));
    };
    const cellOf = (x, y) => [
      Math.max(0, Math.min(res - 1, Math.floor((x - minX) / Math.max(1e-9, maxX - minX) * res))),
      Math.max(0, Math.min(res - 1, Math.floor((y - minY) / Math.max(1e-9, maxY - minY) * res))),
    ];
    const [startCol, startRow] = cellOf(x0, y0);
    const [endCol, endRow] = cellOf(x1, y1);
    const key = (col, row) => row * res + col;
    const open = [{ col: startCol, row: startRow, g: 0, f: 0, parent: null }];
    const closed = new Set();
    const best = new Map([[key(startCol, startRow), 0]]);
    const limit = machineGradeLimit(id);
    let found = null;
    while (open.length) {
      open.sort((a, b) => a.f - b.f);
      const current = open.shift();
      const currentKey = key(current.col, current.row);
      if (closed.has(currentKey)) continue;
      closed.add(currentKey);
      if (current.col === endCol && current.row === endRow) { found = current; break; }
      const currentX = minX + (current.col + 0.5) * dx;
      const currentY = minY + (current.row + 0.5) * dy;
      const currentZ = terrainHeight(currentX, currentY);
      for (let dc = -1; dc <= 1; dc += 1) {
        for (let dr = -1; dr <= 1; dr += 1) {
          if (!dc && !dr) continue;
          const col = current.col + dc, row = current.row + dr;
          if (col < 0 || row < 0 || col >= res || row >= res) continue;
          const nextKey = key(col, row);
          if (closed.has(nextKey)) continue;
          if (blocked(col, row) && !(col === endCol && row === endRow)) continue;
          const nextX = minX + (col + 0.5) * dx;
          const nextY = minY + (row + 0.5) * dy;
          const horizontal = Math.hypot(nextX - currentX, nextY - currentY);
          const grade = Math.abs(terrainHeight(nextX, nextY) - currentZ) / Math.max(1e-9, horizontal) * 100;
          if (grade > limit && !(col === endCol && row === endRow)) continue;
          const g = current.g + horizontal * (1 + grade / 100);
          if (g >= (best.get(nextKey) ?? Infinity)) continue;
          const h = Math.hypot(nextX - x1, nextY - y1);
          best.set(nextKey, g);
          open.push({ col, row, g, f: g + h, parent: current });
        }
      }
    }
    if (!found) {
      const fallback = routeAroundObstacles(x0, y0, x1, y1);
      routeCache.set(segment, fallback);
      return fallback;
    }
    const cells = [];
    for (let node = found; node; node = node.parent) cells.push(node);
    cells.reverse();
    const path = [[x0, y0], ...cells.map((node) => [minX + (node.col + 0.5) * dx, minY + (node.row + 0.5) * dy]), [x1, y1]];
    const simplified = [path[0]];
    for (let index = 1; index < path.length - 1; index += 1) {
      const a = simplified[simplified.length - 1], b = path[index], c = path[index + 1];
      const cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
      if (Math.abs(cross) > 0.5) simplified.push(b);
    }
    simplified.push(path[path.length - 1]);
    routeCache.set(segment, simplified);
    return simplified;
  }

  function updateMachines(t) {
    for (const [id, group] of Object.entries(machines)) {
      const state = segmentAt(id, t);
      if (!state) continue;
      const segment = state.segment;
      const path = Array.isArray(segment.path) && segment.path.length > 1
        ? segment.path.map((point) => [Number(point[0]), Number(point[1])])
        : routeSegment(id, segment);
      const point = pathPoint(path, state.f);
      let x = point.x;
      let y = point.y;
      const offset = MACHINE_OFFSETS[id] || [0, 0];
      x += offset[0]; y += offset[1];
      group.position.set(x, sampleHeight(x, y) + 2.8, y);
      const active = t >= segment.start_s && t <= segment.end_s;
      const card = cards.get(id);
      if (card) card.textContent = `${active ? segment.type.replaceAll('_', ' ') : 'idle'}`;
    }
  }

  function updateTrees(t) {
    for (const node of treeNodes.values()) {
      node.visible = (node.userData.processed_s ?? Infinity) > t;
    }
  }

  function buildDeckCurves(events) {
    const machineType = (id) => events.machines?.[id]?.type || '';
    const hasProcessor = Object.values(events.machines || {}).some((machine) =>
      ['roadside_processor', 'processor'].includes(machine.type));
    const changes = [];
    const add = (t, key, delta) => {
      const value = Number(delta);
      if (Number.isFinite(t) && Number.isFinite(value) && Math.abs(value) > 1e-9) changes.push({ t, key, delta: value });
    };
    for (const event of events.timeline || []) {
      const type = machineType(event.machine);
      const volume = Math.abs(Number(event.volume_m3) || 0);
      if (['grapple_skidder', 'skidder', 'forwarder'].includes(type) && event.type === 'unload') {
        add(event.end_s, 'unprocessed', volume);
      } else if (type === 'cable_yarder' && event.type === 'yard') {
        add(event.start_s, 'unprocessed', volume);
      } else if (['roadside_processor', 'processor'].includes(type) && event.type === 'process') {
        add(event.start_s, 'unprocessed', -volume);
        add(event.end_s, 'processed', volume);
      } else if (type === 'loader' && event.type === 'load' && !hasProcessor) {
        add(event.start_s, 'unprocessed', -volume);
      }
    }
    for (const event of events.truck_events || []) {
      if (event.type === 'truck_load' && hasProcessor) {
        add(event.start_s, 'processed', -Math.abs(Number(event.volume_m3) || 0));
      }
    }
    changes.sort((a, b) => a.t - b.t);
    return { changes };
  }

  function deckVolumesAt(t) {
    let unprocessed = 0;
    let processed = 0;
    for (const change of deckCurves?.changes || []) {
      if (change.t > t) break;
      if (change.key === 'unprocessed') unprocessed += change.delta;
      else processed += change.delta;
    }
    return { unprocessed: Math.max(0, unprocessed), processed: Math.max(0, processed) };
  }

  function makeTextSprite(initial, height = 2.5) {
    const canvas = document.createElement('canvas');
    canvas.width = 512; canvas.height = 96;
    const ctx = canvas.getContext('2d');
    const texture = new THREE.CanvasTexture(canvas);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false }));
    // Match the machine-label height and preserve the canvas aspect ratio.
    sprite.scale.set(height * (512 / 96), height, 1);
    const setText = (text) => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#101416dd'; ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#e8eef2'; ctx.font = 'bold 38px system-ui'; ctx.textAlign = 'center';
      ctx.fillText(text, canvas.width / 2, 60);
      texture.needsUpdate = true;
    };
    setText(initial);
    return { sprite, setText };
  }

  function makeDeck(landing, dx, dy, color, label) {
    const group = new THREE.Group();
    const pad = new THREE.Mesh(
      new THREE.CylinderGeometry(14, 14, 0.45, 20),
      new THREE.MeshStandardMaterial({ color: 0x51452c, roughness: 1 }),
    );
    pad.position.y = 0.2;
    group.add(pad);
    const logs = [];
    const material = new THREE.MeshStandardMaterial({ color, roughness: 0.9 });
    for (let row = 0; row < 3; row += 1) {
      for (let index = 0; index < 8; index += 1) {
        const log = new THREE.Mesh(new THREE.CylinderGeometry(0.62, 0.62, 8.4, 7), material);
        log.rotation.z = Math.PI / 2;
        log.position.set((index - 3.5) * 1.35, 1.05 + row * 1.15, (row - 1) * 2.4);
        group.add(log);
        logs.push(log);
      }
    }
    const text = makeTextSprite(`${label} · 0 m³`, 2.5);
    text.sprite.position.set(0, 12, 0);
    scene.add(text.sprite);
    group.position.set(landing.x + dx, sampleHeight(landing.x + dx, landing.y + dy), landing.y + dy);
    group.userData = { logs, label: text, name: label, lastVolume: -1 };
    scene.add(group);
    return group;
  }

  function updateDecks(t) {
    if (!deckCurves) return;
    const volumes = deckVolumesAt(t);
    for (const [key, group] of Object.entries(decks)) {
      const volume = key === 'unprocessed' ? volumes.unprocessed : volumes.processed;
      const ratio = Math.min(1, volume / 40);
      group.visible = volume > 0.1;
      group.userData.logs.forEach((log, index) => {
        log.visible = index < Math.max(1, Math.ceil(ratio * group.userData.logs.length));
      });
      const scaleY = 0.35 + ratio * 0.65;
      group.scale.set(1, scaleY, 1);
      // The label lives in world space, not inside the scaled deck group, so
      // its text aspect ratio and font size never change with deck volume.
      group.userData.label.sprite.visible = group.visible;
      group.userData.label.sprite.position.set(group.position.x, group.position.y + 12, group.position.z);
      const rounded = volume < 10 ? volume.toFixed(1) : volume.toFixed(0);
      if (rounded !== group.userData.lastVolume) {
        group.userData.lastVolume = rounded;
        group.userData.label.setText(`${group.userData.name} · ${rounded} m³`);
      }
    }
  }

  function pathPoint(path, f) {
    let total = 0;
    const lengths = [];
    for (let index = 1; index < path.length; index += 1) {
      const length = Math.hypot(path[index][0] - path[index - 1][0], path[index][1] - path[index - 1][1]);
      lengths.push(length);
      total += length;
    }
    let remaining = Math.max(0, Math.min(1, f)) * total;
    for (let index = 0; index < lengths.length; index += 1) {
      if (remaining <= lengths[index] || index === lengths.length - 1) {
        const u = lengths[index] > 0 ? Math.min(1, remaining / lengths[index]) : 0;
        const a = path[index];
        const b = path[index + 1];
        return {
          x: a[0] + (b[0] - a[0]) * u,
          y: a[1] + (b[1] - a[1]) * u,
          heading: Math.atan2(b[1] - a[1], b[0] - a[0]),
        };
      }
      remaining -= lengths[index];
    }
    return { x: path[0][0], y: path[0][1], heading: 0 };
  }

  function buildTruckSchedules(events) {
    const loads = (events.truck_events || []).filter((event) => event.type === 'truck_load')
      .sort((a, b) => a.start_s - b.start_s);
    const returns = (events.truck_events || []).filter((event) => event.type === 'truck_return')
      .sort((a, b) => a.start_s - b.start_s);
    const unusedReturns = new Set(returns);
    const baseIds = [...new Set(loads.map((load) => load.machine))];
    const fleetSize = Math.max(4, baseIds.length);
    const ids = Array.from({ length: fleetSize }, (_, index) => `T-${String(index + 1).padStart(2, '0')}`);
    const available = ids.map(() => -Infinity);
    const schedules = Object.fromEntries(ids.map((id) => [id, []]));
    for (const load of loads) {
      const ret = returns.find((item) => unusedReturns.has(item)
        && item.machine === load.machine
        && item.start_s >= load.end_s - 1
        && item.start_s <= load.end_s + 2);
      if (ret) unusedReturns.delete(ret);
      const returnEnd = ret?.end_s ?? (load.end_s + 3600);
      let slot = available.findIndex((ready) => ready <= load.start_s);
      if (slot < 0) slot = available.indexOf(Math.min(...available));
      schedules[ids[slot]].push({
        loadStart: Number(load.start_s),
        loadEnd: Number(load.end_s),
        returnEnd,
        volume: Number(load.volume_m3) || 0,
      });
      available[slot] = returnEnd;
    }
    return schedules;
  }

  function updateTrucks(t) {
    const roadY = roadEndpoints ? Number(roadEndpoints[0][1]) : null;
    const exitX = roadEndpoints ? Number(roadEndpoints[1][0]) : null;
    for (const [id, group] of Object.entries(trucks)) {
      const schedule = truckSchedules[id] || [];
      const previous = schedule.filter((item) => item.loadStart <= t).at(-1);
      const home = group.userData.home;
      let x = home[0];
      let y = home[1];
      let status = 'waiting';
      let heading = 0;
      let visible = true;
      if (!previous) {
        group.userData.cargo.visible = false;
      } else if (t <= previous.loadEnd) {
        status = 'loading';
        group.userData.cargo.visible = true;
      } else if (t <= previous.returnEnd) {
        const returnDuration = Math.max(1, previous.returnEnd - previous.loadEnd);
        const path = [
          [home[0], home[1]],
          [home[0], roadY ?? home[1]],
          [exitX ?? home[0] + 150, roadY ?? home[1]],
        ];
        const pathLength = path.slice(1).reduce((sum, point, index) => (
          sum + Math.hypot(point[0] - path[index][0], point[1] - path[index][1])
        ), 0);
        // On-map speed: 10 km/h; the 20 km mill leg is represented by the
        // off-map gap in the truck-return interval.
        const mapTravel = Math.min(returnDuration * 0.45, Math.max(1, pathLength / (10 * 1000 / 3600)));
        // 20 km to the mill, 50 km/h average over the 40 km return trip = 48 min.
        const millTrip = Math.min(returnDuration, 2880);
        const arrival = previous.loadEnd + millTrip;
        const outboundEnd = previous.loadEnd + mapTravel;
        const inboundStart = arrival - mapTravel;
        if (t <= outboundEnd) {
          const point = pathPoint(path, (t - previous.loadEnd) / Math.max(1, mapTravel));
          x = point.x; y = point.y; heading = point.heading;
          status = 'loaded outbound';
          group.userData.cargo.visible = true;
        } else if (t < inboundStart) {
          visible = false;
          status = 'off map';
          group.userData.cargo.visible = false;
        } else if (t <= arrival) {
          const point = pathPoint(path, 1 - (t - inboundStart) / Math.max(1, mapTravel));
          x = point.x; y = point.y; heading = point.heading;
          status = 'returning empty';
          group.userData.cargo.visible = false;
        } else {
          status = 'waiting';
          group.userData.cargo.visible = false;
          if ((group.userData.queueIndex || 0) > 2) visible = false;
        }
      } else {
        group.userData.cargo.visible = false;
        // Keep only the first two empty trucks visible at the landing; the
        // rest remain staged until they are assigned a load.
        if ((group.userData.queueIndex || 0) > 2) visible = false;
      }
      group.visible = visible;
      if (visible) {
        group.position.set(x, sampleHeight(x, y) + 1.8, y);
        group.rotation.y = heading;
      }
      group.userData.status = status;
    }
  }

  function updateCarriage(t) {
    if (!carriage || !cableSpec) return;
    const yarderId = cableYarderId;
    const state = yarderId ? segmentAt(yarderId, t) : null;
    if (!state || state.segment.type !== 'yard') {
      carriage.visible = false;
      return;
    }
    const f = state.f;
    let u;
    if (f < 0.45) u = f / 0.45;
    else if (f < 0.55) u = 1;
    else u = Math.max(0, (1 - f) / 0.45);
    const yarder = cableSpec.yarder;
    const spar = cableSpec.spar;
    const x = yarder.x + (spar.x - yarder.x) * u;
    const y = yarder.y + (spar.y - yarder.y) * u;
    const lineY = cableSpec.yarderY + (cableSpec.sparY - cableSpec.yarderY) * u;
    carriage.visible = true;
    carriage.position.set(x, lineY - 2.4, y);
    carriage.userData.loaded.visible = u > 0.12 && u < 0.96;
  }

  function setTime(t) {
    currentTime = Math.max(0, Math.min(duration, t));
    updateMachines(currentTime);
    updateTrucks(currentTime);
    updateDecks(currentTime);
    updateCarriage(currentTime);
    updateTrees(currentTime);
    if (onTime) onTime(currentTime);
  }

  function makeMachine(id, color, label) {
    const group = new THREE.Group();
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(4.2, 3.0, 5.4),
      new THREE.MeshStandardMaterial({ color, roughness: 0.6, metalness: 0.1 }),
    );
    body.position.y = 1.5;
    group.add(body);
    const cab = new THREE.Mesh(
      new THREE.BoxGeometry(2.0, 1.8, 2.0),
      new THREE.MeshStandardMaterial({ color: 0xe8eef2, roughness: 0.4 }),
    );
    cab.position.set(0, 3.1, -0.8);
    group.add(cab);
    const canvas = document.createElement('canvas');
    canvas.width = 256; canvas.height = 64;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#101416cc'; ctx.fillRect(0, 0, 256, 64);
    ctx.fillStyle = '#e8eef2'; ctx.font = 'bold 30px system-ui'; ctx.fillText(label, 8, 42);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false }));
    sprite.position.set(0, 7.0, 0); sprite.scale.set(10, 2.5, 1);
    group.add(sprite);
    const beaconMat = new THREE.MeshBasicMaterial({ color });
    const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 16, 6), beaconMat);
    beam.position.y = 13;
    group.add(beam);
    const beacon = new THREE.Mesh(new THREE.SphereGeometry(1.2, 14, 10), beaconMat);
    beacon.position.y = 21;
    group.add(beacon);
    group.scale.setScalar(1.1);
    group.userData.id = id;
    scene.add(group);
    machines[id] = group;
  }

  function makeTruck(id, index, landing) {
    const group = new THREE.Group();
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(3.2, 2.2, 6.0),
      new THREE.MeshStandardMaterial({ color: 0xd6b45a, roughness: 0.7 }),
    );
    body.position.y = 1.7;
    group.add(body);
    const cab = new THREE.Mesh(
      new THREE.BoxGeometry(2.1, 2.0, 2.0),
      new THREE.MeshStandardMaterial({ color: 0xe8eef2, roughness: 0.5 }),
    );
    cab.position.set(0, 3.2, -2.4);
    group.add(cab);
    const cargo = new THREE.Group();
    const cargoMat = new THREE.MeshStandardMaterial({ color: 0x7d5a36, roughness: 0.95 });
    for (let row = 0; row < 2; row += 1) {
      for (let logIndex = 0; logIndex < 3; logIndex += 1) {
        const log = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 4.8, 7), cargoMat);
        log.rotation.z = Math.PI / 2;
        log.position.set((logIndex - 1) * 0.85, 2.9 + row * 0.75, -0.4);
        cargo.add(log);
      }
    }
    cargo.visible = false;
    group.add(cargo);
    const canvas = document.createElement('canvas');
    canvas.width = 256; canvas.height = 64;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#101416cc'; ctx.fillRect(0, 0, 256, 64);
    ctx.fillStyle = '#e8eef2'; ctx.font = 'bold 28px system-ui'; ctx.fillText(id, 8, 42);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false }));
    sprite.position.set(0, 7, 0); sprite.scale.set(8, 2, 1);
    group.add(sprite);
    const home = [landing.x + (index - 1) * 8, landing.y];
    group.scale.setScalar(1.7);
    group.userData = { home, cargo, status: 'waiting', id, queueIndex: index };
    group.position.set(home[0], sampleHeight(home[0], home[1]) + 1.8, home[1]);
    scene.add(group);
    trucks[id] = group;
  }

  function addRetentionClumps(clumps) {
    if (!Array.isArray(clumps) || !clumps.length) return;
    const group = new THREE.Group();
    group.name = "retention_clumps";
    for (const clump of clumps) {
      const polygon = clump.polygon || [];
      if (polygon.length < 3) continue;
      const color = clump.kind === "riparian" ? 0x4a9fd8 : 0x2fbfb0;
      const material = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: clump.kind === "riparian" ? 0.22 : 0.16,
        side: THREE.DoubleSide,
        depthTest: false,
        depthWrite: false,
      });
      const shape = new THREE.Shape();
      polygon.forEach(([x, y], index) => {
        if (index === 0) shape.moveTo(Number(x), Number(y)); else shape.lineTo(Number(x), Number(y));
      });
      const geometry = new THREE.ShapeGeometry(shape);
      geometry.rotateX(Math.PI / 2);
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.y = sampleHeight(polygon[0][0], polygon[0][1]) + 0.8;
      mesh.renderOrder = 3;
      group.add(mesh);
      const points = polygon.map(([x, y]) => new THREE.Vector3(Number(x), sampleHeight(Number(x), Number(y)) + 1.0, Number(y)));
      const outline = new THREE.LineLoop(
        new THREE.BufferGeometry().setFromPoints(points),
        new THREE.LineBasicMaterial({
          color: clump.kind === "riparian" ? 0x9fd8ff : 0x8ff0e5,
          depthTest: false,
        }),
      );
      outline.renderOrder = 4;
      group.add(outline);

      const cx = polygon.reduce((sum, point) => sum + Number(point[0]), 0) / polygon.length;
      const cy = polygon.reduce((sum, point) => sum + Number(point[1]), 0) / polygon.length;
      const labelCanvas = document.createElement('canvas');
      labelCanvas.width = 512;
      labelCanvas.height = 96;
      const labelCtx = labelCanvas.getContext('2d');
      labelCtx.fillStyle = 'rgba(16,20,22,0.82)';
      labelCtx.fillRect(0, 0, 512, 96);
      labelCtx.fillStyle = clump.kind === "riparian" ? '#b9e1ff' : '#8ff0e5';
      labelCtx.font = 'bold 30px system-ui';
      labelCtx.fillText(String(clump.label || clump.kind || 'retention clump').slice(0, 34), 12, 58);
      const label = new THREE.Sprite(new THREE.SpriteMaterial({
        map: new THREE.CanvasTexture(labelCanvas),
        depthTest: false,
        transparent: true,
      }));
      label.position.set(cx, sampleHeight(cx, cy) + 14, cy);
      label.scale.set(42, 7.9, 1);
      label.renderOrder = 10;
      group.add(label);
    }
    scene.add(group);
  }

  function addResidualTrees(payload) {
    if (!payload || !Array.isArray(payload.trees) || !payload.trees.length) return;
    const group = new THREE.Group();
    group.name = 'residual_trees';
    const trunkGeo = new THREE.CylinderGeometry(0.16, 0.22, 1, 5);
    const crownGeo = new THREE.ConeGeometry(1, 1, 8);
    const ringGeo = new THREE.RingGeometry(1, 1.35, 14);
    const trunkMat = new THREE.MeshStandardMaterial({ color: 0x5a4632, roughness: 0.9 });
    // Bright teal and a ground ring keep leave trees readable against the
    // darker harvested stand at the replay camera scale.
    const crownMat = new THREE.MeshStandardMaterial({
      color: 0x2fe0c8,
      emissive: 0x0d5f58,
      emissiveIntensity: 0.75,
      roughness: 0.6,
      metalness: 0.05,
      transparent: true,
      opacity: 0.82,
      depthTest: false,
      depthWrite: false,
    });
    const markerMat = new THREE.MeshBasicMaterial({
      color: 0x7dfff0,
      transparent: true,
      opacity: 0.95,
      depthTest: false,
      depthWrite: false,
    });
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x7dfff0,
      transparent: true,
      opacity: 0.85,
      side: THREE.DoubleSide,
      depthTest: false,
      depthWrite: false,
    });
    for (const tree of payload.trees) {
      const height = Math.max(6, Number(tree.height_m) || 20);
      const dbh = Math.max(0.1, (Number(tree.dbh_cm) || 30) / 100);
      const crownRadius = Math.max(2.5, Number(tree.crown_radius_m) || dbh * 3);
      const x = Number(tree.x);
      const y = Number(tree.y);
      const base = sampleHeight(x, y);
      const trunk = new THREE.Mesh(trunkGeo, trunkMat);
      trunk.scale.set(dbh * 1.5, height * 0.48, dbh * 1.5);
      trunk.position.set(x, base + height * 0.24, y);
      const crown = new THREE.Mesh(crownGeo, crownMat);
      crown.scale.set(crownRadius * 1.55, height * 0.9, crownRadius * 1.55);
      crown.position.set(x, base + height * 0.55, y);
      crown.renderOrder = 8;
      const marker = new THREE.Mesh(
        new THREE.CylinderGeometry(1.15, 1.5, 8.0, 8),
        markerMat,
      );
      marker.position.set(x, base + 4.0, y);
      marker.renderOrder = 9;
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.rotation.x = -Math.PI / 2;
      ring.scale.setScalar(Math.max(2.5, crownRadius * 1.8));
      ring.position.set(x, base + 0.25, y);
      ring.renderOrder = 9;
      group.add(trunk, crown, marker, ring);
    }
    residualGroup = group;
    scene.add(group);
  }

  function applyTerrain(root) {
    if (!terrain) return;
    const bounds = terrain.bounds;
    if (!Array.isArray(bounds) || bounds.length !== 4) return;
    const [minx, miny, maxx, maxy] = bounds.map(Number);
    const width = Math.max(1, maxx - minx);
    const height = Math.max(1, maxy - miny);

    for (const child of [...root.children]) {
      if (child.name === 'ground') child.parent?.remove(child);
    }

    const geometry = new THREE.PlaneGeometry(width, height, 32, 32);
    geometry.rotateX(-Math.PI / 2);
    const mesh = new THREE.Mesh(
      geometry,
      new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 1.0, metalness: 0.0, vertexColors: true }),
    );
    mesh.name = 'terrain';
    mesh.position.set((minx + maxx) / 2, 0, (miny + maxy) / 2);
    const position = geometry.attributes.position;
    let minHeight = Infinity;
    let maxHeight = -Infinity;
    for (let index = 0; index < position.count; index += 1) {
      const x = mesh.position.x + position.getX(index);
      const z = mesh.position.z + position.getZ(index);
      const y = terrainHeight(x, z);
      position.setY(index, y);
      minHeight = Math.min(minHeight, y);
      maxHeight = Math.max(maxHeight, y);
    }
    const colors = [];
    const span = Math.max(1, maxHeight - minHeight);
    for (let index = 0; index < position.count; index += 1) {
      const f = Math.max(0, Math.min(1, (position.getY(index) - minHeight) / span));
      // Low ground is dark green; high ground warms toward dry olive/brown.
      colors.push(0.18 + f * 0.42, 0.30 + f * 0.28, 0.16 + f * 0.12);
    }
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    position.needsUpdate = true;
    geometry.computeVertexNormals();
    scene.add(mesh);
    const wireframe = new THREE.Mesh(
      geometry.clone(),
      new THREE.MeshBasicMaterial({ color: 0x1b2b24, wireframe: true, transparent: true, opacity: 0.22 }),
    );
    wireframe.position.copy(mesh.position);
    wireframe.name = 'terrain_wireframe';
    scene.add(wireframe);

    for (const node of treeNodes.values()) {
      const x = node.position.x;
      const z = node.position.z;
      node.position.y = terrainHeight(x, z);
    }
  }

  function addRoad(events) {
    const landing = events.landing;
    if (!landing) return;
    const roadHeight = (x, y) => sampleHeight(x, y) + 0.9;
    const halfWidth = 5.5;
    const material = new THREE.MeshStandardMaterial({
      color: 0x66685a,
      roughness: 0.95,
      side: THREE.DoubleSide,
    });

    function addRoadRibbon(points) {
      if (!Array.isArray(points) || points.length < 2) return;
      const positions = [];
      const indices = [];
      for (let index = 0; index < points.length; index += 1) {
        const [x, y] = points[index].map(Number);
        const before = points[Math.max(0, index - 1)];
        const after = points[Math.min(points.length - 1, index + 1)];
        const dx = Number(after[0]) - Number(before[0]);
        const dy = Number(after[1]) - Number(before[1]);
        const length = Math.hypot(dx, dy) || 1;
        const nx = -dy / length;
        const ny = dx / length;
        positions.push(x + nx * halfWidth, roadHeight(x + nx * halfWidth, y + ny * halfWidth), y + ny * halfWidth);
        positions.push(x - nx * halfWidth, roadHeight(x - nx * halfWidth, y - ny * halfWidth), y - ny * halfWidth);
        if (index < points.length - 1) {
          const offset = index * 2;
          indices.push(offset, offset + 2, offset + 1, offset + 1, offset + 2, offset + 3);
        }
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
      geometry.setIndex(indices);
      geometry.computeVertexNormals();
      const road = new THREE.Mesh(geometry, material);
      road.name = 'block_road';
      scene.add(road);
    }

    const authored = Array.isArray(events.road_segments)
      ? events.road_segments.filter((segment) => Array.isArray(segment.points) && segment.points.length >= 2)
      : [];
    let roadPoints = [];
    if (authored.length) {
      for (const segment of authored) addRoadRibbon(segment.points);
      const longest = authored.reduce(
        (best, segment) => (segment.points.length > best.points.length ? segment : best),
        authored[0],
      );
      roadPoints = longest.points.map(([x, y]) => [Number(x), Number(y)]);
      roadEndpoints = [roadPoints[0], roadPoints[roadPoints.length - 1]];
    } else {
      const bounds = treeBounds(events);
      if (!bounds) return;
      const roadY = Math.min(Number(landing.y), bounds.minY - 12);
      const left = bounds.minX - 60;
      const right = bounds.maxX + 60;
      roadPoints = [[left, roadY], [right, roadY]];
      roadEndpoints = roadPoints;
      addRoadRibbon(roadPoints);
    }

    const roadPointList = authored.length
      ? authored.flatMap((segment) => segment.points)
      : roadPoints;
    const landingChoices = Array.isArray(events.landings) && events.landings.length
      ? events.landings
      : [{ id: "landing-main", x: landing.x, y: landing.y }];
    landingChoices.forEach((choice, index) => {
      const lx = Number(choice.x);
      const ly = Number(choice.y);
      let nearest = roadPointList[0] || [lx, ly];
      let nearestDistance = Infinity;
      for (const point of roadPointList) {
        const distance = Math.hypot(Number(point[0]) - lx, Number(point[1]) - ly);
        if (distance < nearestDistance) {
          nearest = point;
          nearestDistance = distance;
        }
      }
      const spur = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(Number(nearest[0]), roadHeight(Number(nearest[0]), Number(nearest[1])), Number(nearest[1])),
          new THREE.Vector3(lx, roadHeight(lx, ly), ly),
        ]),
        new THREE.LineBasicMaterial({ color: 0xd8c58a, transparent: true, opacity: 0.9 }),
      );
      spur.name = 'landing_spur';
      scene.add(spur);
      const pad = new THREE.Mesh(
        new THREE.CircleGeometry(index === 0 ? 22 : 16, 32),
        new THREE.MeshStandardMaterial({ color: 0x8b876e, roughness: 0.95, side: THREE.DoubleSide }),
      );
      pad.rotation.x = -Math.PI / 2;
      pad.position.set(lx, sampleHeight(lx, ly) + 0.5, ly);
      pad.name = 'landing_pad';
      scene.add(pad);
      const label = makeTextSprite(index === 0 ? 'landing' : String(choice.id || `landing ${index + 1}`), 2.2);
      label.sprite.position.set(lx, sampleHeight(lx, ly) + (index === 0 ? 16 : 12), ly);
      scene.add(label.sprite);
    });
  }

  function addCable(cable) {
    if (!cable || !cable.yarder || !cable.spar) return;
    const yarder = cable.yarder;
    const spar = cable.spar;
    const yarderY = terrainHeight(Number(yarder.x), Number(yarder.y)) + 8.0;
    const sparHeight = Number(cable.spar_height_m || 42.0);
    const sparY = terrainHeight(Number(spar.x), Number(spar.y)) + sparHeight;
    const points = [
      new THREE.Vector3(Number(yarder.x), yarderY, Number(yarder.y)),
      new THREE.Vector3(Number(spar.x), sparY, Number(spar.y)),
    ];
    const cableLine = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: 0xc678dd, transparent: true, opacity: 0.9 }),
    );
    cableLine.name = 'cable_skyline';
    scene.add(cableLine);

    const sparBase = terrainHeight(Number(spar.x), Number(spar.y));
    const sparTrunk = new THREE.Mesh(
      new THREE.CylinderGeometry(0.7, 1.4, sparHeight, 8),
      new THREE.MeshStandardMaterial({ color: 0x5a4632, roughness: 1.0 }),
    );
    sparTrunk.position.set(Number(spar.x), sparBase + sparHeight / 2, Number(spar.y));
    sparTrunk.name = 'cable_spar';
    scene.add(sparTrunk);
    const crown = new THREE.Mesh(
      new THREE.ConeGeometry(4.0, 10.0, 7),
      new THREE.MeshStandardMaterial({ color: 0x2f7f78, roughness: 0.95 }),
    );
    crown.position.set(Number(spar.x), sparBase + sparHeight + 4.0, Number(spar.y));
    crown.name = 'cable_spar_crown';
    scene.add(crown);

    cableSpec = {
      yarder: { x: Number(yarder.x), y: Number(yarder.y) },
      spar: { x: Number(spar.x), y: Number(spar.y) },
      yarderY,
      sparY,
    };
    cableYarderId = Object.keys(machines).find((id) => id.startsWith('Y')) || null;
    const carriageGroup = new THREE.Group();
    const carriageBody = new THREE.Mesh(
      new THREE.BoxGeometry(2.4, 1.5, 2.0),
      new THREE.MeshStandardMaterial({ color: 0xffcc33, roughness: 0.35, metalness: 0.25 }),
    );
    carriageGroup.add(carriageBody);
    const hanger = new THREE.Mesh(
      new THREE.CylinderGeometry(0.08, 0.08, 2.4, 5),
      new THREE.MeshStandardMaterial({ color: 0x8899a0, roughness: 0.5 }),
    );
    hanger.position.y = 1.7;
    carriageGroup.add(hanger);
    const loaded = new THREE.Group();
    const logMat = new THREE.MeshStandardMaterial({ color: 0x7d5a36, roughness: 0.95 });
    for (let index = 0; index < 3; index += 1) {
      const log = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 3.8, 6), logMat);
      log.rotation.z = Math.PI / 2;
      log.position.set(0, -1.1, (index - 1) * 0.55);
      loaded.add(log);
    }
    carriageGroup.add(loaded);
    carriageGroup.userData.loaded = loaded;
    carriageGroup.visible = false;
    carriage = carriageGroup;
    scene.add(carriageGroup);
  }

  function addBlockOutline(outline) {
    if (!Array.isArray(outline) || outline.length < 3) return;
    const points = outline.map(([x, y]) => new THREE.Vector3(
      Number(x),
      terrainHeight(Number(x), Number(y)) + 0.8,
      Number(y),
    ));
    const line = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color: 0xf08a24, transparent: true, opacity: 0.9 }),
    );
    line.name = 'block_outline';
    scene.add(line);
  }

  function load(payloadArg) {
    const { sceneUrl, events, residual } = payloadArg;
    normalizeLanding(events);
    normalizeFellerSwath(events);
    const runKey = `${sceneUrl}`;
    if (loadedRunKey === runKey) {
      payload = events;
      duration = events.duration_s || 1;
      setTime(0);
      return Promise.resolve();
    }
    loadedRunKey = runKey;
    clearScene();
    landingPosition = events.landing || null;
    loaded = false;
    payload = events;
    duration = events.duration_s || 1;
    terrain = events.terrain || null;
    blockOutline = Array.isArray(events.block_outline) ? events.block_outline : null;

    return new Promise((resolve, reject) => {
      new GLTFLoader().load(sceneUrl, (gltf) => {
        const root = gltf.scene;
        scene.add(root);
        const removeObjects = [];
        root.traverse((object) => {
          if (object.name === 'machine_path' || object.name.startsWith('log')) removeObjects.push(object);
          if (object.isMesh && object.material?.name?.startsWith('crown:')) {
            const code = object.material.name.slice(6);
            const hex = SPECIES_PALETTE[code.toUpperCase()];
            if (hex !== undefined) object.material.color.setHex(hex);
          }
          if (object.userData?.tree_id) treeNodes.set(object.userData.tree_id, object);
        });
        removeObjects.forEach((object) => object.parent?.remove(object));

        if (treeNodes.size) {
          baseElevation = Math.min(...[...treeNodes.values()].map((node) => node.position.y));
        }
        if (terrain) {
          const heights = Array.isArray(terrain.heights) ? terrain.heights : [];
          const minimumHeight = Number.isFinite(Number(terrain.source_min_height))
            ? Number(terrain.source_min_height)
            : heights.length
              ? Math.min(...heights.map((value) => Number(value) || 0))
              : 0;
          baseElevation = Number(terrain.base_m ?? (baseElevation - minimumHeight));
          applyTerrain(root);
        }

        const spec = { ...events.machines };
        machineSpecs = { ...spec };
        const typeCounts = {};
        let skidderIndex = 0;
        for (const [id, machine] of Object.entries(spec)) {
          const type = machine.type;
          const color = type === 'grapple_skidder' || type === 'skidder'
            ? SKIDDER_COLORS[skidderIndex++ % SKIDDER_COLORS.length]
            : (ROLE_COLORS[type] ?? 0xd9d9d9);
          typeCounts[type] = (typeCounts[type] || 0) + 1;
          makeMachine(id, color, `${ROLE_LABELS[type] || type}${typeCounts[type]}`);
          const slot = document.getElementById(`mcard-${id}`);
          if (slot) cards.set(id, slot);
        }

        // Cable runs do not have a trucking model. Use the loader cycles to
        // give the cable case the same visible landing → road edge → landing truck
        // loop without changing the simulation output.
        if (!(events.truck_events || []).length) {
          const loaderId = Object.entries(events.machines || {})
            .find(([, machine]) => machine.type === 'loader')?.[0];
          const loaderLoads = (events.timeline || [])
            .filter((event) => event.machine === loaderId && event.type === 'load')
            .sort((a, b) => a.start_s - b.start_s);
          if (loaderLoads.length) {
            let available = 0;
            const visualTruckEvents = [];
            for (const load of loaderLoads) {
              const start = Math.max(load.start_s, available);
              const end = Math.max(load.end_s, start + Math.max(1, load.end_s - load.start_s));
              visualTruckEvents.push({
                machine: 'T-01', type: 'truck_load', start_s: start, end_s: end,
                x0: events.landing.x, y0: events.landing.y, x1: events.landing.x, y1: events.landing.y,
                volume_m3: Number(load.volume_m3) || 0,
              });
              const returnEnd = end + 3600;
              visualTruckEvents.push({
                machine: 'T-01', type: 'truck_return', start_s: end, end_s: returnEnd,
                x0: events.landing.x, y0: events.landing.y, x1: events.landing.x, y1: events.landing.y,
                volume_m3: Number(load.volume_m3) || 0,
              });
              available = returnEnd;
            }
            events.truck_events = visualTruckEvents;
            events.truck_summary = { truck_count: 1 };
          }
        }
        for (const event of events.truck_events || []) {
          (truckEvents[event.machine] ||= []).push(event);
        }
        truckSchedules = buildTruckSchedules(events);
        const truckIds = Object.keys(truckSchedules).sort();
        truckIds.forEach((id, index) => makeTruck(id, index + 1, events.landing));

        timelineByMachine = {};
        for (const item of events.timeline || []) (timelineByMachine[item.machine] ||= []).push(item);
        for (const list of Object.values(timelineByMachine)) list.sort((a, b) => a.start_s - b.start_s);

        for (const [id, node] of treeNodes) {
          const record = (events.trees || []).find((tree) => tree.tree_id === id);
          if (record) node.userData.processed_s = record.processed_s;
        }
        const sorted = [...(events.trees || [])].sort((a, b) => a.processed_s - b.processed_s);
        processedTimes = sorted.map((tree) => tree.processed_s);
        cumulativeVolume = [];
        let sum = 0;
        for (const tree of sorted) { sum += tree.volume_m3 || 0; cumulativeVolume.push(sum); }

        addResidualTrees(residual);
        retentionClumps = residual?.clumps || [];
        addRetentionClumps(retentionClumps);
        retainedObstacles = (residual?.trees || []).map((tree) => ({
          x: Number(tree.x), y: Number(tree.y), radius: Math.max(2, (Number(tree.crown_radius_m) || 3) * 0.55),
        }));
        addRoad(events);

        if (events.landing) {
          const ring = new THREE.Mesh(
            new THREE.RingGeometry(6.0, 8.0, 44),
            new THREE.MeshBasicMaterial({ color: 0x27ae60, side: THREE.DoubleSide, transparent: true, opacity: 0.85 }),
          );
          ring.rotation.x = -Math.PI / 2;
          ring.position.set(events.landing.x, sampleHeight(events.landing.x, events.landing.y) + 0.4, events.landing.y);
          scene.add(ring);
        }

        deckCurves = buildDeckCurves(events);
        if (events.landing) {
          decks.unprocessed = makeDeck(events.landing, -52, 62, 0x7d5a36, 'unprocessed deck');
          decks.processed = makeDeck(events.landing, 28, 62, 0xc9a36a, 'processed log deck');
          const hasProcessor = Object.values(events.machines || {}).some((machine) =>
            ['roadside_processor', 'processor'].includes(machine.type));
          if (hasProcessor) {
            const flowStart = new THREE.Vector3(
              events.landing.x - 52,
              sampleHeight(events.landing.x - 52, events.landing.y + 62) + 2.5,
              events.landing.y + 62,
            );
            const flowEnd = new THREE.Vector3(
              events.landing.x + 28,
              sampleHeight(events.landing.x + 28, events.landing.y + 62) + 2.5,
              events.landing.y + 62,
            );
            const flow = new THREE.ArrowHelper(
              flowEnd.clone().sub(flowStart).normalize(),
              flowStart,
              flowStart.distanceTo(flowEnd),
              0xf1c40f,
              12,
              7,
            );
            flow.name = 'landing_flow';
            scene.add(flow);
          }
        }

        addCable(events.cable);
        addBlockOutline(events.block_outline);

        setTime(0);
        loaded = true;
        fitCamera();
        requestAnimationFrame(() => {
          resize();
          fitCamera();
        });
        resolve();
      }, undefined, (error) => reject(error));
    });
  }

  function fitCamera() {
    // Frame the block footprint, not the full scene box (which includes
    // machine beacons and tall tree crowns). The orbit target is the
    // area-weighted block centroid at ground level.
    const outline = (blockOutline || []).filter((point) => Array.isArray(point) && point.length >= 2);
    let points = outline.map(([x, y]) => [Number(x), Number(y)]).filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
    if (!points.length) {
      points = [...treeNodes.values()].map((node) => [node.position.x, node.position.z]);
    }
    if (landingPosition) points.push([Number(landingPosition.x), Number(landingPosition.y)]);
    if (roadEndpoints) points.push(...roadEndpoints);
    if (!points.length) {
      const fallback = new THREE.Box3().setFromObject(scene);
      if (fallback.isEmpty()) return;
      const center = fallback.getCenter(new THREE.Vector3());
      points = [[center.x, center.z]];
    }
    let cx;
    let cy;
    if (outline.length >= 3) {
      let twiceArea = 0;
      let sx = 0;
      let sy = 0;
      for (let i = 0; i < outline.length; i++) {
        const [x1, y1] = outline[i];
        const [x2, y2] = outline[(i + 1) % outline.length];
        const cross = Number(x1) * Number(y2) - Number(x2) * Number(y1);
        twiceArea += cross;
        sx += (Number(x1) + Number(x2)) * cross;
        sy += (Number(y1) + Number(y2)) * cross;
      }
      if (Math.abs(twiceArea) > 1e-9) {
        cx = sx / (3 * twiceArea);
        cy = sy / (3 * twiceArea);
      }
    }
    if (!Number.isFinite(cx) || !Number.isFinite(cy)) {
      const xs = points.map(([x]) => x);
      const ys = points.map(([, y]) => y);
      cx = (Math.min(...xs) + Math.max(...xs)) / 2;
      cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    }
    const groundY = terrainHeight(cx, cy);
    let radius = 0;
    for (const [x, y] of points) {
      radius = Math.max(radius, Math.hypot(x - cx, y - cy));
    }
    radius = Math.max(radius, 10) * 1.18;
    const sceneBox = new THREE.Box3().setFromObject(scene);
    const maxHeight = Math.max(20, Number.isFinite(sceneBox.max.y) ? sceneBox.max.y - groundY : 40);
    const target = new THREE.Vector3(cx, groundY, cy);
    const vFov = THREE.MathUtils.degToRad(camera.fov);
    const hFov = 2 * Math.atan(Math.tan(vFov / 2) * Math.max(0.1, camera.aspect));
    const fitFov = Math.min(vFov, hFov);
    const distance = Math.max(
      radius / Math.sin(fitFov / 2),
      maxHeight / (2 * Math.tan(vFov / 2)),
    ) * 1.15;
    const elevation = THREE.MathUtils.degToRad(50);
    const azimuth = THREE.MathUtils.degToRad(35);
    const horizontal = distance * Math.cos(elevation);
    camera.position.set(
      target.x + horizontal * Math.sin(azimuth),
      target.y + distance * Math.sin(elevation),
      target.z + horizontal * Math.cos(azimuth),
    );
    camera.lookAt(target);
    camera.updateMatrixWorld();
    camera.updateProjectionMatrix();
    controls.target.copy(target);
    controls.minDistance = distance * 0.15;
    controls.maxDistance = distance * 4.0;
    controls.minPolarAngle = THREE.MathUtils.degToRad(10);
    controls.maxPolarAngle = THREE.MathUtils.degToRad(85);
    camera.near = Math.max(0.5, distance / 2500);
    camera.far = Math.max(30000, distance * 20);
    camera.updateProjectionMatrix();
    controls.update();
    userInteracted = false;
    window.__fhopsViewerDebug = {
      target: [target.x, target.y, target.z],
      blockCentroid: [cx, groundY, cy],
      radius,
      distance,
    };
  }

  function animate(now) {
    requestAnimationFrame(animate);
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    if (playing && payload) {
      currentTime += dt * speed * duration / 90;
      if (currentTime > duration) currentTime = 0;
      setTime(currentTime);
    }
    controls.update();
    renderer.render(scene, camera);
  }

  resize();
  requestAnimationFrame(animate);

  return {
    load,
    resize,
    fit: fitCamera,
    deckVolumes: () => (deckCurves ? deckVolumesAt(currentTime) : { unprocessed: 0, processed: 0 }),
    truckStatuses: () => Object.entries(trucks).map(([id, group]) => `${id} ${group.userData.status || 'waiting'}`),
    machineStates,
    seek: (t) => setTime(t),
    reset: () => setTime(0),
    setSpeed: (value) => { speed = value; },
    pause: () => { playing = false; },
    play: () => { playing = true; last = performance.now(); },
    toggle: () => { playing = !playing; last = performance.now(); return playing; },
    isPlaying: () => playing,
  };
}
