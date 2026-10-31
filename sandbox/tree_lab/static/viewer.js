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
  roadside_processor: 'P',
  processor: 'P',
  loader: 'L',
  cable_yarder: 'Y',
};
const MACHINE_OFFSETS = { H4: [12, 0], H5: [-12, 0], H6: [0, 12] };
const SWATH_BAND_HEIGHT_M = 24;

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
  let trucks = {};
  let deckCurves = null;
  let decks = {};
  let cableSpec = null;
  let cableYarderId = null;
  let carriage = null;
  let loadedRunKey = null;
  let baseElevation = 0;
  let residualGroup = null;
  let terrain = null;
  let loaded = false;
  let userInteracted = false;
  let blockOutline = null;

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
    residualGroup = null;
    timelineByMachine = {};
    processedTimes = [];
    cumulativeVolume = [];
    terrain = null;
    blockOutline = null;
    payload = null;
  }

  function terrainHeight(x, y) {
    if (!terrain) return baseElevation;
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

  function updateMachines(t) {
    for (const [id, group] of Object.entries(machines)) {
      const state = segmentAt(id, t);
      if (!state) continue;
      const segment = state.segment;
      let x = segment.x0 + (segment.x1 - segment.x0) * state.f;
      let y = segment.y0 + (segment.y1 - segment.y0) * state.f;
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

  function updateTrucks(t) {
    for (const [id, group] of Object.entries(trucks)) {
      const events = truckEvents[id] || [];
      const active = events.find((event) => t >= event.start_s && t <= event.end_s);
      const home = group.userData.home;
      const mill = group.userData.mill;
      let x = home[0];
      let y = home[1];
      let status = 'waiting';
      let heading = 0;
      if (active?.type === 'truck_load') {
        status = 'loading';
        group.userData.cargo.visible = true;
      } else if (active?.type === 'truck_return') {
        const span = Math.max(1, active.end_s - active.start_s);
        const f = Math.max(0, Math.min(1, (t - active.start_s) / span));
        let u;
        if (f < 0.15) u = 0;
        else if (f < 0.65) u = (f - 0.15) / 0.5;
        else if (f < 0.85) u = 1;
        else u = (1 - f) / 0.15;
        x = home[0] + (mill[0] - home[0]) * u;
        y = home[1] + (mill[1] - home[1]) * u;
        heading = Math.atan2(mill[1] - home[1], mill[0] - home[0]);
        status = f >= 0.85 ? 'returning' : (f >= 0.65 ? 'at mill' : 'driving out');
        group.userData.cargo.visible = true;
      } else {
        group.userData.cargo.visible = false;
      }
      group.position.set(x, sampleHeight(x, y) + 1.8, y);
      group.rotation.y = heading;
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
    const home = [landing.x + (index - 1) * 13, landing.y - 28];
    const mill = [landing.x + 120, landing.y + 140];
    group.scale.setScalar(1.7);
    group.userData = { home, mill, cargo, status: 'waiting', id };
    group.position.set(home[0], sampleHeight(home[0], home[1]) + 1.8, home[1]);
    scene.add(group);
    trucks[id] = group;
  }

  function addResidualTrees(payload) {
    if (!payload || !Array.isArray(payload.trees) || !payload.trees.length) return;
    const group = new THREE.Group();
    group.name = 'residual_trees';
    const trunkGeo = new THREE.CylinderGeometry(0.16, 0.22, 1, 5);
    const crownGeo = new THREE.ConeGeometry(1, 1, 7);
    const trunkMat = new THREE.MeshStandardMaterial({ color: 0x5a4632, roughness: 0.9 });
    // Teal tint so leave trees are visually distinct from the harvested stand.
    const crownMat = new THREE.MeshStandardMaterial({ color: 0x2f7f78, roughness: 0.95 });
    for (const tree of payload.trees) {
      const height = Math.max(2, Number(tree.height_m) || 20);
      const dbh = Math.max(0.1, (Number(tree.dbh_cm) || 30) / 100);
      const crownRadius = Math.max(0.6, Number(tree.crown_radius_m) || dbh * 3);
      const x = Number(tree.x);
      const y = Number(tree.y);
      const base = sampleHeight(x, y);
      const trunk = new THREE.Mesh(trunkGeo, trunkMat);
      trunk.scale.set(dbh * 1.2, height * 0.4, dbh * 1.2);
      trunk.position.set(x, base + height * 0.2, y);
      const crown = new THREE.Mesh(crownGeo, crownMat);
      crown.scale.set(crownRadius, height * 0.65, crownRadius);
      crown.position.set(x, base + height * 0.55, y);
      group.add(trunk, crown);
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
      new THREE.MeshStandardMaterial({ color: 0x737a55, roughness: 1.0, metalness: 0.0 }),
    );
    mesh.name = 'terrain';
    mesh.position.set((minx + maxx) / 2, 0, (miny + maxy) / 2);
    const position = geometry.attributes.position;
    for (let index = 0; index < position.count; index += 1) {
      const x = mesh.position.x + position.getX(index);
      const z = mesh.position.z + position.getZ(index);
      position.setY(index, terrainHeight(x, z));
    }
    position.needsUpdate = true;
    geometry.computeVertexNormals();
    scene.add(mesh);

    for (const node of treeNodes.values()) {
      const x = node.position.x;
      const z = node.position.z;
      node.position.y = terrainHeight(x, z);
    }
    baseElevation = terrainHeight(
      Number(terrain.origin?.[0] || (minx + maxx) / 2),
      Number(terrain.origin?.[1] || (miny + maxy) / 2),
    );
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
          baseElevation = Number(terrain.base_m ?? baseElevation);
          applyTerrain(root);
        }

        const spec = { ...events.machines };
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
        // give the cable case the same visible landing → mill → landing truck
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
        for (const list of Object.values(truckEvents)) list.sort((a, b) => a.start_s - b.start_s);
        const truckIds = Object.keys(truckEvents).sort();
        if (!truckIds.length) {
          const truckCount = Number(events.truck_summary?.truck_count) || 0;
          for (let index = 1; index <= truckCount; index += 1) truckIds.push(`T-${String(index).padStart(2, '0')}`);
        }
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
          if (truckIds.length) {
            const millX = events.landing.x + 120;
            const millY = events.landing.y + 140;
            const shed = new THREE.Mesh(
              new THREE.BoxGeometry(18, 8, 14),
              new THREE.MeshStandardMaterial({ color: 0x59656a, roughness: 0.85 }),
            );
            shed.position.set(millX, sampleHeight(millX, millY) + 4, millY);
            scene.add(shed);
            const millLabel = makeTextSprite('mill', 2.5);
            millLabel.sprite.position.set(millX, sampleHeight(millX, millY) + 12, millY);
            scene.add(millLabel.sprite);
            const road = new THREE.Line(
              new THREE.BufferGeometry().setFromPoints([
                new THREE.Vector3(events.landing.x, sampleHeight(events.landing.x, events.landing.y) + 0.5, events.landing.y),
                new THREE.Vector3(millX, sampleHeight(millX, millY) + 0.5, millY),
              ]),
              new THREE.LineBasicMaterial({ color: 0x9a8b5a, transparent: true, opacity: 0.55 }),
            );
            road.name = 'mill_road';
            scene.add(road);
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
