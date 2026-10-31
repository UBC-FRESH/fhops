# Phase 20 plan: stand-scale web serious game

Parent issue: #311
Branch: `feature/phase20-serious-game`
Status: revised 2026-10-31 — old shift-scenario levels retired

## Revision

The first P20 draft used the synthetic `tiny7`, `small21`, `med42`, and
`large84` shift scenarios. That was the wrong abstraction for the game. Those
levels are multi-block scheduling exercises with no stand geometry, no tree
list, no log recovery, and no net profit.

The game is now organised around **one real VRI-derived stand per level**:

- the stand boundary is the map/viewport;
- a deterministic tree list is generated inside that boundary;
- the player controls the block-level machine plan, landing choice, and bucking
  policy;
- the score is dominated by **net operations profit**, not just delivered
  volume.

The existing exact-precompute pipeline and old tiny7 artifact are retained only
for regression/reference until the stand-scale loader replaces them. They are
not the game's active levels.

## Goal

Turn the operational web UI into a deterministic, instructor-run serious game.
Each level is one real stand polygon from MKRF, AFRF Gavin Lake, or AFRF Knife
Creek. Teams choose a bounded machine/arrival/landing/bucking plan, run one
deterministic operation, and receive a 0–100 score based on normalized net
profit.

## Selected stands

Stand selection is committed in `examples/game/stands/catalog.yaml` with the
exact polygons as EPSG:3005 GeoJSON.

| Level | Stand | Area | BEC / stand | System | Main difficulty |
| --- | --- | ---: | --- | --- | --- |
| 1 `mkrf_684` | MKRF RES_KEY 684 | 6.86 ha | CWHdm, HW/FDC, 104 y | tree-length: feller + skidder + loader | starter: small layout, no processor |
| 2 `gavin_3` | Gavin Lake BLOCK_ID 3 | 13.94 ha | ICHmk3, 207 y | cut-to-length: feller + skidder + processor + loader | intermediate: value recovery and processing balance |
| 3 `kc_57254551` | Knife Creek VRI polygon 57254551 | 35.95 ha | IDFdk3, FDI, 140 y, 479 stems/ha, 146.6 m³/ha | selection cut, cut-to-length, two skidders | advanced: careful-logging trade-off, landing choice, trunk-road extension |

### Provenance

- MKRF: `models/mkrf_patchworks_model/spatial/fragments.shp`, a VRI-derived
  MKRF patchworks layer; selected by `RES_KEY`.
- Gavin Lake: `data/legacy_gavinlake/spatial/fragments.shp`, a VRI-derived
  cutblock layer; selected by `BLOCK_ID`.
- Knife Creek: `data/inventory/vri_2025_kc.gpkg`, VRI 2025 R1; selected by
  `POLYGON_ID`.

Only Knife Creek is backed by a raw VRI polygon in the local FEMIC instance.
MKRF and Gavin Lake are backed by VRI-derived stand layers with VRI/BEC and age
attributes. If a raw-VRI-only rule is required, those two boundaries must be
replaced with public VRI polygons before the levels are enabled.

### Optional boss level

A later fourth level can use Knife Creek `POLYGON_ID 34685844` (57.05 ha,
IDFdk3, 734 stems/ha, 204 m³/ha) with three landing options. It is not part of
the MVP because the larger tree list and road extensions increase simulation
cost.

## One block, whole-operation viewport

Every level has exactly one harvest block. This keeps the web map simple: the
viewport can frame the whole operation, including the block boundary, tree
list, landing candidates, and any trunk-road extension.

Large blocks may have **multiple mutually exclusive landing options**:

- `main` uses existing access and has no road-extension cost;
- `north` / `south` (or similar) require a short deterministic trunk-road
  extension, charged as length × unit cost plus mobilisation;
- the chosen landing is part of the player's plan and is revealed with the
  optimal plan after completion.

For MVP, one landing is active in a run. If simultaneous landings are added
later, the visual stand is partitioned into simulation sub-blocks but remains
one level and one map extent.

Landing coordinates, trunk-road alignment, and extension lengths must be
surveyed from the stand boundary/road layer or DEM. They are not invented in
the scoring code.

## Deterministic synthetic tree maps

Tree lists are generated offline with Nemora from PSP distributions, pinned,
and checked into the level assets:

1. Select PSP plots matching the stand BEC, leading species, and age/site
   stratum.
2. Fit species composition and DBH/height distributions; retain the fit
   metadata and sample sizes.
3. Generate a deterministic tree list with the level seed and place trees
   inside the exact stand polygon.
4. Calibrate to VRI stems/ha and volume/ha where those attributes exist.
5. Export a `fhops.tree.inventory.v1` table plus metadata and checksums.

