# P20 serious game — closeout

Status: complete. Delivered in PR #317; dual replay and closeout follow-ups verified through #428.

## Delivered

- Three stand-scale levels: MKRF, Gavin Lake, Knife Creek.
- One block per level with committed EPSG:3005 boundaries.
- Nemora/FAIB-PSP synthetic tree inventories and pins.
- Knife Creek selection-cut careful-logging trade-off with diminishing damage
  benefits and residual-tree inventory.
- Finite precomputes for every level:
  - MKRF: 4 combinations, best $257,235.66 / worst $246,117.58.
  - Gavin: 4 combinations, best $2,302.38 / worst -$3,838.62 (deliberately
    straddles break-even).
  - Knife Creek: 20 combinations, best $70,773.50 / worst $20,880.42.
- Local game API, session/team order enforcement, one-play rejection,
  leaderboard, post-level debrief, and final-only optional chat.
- DeepSeek V4.1 Flash provider hook, strict JSON validation, and level+choice
  explanation cache.
- CLI launch flags for levels, precomputes, model, and cache.
- Level map with completed/current/locked states and submission feedback.
- Dual 3D replay with pre-saved optimal assets, JIT/cached player assets, linked play/scrub, and compacted machine timelines.
- Instructor how-to: `docs/howto/serious_game.rst`.

## Validation

- Game/web/CLI tests pass, including:
  - precompute completeness and score bounds;
  - no `best_choices` leakage in public payloads;
  - identical scores for identical choices across teams;
  - level-order and replay rejection;
  - debrief/chat gating before completion;
  - DeepSeek prompt/response and cache behavior.
- All three `precompute_stand_level.py --check` runs pass.
- Full three-level tournament test: identical choices across two teams produce
  identical scores and attempts; debrief is available after completion.
- Dual replay API tests cover gating, job lifecycle, tokenized assets, and
  committed optimal capture consistency.
- Browser smoke: both viewer panes ready, linked clock advanced, timeline
  compacted from 35,942 events to 2,226 bars, no page errors.
- Pre-commit passes on changed files.

## Limits and follow-ups

- No public authentication; local/instructor deployment only.
- MKRF/Gavin boundaries are VRI-derived FEMIC layers, not raw VRI polygons.
- Gavin PSP support is two plots and its stand is synthetic.
- Price/cost decks are game assumptions, not market forecasts.
- FHOPS stem products are placeholders.
- A true live tree-system progress view is not implemented because submissions
  are scored from the precomputed grid; the UI shows submission progress only.
