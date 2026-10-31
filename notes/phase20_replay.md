# P20 dual 3D replay plan

Decision: pre-save the no-tip optimal replay for each level; generate the
player-selected replay JIT and cache it by level + choice hash.

## Assets

For each replay capture:

- stand/tree scene GLTF;
- `system_events.json` with machine and tree timelines;
- `terrain.json` when available;
- scene metadata: level, choices, contractor, duration, tree count.

Optimal captures are generated offline and committed under
`examples/game/replays/<level>/optimal/`. MKRF, Gavin, and KC optimal captures are pre-saved. Player captures are generated
JIT and cached, with per-directory locks and duration consistency checks so a
scene, event timeline, and metadata file cannot be mixed across runs.

Player captures are generated after a completed attempt under
`build/game_replays/<level>/<choice-hash>/` and served only to that session/team.
The JIT generation reuses `simulate_ground_system` with the selected scenario
variant and writes the same viewer contract.

## UI

After a level is complete, show a two-pane 3D replay:

- left: optimal plan;
- right: player plan.

Each pane is the existing FHOPS tree-system viewer with independent orbit/zoom.
A wrapper synchronizes play/pause, timeline position, and speed. The player can
scrub and replay as often as desired.

## Job execution

Replay generation is asynchronous. The game starts a replay job, polls its
state, and opens the dual viewer only when both assets are ready. This avoids
proxy timeouts during the expensive KC scene/timeline generation.

## Constraints

- No replay assets before completion.
- JIT generation takes roughly the tree-system run time; show progress and cache.
- Pre-saved optimal assets are server-side; do not expose the optimal choices
  before the debrief gate.
- Camera controls remain independent so visual learners can inspect either plan.