Knife Creek has local PSP assets (`data/psp/`). MKRF CWHdm and Gavin Lake
ICHmk3 currently need BEC-matched PSP inputs; those levels must stay disabled
until the fit source and sample counts are recorded. Do not substitute VRI
polygon attributes for a tree list and call it PSP-derived.

The tree list is fixed for all teams. The player does not control the hidden
tree map, breakdown timings, or PSP sampling.

## Machine plan controls

1. **Fleet counts** within the level palette. Extra slots have increasing fixed
   opportunity costs, including the expensive spot/rental slot.
2. **Arrival posture**: hot, staged, or phased.
3. **Shift plan**: operating days/shifts and shift length within the level's
   allowed windows.
4. **Landing option**: main or a trunk-road-extension option.
5. **Bucking policy** (below).

The machine plan is evaluated by the tree-scale system. The old multi-block SA
assignment is not the game's primary scheduling engine; one block does not give
SA a meaningful block-selection problem. A fixed-fleet schedule solver may still
be used internally where it improves the operations plan, but the scored output
is the deterministic tree-system/net-profit result.

## Careful logging and residual damage (Knife Creek)

Knife Creek is a selection cut, not a clearcut. The base harvester productivity
is reduced by `0.80` relative to a clear-fell rate to account for slower
movement, selection of retained stems, and damage avoidance.

The player then chooses a careful-logging level. Higher care:

- lowers harvester productivity further;
- adds a negotiated operator care premium per harvested m³;
- reduces the fraction of residual trees damaged.

The residual-damage benefit has **decreasing marginal returns**:

| Setting | Care multiplier | Care premium $/m³ | Residual damage |
| --- | ---: | ---: | ---: |
| standard | 1.00 | 0.0 | 20% |
| light care | 0.96 | 2.0 | 13% |
| moderate care | 0.90 | 3.0 | 8.5% |
| high care | 0.82 | 7.0 | 5.5% |
| maximum care | 0.72 | 14.0 | 4.0% |

The exact mapping is server-side and is used in precompute. The briefing shows
only plausible ranges: care premium `0–14 $/m³`, productivity multiplier
`0.72–1.0`, and residual damage `4–20%`. Players can reason about the trade-off
but cannot calculate the exact optimum from the UI. The default curve has an
interior optimum, so “maximum care” is not automatically best.

Residual trees are a separate pinned inventory. They are not processed by the
tree system. Their asset value loss is charged as:

```text
residual_damage_loss = residual_asset_value * residual_damage_fraction
```

The residual inventory, damage value, and exact care mapping are revealed only
in the post-level debrief.

## Bucking policy and log value

The player parameterizes a bucking policy, for example:

- target log length (finite choices such as 4.9, 5.2, 6.1 m);
- stump height;
- minimum sawlog DBH;
- top diameter / grade split;
- whether to prioritize grade recovery or volume recovery.

The policy changes which logs are produced from each stem and therefore
recovery by product/grade. FHOPS currently has a simple `sawlog`/`pulp` stem
model with placeholder products; P20 must add a level-owned product price
schedule and a game bucking-policy adapter. The adapter must be deterministic
and report volumes by product/grade, not just total merchantable volume.

The KC stand uses a calibrated reference stem form factor (`0.192014`) so the
harvested tree list reconciles to the VRI volume target (3,162 m³). The tree
system now accepts `--stem-form-factor`, bucking (`--stem-log-length`,
`--stem-stump-height`, `--stem-sawlog-min-dbh`), and a
`--feller-productivity-multiplier`; the game engine will pass the selection-cut
base (`0.80`) times the chosen care multiplier.

Revenue:

```text
gross_log_value = sum(product_volume_m3 * product_price_per_m3)
```

## Net-profit scoring

Ops cost includes scheduled machine hours, mobilisation, landing/road
extension, trucking if enabled, and the fixed fleet opportunity cost.

```text
net_profit = gross_log_value
           - machine_operating_cost
           - careful_logging_premium
           - residual_damage_loss
           - mobilisation_cost
           - road_extension_cost
           - landing_cost
           - trucking_cost
           - fleet_opportunity_cost
```

The level fixes objective weights and product prices. The game precomputes every
feasible finite control combination with the deterministic evaluator and
records best/worst net profit:

```text
score = 100 * (net_profit - worst_level) / (best_level - worst_level)
```

Scores are clamped to 0–100. The score is only enabled when every feasible
combination is evaluated, the tree inventory and event calendar are pinned, and
the precompute is complete. Best-known or sampled bounds must not be labelled
optimal.

