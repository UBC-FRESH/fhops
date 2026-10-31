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
  let loadedRunKey = null;
  let baseElevation = 0;
  let residualGroup = null;
  let terrain = null;
  let loaded = false;
  let userInteracted = false;

  controls.addEventListener('start', () => { userInteracted = true; });

  function resize() {
    const width = container.clientWidth || window.innerWidth;
    const height = container.clientHeight || window.innerHeight;
    renderer.setSize(width, height, false);
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
    residualGroup = null;
    timelineByMachine = {};
    processedTimes = [];
    cumulativeVolume = [];
    terrain = null;
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

  function updateTrucks(t) {
    for (const [id, group] of Object.entries(trucks)) {
      const events = truckEvents[id] || [];
      const active = events.find((event) => t >= event.start_s && t <= event.end_s);
      group.userData.status = active ? active.type.replaceAll('_', ' ') : 'parked';
    }
  }

  function setTime(t) {
    currentTime = Math.max(0, Math.min(duration, t));
    updateMachines(currentTime);
    updateTrucks(currentTime);
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
    const canvas = document.createElement('canvas');
    canvas.width = 256; canvas.height = 64;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#101416cc'; ctx.fillRect(0, 0, 256, 64);
    ctx.fillStyle = '#e8eef2'; ctx.font = 'bold 28px system-ui'; ctx.fillText(id, 8, 42);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false }));
    sprite.position.set(0, 7, 0); sprite.scale.set(8, 2, 1);
    group.add(sprite);
    const x = landing.x + (index - 1) * 22;
    const y = landing.y - 30;
    group.scale.setScalar(1.7);
    group.position.set(x, sampleHeight(x, y) + 1.7, y);
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

        const truckCount = events.truck_summary?.truck_count || 0;
        for (let index = 1; index <= truckCount; index++) makeTruck(`T${index}`, index, events.landing);
        for (const event of events.truck_events || []) {
          (truckEvents[event.machine] ||= []).push(event);
        }
        for (const list of Object.values(truckEvents)) list.sort((a, b) => a.start_s - b.start_s);

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
    // Frame the whole ground plan, not the tallest machine beacon. Use the
    // stand/tree bounding box for plan dimensions, put the target at the
    // ground-plan centroid, and fit both the vertical and horizontal FOV.
    // The fixed 50° elevation / 35° azimuth gives a predictable bird's-eye
    // oblique view for every case.
    const box = new THREE.Box3().setFromObject(scene);
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const radius = Math.max(10, 0.5 * Math.hypot(size.x, size.z));
    const target = new THREE.Vector3(
      center.x,
      terrainHeight(center.x, center.z),
      center.z,
    );
    const elevation = THREE.MathUtils.degToRad(50);
    const azimuth = THREE.MathUtils.degToRad(35);
    const vFov = THREE.MathUtils.degToRad(camera.fov);
    const hFov = 2 * Math.atan(Math.tan(vFov / 2) * Math.max(0.1, camera.aspect));
    const fitFov = Math.min(vFov, hFov);
    const heightFit = (Math.max(1, size.y) / 2) / Math.tan(vFov / 2);
    let distance = Math.max(
      radius / Math.sin(fitFov / 2),
      heightFit,
    ) * 1.35;

    const place = () => {
      const horizontal = distance * Math.cos(elevation);
      camera.position.set(
        target.x + horizontal * Math.sin(azimuth),
        target.y + distance * Math.sin(elevation),
        target.z + horizontal * Math.cos(azimuth),
      );
      camera.lookAt(target);
      camera.updateMatrixWorld();
      camera.updateProjectionMatrix();
    };
    place();

    // Account for the tallest trees and the cable spar without letting a
    // single beacon dominate the fit. Iterate on the actual projected corners.
    const corners = [];
    for (const x of [box.min.x, box.max.x]) {
      for (const y of [box.min.y, box.max.y]) {
        for (const z of [box.min.z, box.max.z]) corners.push(new THREE.Vector3(x, y, z));
      }
    }
    for (let pass = 0; pass < 3; pass++) {
      let extent = 0;
      for (const corner of corners) {
        const ndc = corner.clone().project(camera);
        extent = Math.max(extent, Math.abs(ndc.x), Math.abs(ndc.y));
      }
      if (!Number.isFinite(extent) || extent <= 0) break;
      distance = Math.min(radius * 12, Math.max(radius * 0.5, distance * (extent / 0.82)));
      place();
    }

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
