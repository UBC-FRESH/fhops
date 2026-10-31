# P20 serious game — validation note

Status: core game path is implemented and tested; P20.3 polish remains open.

## Delivered

- Three stand-scale levels: MKRF, Gavin Lake, Knife Creek.
- One block per level with committed EPSG:3005 boundaries.
- Nemora/FAIB-PSP synthetic tree inventories and pins.
- Knife Creek selection-cut careful-logging trade-off with diminishing damage
  benefits and residual-tree inventory.
- Finite precomputes for every level:
  - MKRF: 4 combinations, best $334,549.83 / worst $326,885.86.
  - Gavin: 4 combinations, best $2,456.78 / worst -$5,711.50 (straddles
    break-even by design).
  - Knife Creek: 20 combinations, best $75,705.63 / worst $21,969.10.
- Local game API, session/team order enforcement, one-play rejection,
  leaderboard, post-level debrief, and final-only optional chat.
- DeepSeek V4.1 Flash provider hook, strict JSON validation, and level+choice
  explanation cache.
- CLI launch flags for levels, precomputes, model, and cache.
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

## Limits and open work

- No public authentication; instructor/local deployment only.
- MKRF/Gavin boundaries are VRI-derived FEMIC layers, not raw VRI polygons.
- Gavin PSP support is two plots and its stand is synthetic.
- Price/cost decks are game assumptions, not market forecasts.
- FHOPS stem products are placeholders.
- The Game page has a level selector and leaderboard but not a full lobby/level
  map or live progress view.