The old fleet-opportunity formula is retained: extra marginal multipliers
`1×`, `2×`, `8×`, with a `4×` spot surcharge on the last slot. It is now one
component of net profit, not the whole objective.

## Deterministic events

Breakdowns, weather/terrain downtime, and other hidden events are fixed per
level and seed. They are stored server-side and replayed identically for every
team. They are never sent to the client before the attempt is complete.

## End-of-level learning debrief

After completion, reveal:

- the optimal machine plan, landing choice, and bucking policy;
- the player's plan and score;
- gross log value, product/grade recovery, machine hours, mobilisation, road
  extension, fleet opportunity cost, and net profit;
- the cost of each wrong parameter value, computed by replacing one parameter
  with the optimal value while holding the rest fixed.

The explanation layer remains fact-grounded:

1. Build a structured `ExplanationFacts` payload from the precomputed grid.
2. Generate the “why optimal” and per-parameter cost text with the optional LLM
   under a strict JSON schema.
3. Validate every numeric claim against `ExplanationFacts`; fall back to
   deterministic templates on mismatch.
4. Cache by level + choice hash so every team sees the same explanation.

Optimal controls, optimal bucking policy, and hidden events are withheld until
the attempt completes.

## Tournament state

- `TournamentSession`: instructor-created ID, level order, ruleset hash.
- `TeamSession`: opaque team code, ordered attempts, scores, total.
- `LevelAttempt`: controls, inventory hash, event hash, run ID, net profit,
  normalized score, status.
- One attempt per level; server rejects replay, skip-ahead, and cross-level
  submission.
- State is local-only and persisted server-side. No public authentication claim.

## UI

A new **Game** workspace:

- lobby/team code entry;
- ordered level map with locked/completed states;
- level briefing, whole-stand viewport, tree/landing context;
- fleet/arrival/shift/landing/bucking controls;
- launch and run progress;
- score card, leaderboard, and post-level debrief.

## Artifacts

Committed stand assets:

- `examples/game/stands/catalog.yaml` — selected stands and provenance.
- `examples/game/stands/*.geojson` — exact EPSG:3005 stand boundaries.

Planned assets and code:

- `examples/game/levels/<level>.yaml` — level manifests.
- `examples/game/stands/<level>/trees.csv` and metadata — harvested Nemora
  inventories.
- `examples/game/stands/<level>/residual_trees.csv` — residual stems for damage
  accounting (Knife Creek).
- `examples/game/stands/<level>/landings.geojson` — landing candidates and
  trunk-road extensions.
- `scripts/generate_game_inventory.py` — deterministic Nemora/PSP producer.
- `examples/game/stands/<level>/prices.yaml` — product/grade prices.
- `src/fhops/game/levels.py`, `inventory.py`, `bucking.py`,
  `careful_logging.py`, `scoring.py`, `precompute.py`, `state.py`.
- `src/fhops/web/game.py` and `src/fhops/web/static/game.*`.
- `tests/game/`, `tests/web/test_game_api.py`.
- `docs/howto/serious_game.rst`.

## Acceptance

- Three MVP levels use the committed MKRF, Gavin Lake, and Knife Creek stand
  polygons; one block per level.
- Each level has a pinned Nemora/PSP tree inventory and provenance; levels
  without a valid PSP fit stay disabled.
- Players can parameterize fleet, arrival, shift, landing, bucking policy, and
  (on Knife Creek) careful logging.
- The score is normalized net profit with log-value recovery, operating costs,
  care premium, and residual damage visible.
- Careful-logging damage benefits have decreasing marginal returns; maximum
  care is not automatically optimal.
- Every feasible finite combination is precomputed; incomplete levels fail
  closed.
- Same choices produce identical trees, events, machine runs, and scores.
- One-play/order rules are server-enforced.
- Optimal plans and hidden events never reach the client before completion.
- Tests/docs pass; no operational or harvest-planning claim.

## Risks

- CWHdm/ICHmk3 PSP coverage is not yet local; the two smaller levels may need
  public PSP inputs or a BEC-matched regional fit.
- FHOPS tree system is ground-based and currently supports one feller/loader
  with multiple skidders/processors; the game must not imply cable or full
  multi-feller support.
- FHOPS stem products are placeholders; bucking/value code must be added and
  validated.
- Careful-logging curve defaults are a game design, not an empirical
  productivity/damage model; they need calibration and clear caveats.
- Landing candidates and trunk-road lengths need a real road/DEM survey.
- Exhaustive tree-system precompute can still be expensive for the 36 ha level;
  cache bucking value by stand/policy and fail closed on incomplete grids.
- The web service has no authentication; tournaments are local/instructor-run.
- The game measures simulated operational decisions, not real-world
  productivity or profitability.
