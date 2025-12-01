# FHOPS MILP Formulation Plan

This note captures candidate mixed-integer programming (MILP) formulations for
FHOPS-style machine–block–time scheduling, plus design ideas borrowed from the
recent harvest-planning literature.

The goal is **not** to replace the heuristics, but to:

- Provide small/medium-scale MILP benchmarks for validation and “upper bound”
  comparison.
- Sketch a tactical planning layer (team–area–period) that can sit above the
  current shift-indexed heuristics.
- Inform any future column-generation / decomposition work.

## 1. Literature hooks

### 1.1 Tactical harvest-team planning

- **Bredström, Jönsson & Rönnqvist (2010)** — *Annual planning of harvesting
  resources in the forest industry* (Int. Trans. Oper. Res. 17(2):155–177).
  - Problem: annual allocation of harvest teams (harvester+forwarder pairs) to
    harvest areas over four seasons.
  - Time: seasonal (four periods), no daily/shift structure.
  - Key ingredients:
    - Team–area compatibility and min/max volume per area and per season.
    - “Compression” penalties for assigning teams far from their home base
      (discourages long-distance assignments unless necessary).
    - Capacity constraints on team hours per season.
    - Two-phase solution: MIP for allocation, then TSP-style heuristics for
      sequencing the harvest areas within each season for each team.
  - **Use to copy:**
    - Team–area–season assignment variables.
    - Compression/penalty structure for distance from home base or preferred
      working region.
    - High-level capacity constraints and AAC-style volume envelopes.

- **Frisk, Flisberg, Rönnqvist & Andersson (2016)** — *Detailed scheduling of
  harvest teams and robust use of harvest and transportation resources* (Scand.
  J. Forest Research 31(7):681–690).
  - Problem: integrated planning of harvest teams and transportation, from
    short-term detailed schedules up to a longer tactical horizon.
  - Time: split into business (daily) and anticipation (monthly) periods in a
    rolling-horizon framework.
  - Key ingredients:
    - Business periods:
      - Detailed schedule for harvest teams (start times on harvest areas,
        durations over multiple days).
      - Bucking price-list choice per area/period to match demand.
      - Explicit truck flows and inventory at terminals.
    - Anticipation periods:
      - Coarser aggregate decisions about which areas to harvest and flows to
        customers.
    - Penalties:
      - Upper bounds on the number of moves per machine, with penalties for
        exceeding (discourages churning between areas).
      - Compression cost for harvesting far from the team’s home base (similar
        to Bredström).
    - Solution method:
      - Sequence of decomposed MIPs using different aggregations of the full
        model, rather than one huge monolith.
  - **Use to copy:**
    - Business vs anticipation period structure for a tactical FHOPS layer
      (e.g., days vs weeks/months).
    - Move-count and distance-penalty structures.
    - Rolling-horizon decomposition ideas (solve near-term detail + far-term
      aggregate, then roll forward).

### 1.2 Integrated harvest + timber supply

- **Shabaev, Sokolov, Urban & Pyatin (2020)** — *Optimal Planning of Wood
  Harvesting and Timber Supply in Russian Conditions* (Forests 11:662).
  - Problem: joint planning of harvest sites and timber flows to customers over
    a one-year horizon, under Russian AAC and logistics constraints.
  - Time: annual tactical horizon with periods; sites are assigned to periods
    and customers.
  - Key ingredients:
    - Multicriteria Boolean nonlinear programming model (profit + other
      criteria), reduced to a block linear program.
    - Blocks correspond roughly to site–period–assortment patterns.
    - Solution via Dantzig–Wolfe decomposition with column generation:
      - Master problem chooses patterns for each site/period.
      - Subproblems generate profitable patterns consistent with AAC, demand,
        road access, etc.
  - **Use to copy:**
    - Block structure and pattern concepts for any FHOPS column-generation work
      (e.g., patterns = “harvest this block subset in this period with this
      mix of assortments”).
    - Profit-based objective that includes both harvest and transport costs and
      customer revenue.

### 1.3 Operational harvest scheduling (closest to FHOPS)

- **Arora (2023)** — *Optimization of forest harvest scheduling at the
  operational level* (UBC PhD thesis) and the associated IJFE papers.
  - Problem: detailed scheduling of harvesting activities across multiple cut
    blocks with precedence constraints, machine movement, and (in later
    chapters) multiple-machine assignments and multi-task machines.
  - Time: continuous or discretised time over a 12-week horizon.
  - Key ingredients (Chapter 3 model):
    - Activities: up to seven harvesting activities (manual/mechanical felling,
      ground/cable/aerial yarding, mechanical processing, loading).
    - Machines:
      - Exclusive to activities in Model 1.
      - Multiple machines per activity and multi-task machines in later models.
    - Decision variables:
      - Start and end time of each activity on each block.
      - Binary machine–block–activity assignment.
      - Sequencing / movement decisions: which block a machine goes to next.
    - Constraints:
      - Activity precedence within each block (e.g., yarding cannot start
        before felling ends; loading after yarding/processing).
      - Machine continuity and exclusivity: each machine works on at most one
        block/activity at any time; travel times between blocks.
      - Optional slope- and system-based precedence variations in later models.
    - Objective:
      - Minimise total cost = operating costs + idle time + machine movement.
    - Implementation:
      - Mixed-integer linear programming with a rolling-horizon execution (re-
        solve for each 12-week window with updated inputs).
  - **Use to copy:**
    - Activity–block–time decision structures with explicit precedence.
    - Machine continuity and movement constraints for a MILP that mirrors
      FHOPS’s heuristic schedules.
    - Rolling-horizon execution strategy for operational scheduling.

### 1.4 Additional references (from fhop folder)

- **Bredström, Jönsson & Rönnqvist (2010)** — already captured via HTML
  metadata (`j.1475-3995.2009.00749.x.html`).
- **Frisk et al. (2016)** — `Detailed scheduling of harvest teams and robust use
  of harvest and transportation resources.pdf`.
- **Shabaev et al. (2020)** — `forests-11-00662-v2.pdf` / `.xml`.
- **Arora (2023)** — `ubc_2023_november_arora_rohit.pdf.pdf`.
- **Additional PDFs in `notes/reference/fhop/`** such as early OR papers
  (`1-s2.0-S0168169925001668-main.pdf`, `1-s2.0-S0377221799001447-main.pdf`),
  Gerasimov, and MDPI Forests articles (e.g., `forests-10-01110-v2.pdf`) appear
  to focus more on tactical wood supply/logistics or equipment productivity;
  they are useful context but less directly aligned with FHOPS’s shift-indexed
  machine–block assignment than the four core references above.

## 2. FHOPS vs literature: problem alignment

FHOPS’s core optimisation problem (as implemented by the heuristics) is:

- Given:
  - A finite set of **blocks** with work requirements, windows, stand metrics,
    and mobilisation distances.
  - A set of **machines** with roles, daily-hours/availability, and per-block
    productivity (m³ per shift/day).
  - A discretised planning horizon (days × shifts).
- Decide:
  - For each machine, day, and shift, which block (if any) it works on.
  - Respect block windows and “finish-the-block-before-switching” constraints.
  - Optionally, respect landing capacities, mobilisation costs, and penalties
    on left-over volume.
- Objective:
  - Maximise total production (or a weighted combination of production,
    mobilisation, makespan, etc.), penalising unfinished volume.

Closest analogues:

- Arora’s MILPs match the **machine–block–time** flavour, but with continuous
  time and explicit activity precedence rather than day×shift grids.
- Bredström/Frisk/Shabaev operate at higher tactical levels (teams ↔ areas ↔
  periods, or sites ↔ patterns ↔ periods), with daily/weekly detail only for
  teams/trucks, not individual machines per shift.

Conclusion: we can treat Arora as the main **operational** template, with
Frisk/Bredström/Shabaev guiding **tactical** and **decomposition** layers that
wrap around FHOPS.

## 3. FHOPS MILP design tasks

### 3.1 Operational MILP benchmark (Arora-style)

**Goal:** Provide a Pyomo (or similar) MILP model that reproduces the FHOPS
machine–block–day/shift schedule for small instances (e.g., tiny7 or a
reduced med42), so we can:

- Validate heuristic schedules against an exact or near-exact optimum.
- Explore objective trade-offs in a controlled setting.

**Top-level tasks:**

1. **Define MILP data contract**
    - 1.1 Identify the minimal subset of the FHOPS scenario contract required:
    - Blocks: `id`, `work_required`, `earliest_start`, `latest_finish`,
      `landing_id`, stand metrics (for productivity, if computed inside).
      - Block-to-system assignments `system_id[b]` (or a default choice rule) so the MILP
        knows which harvest system—and therefore which role order, buffers, and batch size—to
        apply on each block.
      - Machines: `id`, `role`, `daily_hours`, `operating_cost`.
      - Harvest systems: ordered role list (e.g., feller → skidder → processor → loader),
        per-role multiplicity (`count[h,r]` machines of role `r` assigned to system `h`),
        head-start buffers `buffer_shifts[h, r_down]` (machine-shifts of upstream production
        required before role `r_down` may begin), loader batch size `batch_volume[h]`
        (defaults 30 m³ or 60 m³), and optional mobilisation overrides.
     - Calendar: `machine_id`, `day`, `available`.
     - Production rates: `machine_id`, `block_id`, `rate` (m³ per day/shift).
   - 1.2 Decide whether to treat shifts explicitly (day×shift) or aggregate to
     “day” only for the first MILP.
   - 1.3 Define a small JSON/YAML bundle for MILP experiments to avoid coupling
     directly to the full FHOPS loader in early prototypes.

2. **Formulate the core MILP**
   - 2.1 Decision variables:
     - `x[m,b,t] ∈ {0,1}`: machine `m` works on block `b` at time slot `t`
       (day or day×shift).
     - `y[b] ∈ {0,1}` or continuous `completion[b] ∈ [0,1]` if we want
       block-completion flags.
     - Optional: start/finish time variables for blocks if we want Arora-style
       precedence structure later.
     - Role-level staging variables:
      - `stage[r,b,t] ≥ 0` to track the cumulative inventory (m³) available to
        role `r` on block `b` by the end of slot `t`.
      - `start_allowed[r,b,t] ∈ {0,1}` to linearise the “head-start” buffer when needed.
     - Loader batch variables: integer `loads[h,b,t] ≥ 0` counting truckloads produced by
       system `h` on block `b` during slot `t`.
   - 2.2 Constraints:
     - Machine capacity: each `m,t` works on at most one `b`, and only if
       calendar says available.
     - Block work balance:
       - Sum over `m,t` of `rate[m,b] * x[m,b,t]` ≥ `work_required[b] * y[b]`.
       - Or an exact balance with slack variable representing leftover volume.
     - Windows: `x[m,b,t] = 0` if `t` is outside `[earliest_start[b],
       latest_finish[b]]`.
     - Finish-the-block:
       - If machine begins block `b` at `t`, then it must continue until
         `work_required[b]` is exhausted (can be modelled crudely with big‑M or
         via consecutive assignment constraints per block/machine).
     - Role-level staging and buffers:
       - Update staging inventory per slot:
         `stage[r,b,t] = stage[r,b,t-1] + Σ_{m∈upstream(r)} prod[m,b,t] − Σ_{m∈role(r)} prod[m,b,t]`.
        - Downstream production limited by staged volume:
          `Σ_{m∈role(r)} prod[m,b,t] ≤ stage[r,b,t-1] / Δt`
          or, with binary gating, impose
          `stage[r,b,t-1] ≥ buffer_shifts[h,r] * shift_production[h,r] * start_allowed[r,b,t]`
          and `x[m,b,t] ≤ start_allowed[r,b,t]` so machines cannot engage until the buffer is met.
       - Buffers measured in machine-shifts: `shift_production[h,r] = Σ_{m∈role(r)} rate[m,b] / shifts_per_day`.
         Balanced systems set `buffer_shifts[h,r]=0` so roles can start immediately once upstream
         production is non-zero.
     - Multiple machines per role:
       - For each `(h,r)` ensure the aggregated assignment across the `count[h,r]` machines respects
         capacity and staging. This lets, e.g., two skidders drain staged volume twice as fast
         while still honouring head-start rules.
     - Loader batching / trucking cadence:
       - For each loader machine `m` belonging to system `h`, constrain
         `prod[m,b,t] = batch_volume[h] * loads[h,b,t]`.
       - Optionally add smoothness constraints such as `|loads[h,b,t] - loads[h,b,t-1]| ≤ ramp_limit`
         to avoid bursty truck dispatching, or penalise deviations from a target loads-per-shift rate.
   - 2.3 Objective:
     - Maximise `Σ_b value[b] * completion[b] − penalty * leftover_volume[b]`.
     - Optionally include mobilisation cost approximations or soft penalties for
       long machine moves.

3. **Implement Pyomo prototype**
   - 3.1 Create `fhops.model.milp.operational` module:
     - Data loaders from a scenario bundle or a preprocessed JSON.
     - Pyomo sets (`Machines`, `Blocks`, `Times`) and parameters.
     - Variable declarations and constraints mirrored from 2.x.
   - 3.2 Hook into CLI for a small command:
     - `fhops solve-milp-operational --scenario ... --tier small`.
   - 3.3 Test on tiny7:
     - Compare MILP solution KPIs vs heuristic `solve-heur` outputs for small
       iteration budgets.

4. **Extend with Arora-style features**
   - 4.1 Add activities and precedence:
     - Introduce activity index `a` (felling, yarding, processing, loading).
     - Decision variables `x[m,a,b,t]` or continuous start/end times per
       activity and block.
     - Precedence constraints within each block (processing after yarding,
       loading after processing, etc.).
   - 4.2 Add machine movement:
     - Binary sequencing variables `z[m,b1,b2]` indicating that machine `m`
       moves from block `b1` to `b2`.
     - Travel-time constraints to ensure no overlap between work intervals.
   - 4.3 Multiple machines per activity and multi-task machines (Arora’s later
     chapters):
     - Allow a pool of machines per activity, with assignment variables.
     - For multi-task machines, restrict at most one activity at a time per
       machine, with role compatibility.

### 3.2 Tactical MILP layer (Bredström/Frisk/Shabaev-style)

**Goal:** Add a higher-level planning layer that:

- Chooses which blocks (or groups of blocks) to harvest in each period (season/
  month/week).
- Allocates teams or machine systems to areas.
- Feeds a reduced set of blocks and machine capacities to the operational
  heuristics or MILP.

**Top-level tasks:**

1. **Define tactical periods and aggregation**
   - 1.1 Choose period granularity (e.g., months or 4-week buckets).
   - 1.2 Decide aggregation of FHOPS blocks into “harvest areas” or keep them
     as-is but treat each as a potential tactical harvest candidate.
   - 1.3 Define business vs anticipation horizon split:
     - Business: near-term periods where operational details matter.
     - Anticipation: tail periods where only coarse decisions are needed.

2. **Formulate team/area/period model**
   - 2.1 Decision variables:
     - `y[team, area, period] ∈ {0,1}`: team works area in period.
     - `q[area, period]` harvested volume per area/period.
     - Optional: pattern variables for Shabaev-style “site–period–assortment”.
   - 2.2 Constraints:
     - Team capacity per period (hours, max number of areas served).
     - Area volume bounds per period, plus total volume over horizon.
     - Demand and AAC constraints (if we hook to supply/demand).
     - Compression / distance penalties (Bredström/Frisk).
   - 2.3 Objective:
     - Maximise profit or minimise cost (harvest + transport).
     - Include soft penalties for:
       - Over-/under-supplying mills (Shabaev).
       - Too many moves per machine (Frisk).
       - Harvesting far from home base (compression).

3. **Connect tactical and operational layers**
   - 3.1 Use tactical decisions to *filter* the block set for operational
     scheduling:
     - Only send blocks/areas selected for the “business” periods into the
       shift-indexed heuristics or operational MILP.
   - 3.2 Feed back operational KPIs (makespan, leftover volume) into tactical
     re-planning (rolling horizon).
   - 3.3 Optionally, explore column-generation:
     - Master: choose which area/period patterns to activate.
     - Subproblem: generate new patterns using FHOPS heuristics as oracles.

### 3.3 Decomposition and column generation (longer-term)

**Goal:** For large planning problems (many blocks, long horizons), explore
decomposition schemes inspired by Frisk and Shabaev.

**Sketch tasks:**

1. **Identify natural blocks / columns**
   - 1.1 Columns as “harvest-and-haul patterns” for block groups over multiple
     periods (Shabaev-style).
   - 1.2 Columns as “team schedules over a short horizon” (Frisk-style).

2. **Prototype master problem**
   - 2.1 Implement a small master LP selecting patterns subject to:
     - Volume, AAC, demand constraints.
     - Machine/crew capacity aggregates.
   - 2.2 Derive dual prices to feed to subproblems.

3. **Prototype pricing subproblems**
   - 3.1 Use FHOPS heuristics (SA/ILS/Tabu) as embedded oracles to generate
     promising patterns/schedules.
   - 3.2 Optionally, use a restricted MILP as pricing oracle.

4. **Assess practicality**
   - 4.1 Benchmark runtime and quality vs pure heuristics on synthetic tiers.
   - 4.2 Decide whether the complexity is justified for the intended FHOPS
     workflows (e.g., research vs production).

## 4. Operational MILP rollout plan (shift × day grid)

Plan for delivering the Section 3.1 operational MILP benchmark using the existing FHOPS
day×shift discrete time structure.

- [x] **Define the MILP data interface**
  - [x] Extracted an in-memory bundle builder (`fhops.model.milp.data.build_operational_bundle`)
        that captures machines, blocks, day×shift availability, production rates, landing links,
        block→system mappings, and harvest system metadata ready for head-start/batching logic.
  - [x] Added `OperationalMilpBundle`, `SystemConfig`, and `SystemRoleConfig` dataclasses plus a
        regression test to keep the serialization stable (`tests/model/test_operational_bundle.py`).

- [ ] **Formulate sets and variables on the shift grid**
  - [x] Implemented an initial Pyomo builder (`fhops.model.milp.operational.build_operational_model`)
        that instantiates the `M × B × S` tensor, machine-capacity / window / production-cap
        constraints, block balance equations, and a production-maximising objective.
  - [ ] Extend the builder with role-level staging variables, head-start buffers, loader batching,
        and multi-machine role coordination per the design bullet list below.
        * [x] Implemented role compatibility filters, aggregated role production, inventory tracking,
          loader batching variables, and optional head-start binaries (triggered when buffer_shifts > 0).
        * [x] Wired system-level buffer counts, loader batch defaults, transition binaries, mobilisation cost penalties, and landing/leftover slack terms (tests cover bundle round-trips and mobilisation-aware builds). Remaining work: expose calibrated defaults + mobilisation-driven objective tuning via the scenario contract.

- [ ] **Build the Pyomo model and solver harness**
  - [ ] Add `fhops/model/milp/operational.py` with:
        - Builder `build_operational_model(data)` assembling sets, vars, constraints.
        - Objective replicating SA scoring
          (`production - mobilisation_penalty - transition_penalty - landing_penalty
            - leftover_penalty`).
  - [x] Provide `solve_operational_milp(...)` in `fhops.model.milp.driver` so we can build the Pyomo model,
        call HiGHS, and capture assignments/objectives in a regression-friendly format.

- [ ] **CLI integration and regression tests**
  - [x] Add `fhops solve-mip-operational` command that:
        - Accepts `--scenario` plus standard solver flags, supports ``--bundle-json`` for replay, and writes assignments identical to SA/Tabu outputs (optionally dumping the bundle via ``--dump-bundle``).
        - Prints KPI summaries when feasible schedules exist (reusing `compute_kpis`).
        - Added telemetry logging (`--telemetry-log`) and live watch snapshots (`--watch`) so runs mirror the heuristic UX, plus bundle dump/replay fixtures exercising the CLI and driver round-trips.
  - [ ] Create `tests/milp/test_operational.py`:
        - Tiny tiny7 fixture → assert optimal objective/KPIs.
        - Compare MILP vs SA results for a seeded scenario (tolerances on KPIs).
  - [ ] Update `tests/test_regression_integration.py` to include the MILP solver once the
        new objective scale/fixtures are in place.

- [ ] **Documentation and changelog**
  - [ ] Expand this note with any modeling trade-offs discovered during coding.
  - [ ] Add README/docs snippets describing the operational MILP (inputs, limitations,
        runtime expectations) including the new bundle replay workflow.
  - [ ] Record completion in `CHANGE_LOG.md` before merging back to main.

- [ ] **Open questions / parameter calibration**
  - [ ] Derive reasonable default `buffer_shifts` per system role from the productivity models
        (e.g., three skidder shifts ≈ 2 000 m³ staged) and expose CLI knobs so operators can tune them.
  - [ ] Decide whether head-start buffers are block-specific (based on stand density) or purely
        system-level; document how to override them in scenario input.
  - [ ] Specify default loader batch sizes (single vs tandem) and whether mills impose per-day truck
        cadence constraints that should appear in the MILP objective.
  - [ ] Confirm how multi-machine roles interact with mobilisation penalties (e.g., moving both
        skidders simultaneously vs sequential moves).

### Section 4 next actions

1. **Bundle/schema enhancements**
   - Add explicit `buffer_shifts`, loader batch volumes, and role multiplicity to the Scenario contract (or a sidecar JSON) so `build_operational_bundle` no longer relies on placeholders.
   - Ensure `bundle_to_dict`/`bundle_from_dict` round-trip these parameters and add regression fixtures for dumped bundles.

2. **Model refinements**
   - Integrate mobilisation/transition penalties and landing slack variables so the objective mirrors SA/MIP scoring. Reuse the transition binary machinery from `fhops.optimization.mip.builder`.
   - Add optional leftover volume slack to capture partial completion penalties.
   - Expand unit tests (and a tiny Pyomo solve) to confirm the new constraints behave (e.g., mobilisation costs accrue when machines hop blocks).

3. **Solver harness + telemetry**
   - Extend `solve_operational_milp` to accept `driver="highs-exec"` and Gurobi variants, surface warm-start hooks, and emit telemetry records (objective trace, solver status).
   - Hook `LiveWatch` into long-running MILP solves (even if only showing objective/kpi placeholders) so CLI parity with heuristics improves.

4. **CLI & docs**
   - Document the bundle replay workflow (`--dump-bundle` / `--bundle-json`) in `docs/howto/benchmarks.rst` and Sphinx CLI reference.
   - Add a how-to describing when to use the operational MILP vs heuristics, expected runtimes, and data prerequisites.

5. **Regression coverage**
   - Implement `tests/milp/test_operational.py` comparing MILP vs SA on tiny7 (objective, completed blocks).
   - Add a `solve-mip-operational` entry to `tests/test_regression_integration.py` once med42 fixtures stabilize.

## 5. med42 dataset rebuild (20 ha block focus)

Rework `examples/med42` so ≈60 % of the workload is carried by ~20 ha blocks at ~400 m³/ha
(≈8 000 m³ per block) with the remainder in smaller satellites, while keeping the lone ground-based
system slightly under-capacity (bottleneck days just above the 42-day horizon).

- [x] **Define new block targets**
  - Large blocks: sampled 10–18 ha (≈320–360 m³/ha) so each contributes ≈3.5–5.8 k m³.
  - Satellites: sampled 1.3–2.3 ha (≈140–190 m³/ha) to supply 300–500 m³ filler blocks without
    dragging the big-block volume share below 60 %.
  - Final mix: 29 blocks total (3 large + 26 satellites) delivering 22.5 k m³ with a 65 % volume
    share in the 20 ha class.

- [x] **Consolidate blocks**
  - Added `scripts/rebuild_med42_dataset.py` to deterministically regenerate the block table using a
    fixed seed, Lahrsen-aligned stand metrics, and landing-aware window sampling.
  - `python scripts/rebuild_med42_dataset.py` now refreshes `examples/med42/data/blocks.csv`
    end-to-end (area, work, windows, sigmas).

- [x] **Regenerate production rates and calendar/machines**
  - `scripts/rebuild_med42_dataset.py` also recomputes `prod_rates.csv` directly from the FHOPS
    helpers (Lahrsen feller-buncher, ADV6N7 skidder, Berry processor, TN-261 loader) and scales them
    to the 24 h day.
  - Calendar/machine files already model the single-system 42-day roster, so no changes required.

- [ ] **Validate workload vs capacity**
  - [ ] Run a quick `fhops solve-heur ... --iters 20000` to confirm heuristics now leave a couple of
        blocks unfinished (processor bottleneck ≈46 days vs. 42-day horizon).
  - [x] Update README/changelog with the new block counts, share, and generator instructions.

- [ ] **Refresh fixtures/assets**
  - [ ] Re-export med42 benchmark/playback/tuning assets (`docs/softwarex/assets/...`).
  - [ ] Update tests/fixtures referencing med42 (playback CSVs, KPI snapshots) once the MILP
        work is ready.

- [x] **System rebalance + productivity tweaks**
  - [x] Regenerate the harvest system definition so med42 models a near-balanced crew:
        2 feller-bunchers, 1 grapple skidder, 3 processors, and 3 loaders sharing the same
        block roster. Allow multiple machines within a role to split across different blocks
        whenever windows/head-start buffers make that advantageous for throughput. (Done via the
        shared generator; small21 mirrors the same roster, large84 doubles it.)
  - [x] Update the generator script to estimate grapple-skidder productivity using an average
        skidding distance derived from block area (assume square blocks and set distance to
        half the inferred block width so we can approximate travel distances without a full
        geometry model). (Implemented by `_estimate_skidding_distance` in `scripts/rebuild_reference_datasets.py`.)
  - [x] Recompute `examples/med42/data/{machines,calendar,prod_rates}.csv` plus README docs to
        reflect the balanced system, then rerun `fhops solve-heur` smoke tests to measure how the
        extra processors/loaders change makespan/leftover volume. (Docs/manuscript asset refresh pending once
        regression fixtures are rebuilt.)
  - [x] Capture the new rates/assumptions in the changelog and note any solver-behaviour updates
        (e.g., whether heuristics are splitting processors across blocks as expected).

- [ ] **Scenario ladder rebuild**
  - [x] Remove the legacy `examples/minitoy` dataset (docs/tests) since it no longer matches the four-role system assumptions.
  - [x] Scrub the docs/notes/manuscript references (and archived benchmark/playback assets) so guidance, assets, and tooling now point to `examples/tiny7` as the entry-level scenario.
  - [x] Derive `small21` and `tiny7` variants from the med42 generator by truncating the horizon (21-day / 7-day) and subsampling blocks while keeping the single balanced system. (Tiny7 remains the single-crew regression smoke test until we refresh all fixtures; small21 already uses the full balanced roster.)
- [x] Derive `large84` by doubling the med42 block set/system count and extending the horizon to 84 days (two balanced systems, doubled workload).
  - [ ] Ensure each dataset ships with deterministic `scripts/rebuild_*` entries (shared generator) plus README/KPI updates, then refresh CLI/docs/tests to reference the new ladder.
- [x] 2025-11-30 refresh run: rebuilt the entire ladder via `scripts/rebuild_reference_datasets.py tiny7|small21|med42|large84 --seed 20251209`, regenerated the dataset summaries (`run_dataset_inspection.py`), solved the operational MILP for tiny7/med42/large84 with the current gap/limit presets to refresh `tests/fixtures/playback/*` (assignments + shift/day CSV+Parquet), recomputed deterministic & stochastic KPI snapshots, rewrote the operational bundle fixtures, and captured new SA benchmark rows from `fhops bench suite` (tiny7: `--time-limit 120 --sa-iters 200`, med42: `--time-limit 600 --sa-iters 500`, large84: `--time-limit 900 --sa-iters 500`). Full `pytest` run stayed green after the updates.
- [x] 2025-11-30 workload trim: updated `scripts/rebuild_reference_datasets.py` so small21/med42/large84 use the tiny7 block profiles and scaled block counts (6/12/24) before regenerating each dataset with seed 20251209. Goal: keep per-system workload roughly constant as horizon grows so MIP/heuristic scaling tests are meaningful.
- [x] 2025-11-30 delivery-only scoring benchmarks (`.venv/bin/fhops bench suite --include-mip --scenario examples/tiny7/scenario.yaml --scenario examples/small21/scenario.yaml --scenario examples/med42/scenario.yaml --scenario examples/large84/scenario.yaml --out-dir tmp/benchmarks_delivery_full --time-limit 600 --sa-iters 500`):
  - **Tiny7:** MILP 4 114.84 (0.18 s); SA 1 928.50 (2.0 s). Both finish 2/2 blocks; SA keeps mobilisation cost low by idling spare machines.
  - **Small21 (trimmed workload):** MILP 8 904.15 (1.7 s); SA −766.39 (5.5 s). Heuristics now deliver ~8.1 k m³ (≈90 % of workload) with only ~900 m³ staged when the horizon ends.
  - **Med42 (trimmed workload):** MILP 14 343.14 (15 s); SA −3 612.53 (11.8 s). Heuristics deliver ≈12.4 k m³ and leave ≈1.9 k m³ staged; still negative but far closer to capacity.
  - **Large84 (trimmed workload, double system):** MILP 37 121.58 (≈265 s); SA −41 033.36 (59 s). SA delivers ≈34 k m³ and leaves ≈3 k m³ staged; tuning should now be able to close most of the remaining gap.
- [x] 2025-12-20 delivery-only tuning sweep (`.venv/bin/fhops bench suite ... --time-limit 900 --sa-iters 20000 --sa-cooling-rate 0.99995 --sa-restart-interval 2000 --operator-preset mobilisation --include-ils --ils-iters 750 --ils-perturbation-strength 6 --ils-stall-limit 25 --include-tabu --tabu-iters 15000 --tabu-tenure 200` per scenario; large84 solvers were executed individually to bypass the 30‑minute CLI timeout). Results captured under `tmp/benchmarks_delivery_tuned/*`:
  - **Tiny7:** MILP 4 114.84 (0.18 s). SA holds at 1 928.50 despite 20 k iters, while ILS/Tabu climb to 3 715.54 in 5.5 s/60 s respectively. All heuristics finish both blocks with zero staged wood; the SA score remains depressed because it never escapes the mobilisation-light seed.
  - **Small21:** MILP 8 904.15 (1.97 s). SA/ILS/Tabu converge to −701.44 with ≈8.48 k m³ delivered, 0.43 k m³ staged, and 1.6 k mobilisation spend; longer SA runs only improve acceptance (~98 %) without lifting the objective. Runtime: SA 213 s, ILS 12.9 s, Tabu 162 s.
  - **Med42:** MILP 14 343.14 (14.4 s). All heuristics remain stuck at −3 612.52 while delivering 9.10 k m³ and staging 5.25 k m³ (zero sequencing issues). SA needed ~470 s for 20 k iters, ILS finished in 28.6 s, Tabu in 357 s; raising the iteration budget did not rescue the score because the leftover penalty dominates once loaders idle near the horizon.
  - **Large84:** MILP 37 121.58 (258.7 s; minor sequencing violation due to fully staged terminal loads). SA (15 k iters, 0.99995 cooling, 2 000 restart) and ILS settle at −41 033.36 with 34.4 k m³ delivered, 2.69 k m³ staged (~18/24 blocks completed), and 10.32 k mobilisation cost; Tabu matches (+2.64 objective points) in 1 195 s. SA required the full 1 768 s budget, so future sweeps need either GPU-free batching or a reduced iteration target. KPIs validated via `fhops evaluate ... --assignments tmp/benchmarks_delivery_tuned/large84/user-1/*.csv`.
  - Follow-ups:
      - Re-tune SA/ILS/Tabu for medium/large tiers (slower cooling, higher restart intervals, mobilisation-heavy presets, larger iteration budgets).
      - Consider scaling the leftover penalty or adding staged-volume telemetry thresholds so watch output highlights when heuristics stall.
- [ ] Large-scenario tuning plan:
  - **SA:** test `--cooling-rate 0.99995`, `--restart-interval 2000`, and mobilisation preset by default on med42/large84; increase `--iters` to ≥20 000 and log staged volume via `--watch-debug`.
  - **ILS/Tabu:** mirror mobilisation preset and extend perturbation/tabu-tenure values; ensure coverage injection stays enabled to keep loaders fed.
  - **Benchmarks:** rerun `fhops bench suite` after tuning and compare staged volume + mobilisation costs against MILP to verify progress.

## 6. Current priorities (operational focus – manuscript parked)

Per 2025-11-30 sync, the SoftwareX/manuscript track is frozen until the
operational MILP, dataset ladder, and heuristics all align with the
Arora-style formulation. Immediate priorities:

### 6.1 Operational MILP bring-up (exact solver first)
- [ ] Finish the model feature set (role buffers, batching, mobilisation penalties, landing slack) and land the missing unit tests + regression harness so `solve-mip-operational` is trustworthy.
  - [x] Head-start buffers now use upstream-role capacity and require previous-shift inventory, loader batching enforces truckload quanta, and regression tests cover both behaviours plus the driver replay path (`tests/model/test_operational_milp.py`, `fhops.model.milp.driver`).
- [x] Generate the `tiny7` scenario via the shared dataset builder and validate that HiGHS/CPLEX produce a “sane” optimal schedule (objective, completed blocks, mobilisation moves).
  - 2025-11-30: HiGHS solved `examples/tiny7` with the balanced roster (2 FB, 1 GS, 3 processors, 3 loaders) in 19 s using a 2 % relative gap, delivering objective 11 803.71, 11 990 m³ production, and full completion of all 9 blocks. Mobilisation spend: 1 128.84.
- [x] Once `tiny7` is green, scale the same checks to `small21`, `med42`, and `large84` before touching any heuristic code.
  - `examples/small21` (21 days, 12 blocks) solved in 85 s at 5 % gap; objective 41 264.52 with 41 606 m³ production and all blocks finished.
  - `examples/med42` (42 days, 20 blocks) solved in 42 s at 5 % gap; objective 68 716.92 with 69 781 m³ production and all blocks finished.
  - `examples/large84` (84 days, 40 blocks, doubled system) solved in ≈8 min at 10 % gap; objective 125 016.95 with 125 017 m³ production and full completion. Mobilisation spend: 21 798.08; utilisation still 100 % at the shift level thanks to the balanced roster.
- [ ] After the heuristic refactor lands, rerun the doc audit (README, data-contract guide, CLI references, SoftwareX assets) so the balanced ladder, new schedules, and heuristics are fully documented.
- [ ] Capture calibration defaults (buffer_shifts, loader batch volumes, per-role productivity scaling) inside the scenario contract so both the MILP and future heuristics share identical parameters.
- [ ] Capture calibration defaults (buffer_shifts, loader batch volumes, per-role productivity scaling) inside the scenario contract so both the MILP and future heuristics share identical parameters.

### 6.2 Dataset ladder rebuild (shared generator, no heuristic tuning)
- [ ] Finish the deterministic dataset generator that emits `tiny7`, `small21`, `med42`, and `large84` from a single configuration + seed (including machine rosters, landings, prod rates, calendar, mobilisations).
  - [x] Introduced `scripts/rebuild_reference_datasets.py` with a first pass that deterministically regenerates the new `tiny7` scenario (blocks, prod rates, machines, calendar, landings, mobilisation distances, scenario YAML). Extend it to cover `small21`/`med42`/`large84` next.
  - [x] Refactored the generator around reusable `DatasetConfig`/`BlockProfile` scaffolding so landing/machine mixes, block distributions, and scenario metadata can be defined per dataset (sets us up to script `small21`/`med42`/`large84` without copy/paste).
  - [x] Extended the generator to emit `small21`/`med42`/`large84` with Lahrsen-style (60 % ≥12 ha) blocks, rescaled ADV6N7 skidding distance derived from block geometry, and multi-machine rosters (med42/small21 = 2 FB, 1 GS, 3 processors, 3 loaders; large84 doubles the system + horizon). README stats regenerate automatically alongside the scenario YAML/CSV bundle.
  - [x] Align the `tiny7` roster with the med42 system once we are ready to refresh all regression fixtures. Tiny7 now shares the same balanced crew (2 FB, 1 GS, 3 processors, 3 loaders) and the README captures the refreshed stats; fixture refresh will follow in a dedicated PR.
- [ ] Delete `examples/minitoy` plus all docs/tests references; replace fixtures with the new ladder.
  - [x] Removed the `examples/minitoy` bundle, replaced CLI/tests/fixtures with `examples/tiny7`, and regenerated benchmark/KPI/playback/MILP fixtures so code/tests no longer rely on the legacy dataset. Documentation + manuscript assets still reference tiny7 and need follow-up edits.
- [ ] For each scenario, document the “slightly under-capacity” intent, run an operational MILP smoke test, and log KPIs in `CHANGE_LOG.md` / dataset README—skip SA/ILS/Tabu tuning until the heuristics are rebuilt.

### 6.3 Heuristic refactor (post-MILP validation)
- [x] Design a shared “operational problem” module that exposes the same bundle/constraint structures to MILP and heuristics (roles, buffers, batching, mobilisation state).
  - Added `src/fhops/optimization/operational_problem.py`, which wraps the operational MILP bundle, derives per-block role permissions/head-start metadata, caches availability/lock/blackout lookups, and exposes a sanitizer factory so every heuristic enforces the same feasibility rules as the MILP.
- [x] Port SA, ILS, and Tabu to consume that module so all three heuristics reuse identical problem-definition code.
  - `solve_sa` now builds the shared context once and threads it through `_init_greedy`, `_evaluate`, `_neighbors`, and `_evaluate_candidates`; ILS/Tabu reuse the same context for local search, perturbations, and evaluation, and the registry/unit tests were updated to pass the shared sanitizer.
  - 2025-11-30: Finished wiring SA/ILS/Tabu into the shared helper implementations in `fhops.optimization.heuristics.common` so all three solvers now call the exact same greedy seed, evaluator, neighbour generator, and candidate scorer. Left lightweight wrapper aliases in SA/ILS to keep legacy tests working, reran `pytest tests/heuristics`, and spot-checked `fhops bench suite --scenario examples/tiny7/scenario.yaml --include-sa --include-ils --include-tabu --sa-iters 200 --ils-iters 10 --tabu-iters 200 --time-limit 30 --out-dir tmp/bench_tiny7_refactor` to confirm the refactor preserved behaviour.
  - [x] Follow-up: cleared the remaining test imports (`tests/heuristics/test_ils.py`, `tests/heuristics/test_operators.py`, `tests/heuristics/test_registry.py`, `tests/test_system_roles.py`, `tests/test_schedule_locking.py`) so they now use `evaluate_schedule` / `generate_neighbors` from `heuristics.common`. The compatibility wrappers in SA/ILS were removed, and the heuristic/regression suite (`pytest tests/heuristics` + `fhops bench suite ...`) was re-run to confirm behaviour is unchanged.
- [x] Stamp `harvest_system_id` onto every block in the reference ladder so heuristics actually see the same system metadata as the MILP (and can honour buffers/loader batching in neighbour moves). `scripts/rebuild_reference_datasets.py` now writes the column and the four ladder datasets (`examples/{tiny7,small21,med42,large84}/data/blocks.csv`) were updated in-place with `ground_fb_skid`, so heuristics inherit the default system buffers without relying on implicit fallbacks.
- [x] Refresh deterministic fixtures once sequencing metadata is wired through: reran `fhops eval-playback` for tiny7/med42 (CSV+Parquet), recomputed deterministic KPI snapshots, and rebuilt the tiny7 SA benchmark JSON so tests exercise the post-refactor objectives/gaps. `run_benchmark_suite` now picks the *max* objective when labelling the “best heuristic” and reports positive gaps for exact solvers.
- [ ] **Sequencing feasibility enforcement (blocking)**
  - [x] Add per-role work queues to `OperationalProblem` (`role_work_required`) and teach `_repair_schedule_cover_blocks` / `_init_greedy` to measure deficits at the `(block, role)` level instead of lumping all work together. Downstream roles must only see demand once upstream machines have produced staged volume.
  - [x] Rework `evaluate_schedule` so it debits staged inventory per role, enforces head-start buffers via the same bookkeeping, and only decrements block-level `remaining_work` when loaders finish (or when a block has no explicit system). This should make the “bad vs good” sequencing unit tests fail/pass deterministically and keep the heuristics from self-healing infeasible plans during scoring.
- [x] Mirror the staged-inventory changes inside playback/KPI aggregation (`assignments_to_records` + `compute_kpis`) so sequencing violation counts, staged production, and completed-volume tallies all reference the same logic.
  - [ ] Once the evaluator/repair/watch paths align, refresh the regression assets: rerun `fhops solve-heur` smoke tests (tiny7/med42 short iters), update the benchmark JSON summaries, regenerate KPI/playback fixtures, and capture the new command cadence in the changelog. *(Playback + KPI fixtures refreshed; need new benchmark baselines once heuristics stabilise.)*
- [x] Enforce loader buffers directly in the MILP by treating `loader_batch_volume` as the minimum staged inventory, wiring `role_active` binaries to machine assignments, and emitting per-shift production so playback/KPIs see the throttled volumes; tiny7/med42 MILP runs (and matching SA smoke tests) now report zero sequencing violations under `--sequencing-debug` (2025-11-30).
- [x] Trimmed the `tiny7` workload to two blocks (~4,950 m³) via `scripts/rebuild_reference_datasets.py tiny7 --seed 20251209` so the single-system roster can actually finish everything inside 7 days. MILP now reports `completed_blocks=2` with sequencing-clean schedules.
- [ ] SA mobilisation tuning: current SA runs finish both tiny7 blocks but spend ~800 vs. the MILP’s ~480 mobilisation cost because loaders bounce around unnecessarily. Once the MILP changes settle, revisit SA operator weights/repair logic so it prefers stationary patterns after blocks complete.
- [ ] **Queued sequencing tasks (2025-11-30)**
  - [ ] Harden `_repair_schedule_cover_blocks` so downstream machines skip blocks until upstream role demand is satisfied for that day/shift, and add targeted unit coverage that reproduces the current “loader starts too early” issue.
  - [ ] Instrument `SequencingTracker`/`evaluate_schedule` with debug counters for staged volume vs. consumption so SA/ILS/Tabu watch output can flag which role first violates head-start buffers; enable the flag via `--watch-debug`.
  - [ ] Wire the same staged-inventory logic into `generate_neighbors` sanitization to prevent operator moves that overbook downstream roles or landings, then add regression checks in `tests/heuristics/test_operators.py`.
  - [ ] Re-run short SA/ILS/Tabu smoke tests on `examples/tiny7` and `examples/med42` (e.g., `--iters 2000 --profile explore`) and capture KPI snapshots proving zero sequencing violations; attach the command list to `CHANGE_LOG.md`.
  - [ ] Regenerate `tests/fixtures/benchmarks/*.json` once the heuristics can routinely hit feasible solutions, ensuring the recorded objectives are non-negative and within 5 % of the operational MILP baseline.
- [ ] **Fixture + regression refresh for loader buffers (2025-11-30)**
  - [ ] Re-run deterministic playback exports for tiny7/med42 (`fhops eval-playback ... --shift-out --day-out --shift-parquet --day-parquet`) using the new MILP assignments so sequencing counters match the tightened loader staging.
  - [ ] Recompute deterministic/stochastic KPI snapshots (`tests/fixtures/kpi/*.json`) via `compute_kpis` / `run_stochastic_playback` so regression tests lock onto the new violation totals.
  - [ ] Refresh benchmark suite fixtures (`tests/fixtures/benchmarks/tiny7_sa.json` etc.) by rerunning `fhops bench suite` with the updated heuristics, ensuring objectives and “best heuristic” labels reflect non-negative scores under the stricter evaluator.
  - [ ] Update regression baselines in `tests/fixtures/regression/baseline.yaml` once SA/Tabu runs on the toy scenario stabilise with the loader buffers (expect different mobilisation and objective values).
  - [ ] After each fixture refresh, run the relevant pytest slices (`tests/test_benchmark_harness.py`, `tests/test_cli_playback.py`, `tests/test_regression_integration.py`, `tests/test_system_roles.py`, `tests/test_schedule_locking.py`) to confirm sequencing counts/objectives align before attempting a full suite.
- [ ] Extract the solver-agnostic neighbourhood/search logic into a standalone package candidate (generic metaheuristic core) so we can later target tactical MILPs, trucking, and future FLP bridges without rewriting operators.
- [ ] After SA is running on the new primitives, replay the dataset ladder to ensure heuristic KPIs mirror the MILP objective within expected gaps; only then consider parameter tuning.

### 6.4 Tactical MILP (queued after the above)
- [ ] Keep the tactical-level MILP design on hold until the operational stack + heuristics settle; once ready, reuse the modular problem-definition layer to avoid duplicating code.
- [ ] Document any tactical data requirements that surface during the operational refactor so we can extend the scenario contract cleanly when work resumes.


#### 6.3.1 Heuristic performance fix (2025-12-20)

**Observed bottlenecks**
- *Per-iteration cost explodes with scale.* `evaluate_schedule` walks every machine × shift, rebuilds staged inventory, and recomputes mobilisation/landing penalties from scratch. Large84 = 16 machines × 252 shifts ≈ 4 000 slots, so even one candidate costs ~100 ms; 20 k iterations → 30 min runtime.
- *Operators touch the entire plan.* Each move deep-copies the full schedule, `_repair_schedule_cover_blocks` rescans before/after, and block insertion / cross exchange / coverage injection iterate over almost every machine-shift pair to find a viable target.
- *Single-candidate sampling.* Batch size = 1 by default, so every iteration repeats the full repair + score pipeline for just one neighbour; there is no amortisation.
- *Objective discourages exploration.* The greedy seed already delivers ≈34.4 k m³ with 2.7 k m³ staged. With leftover weight = 1.0 and mobilisation penalties high, any move that temporarily increases staged volume is rejected, so SA/ILS/Tabu acceptance stays near zero and the score never improves beyond the initial greedy plan.

**Remediation plan**
1. **Cheaper moves**
   - Cache staged inventory, mobilisation history, and landing usage so scoring updates only the slots touched by a move.
   - Replace dict-of-dicts schedules with mutable arrays + undo records to avoid whole-plan copies.
   - Constrain operator search scopes by pre-indexing feasible slots per block and sampling a limited window (`k` random targets) instead of scanning all machines/shift combinations.
   - Enable small `batch_size` (e.g., 4) with thread-pool scoring to reuse expensive bookkeeping per iteration.
2. **Better exploration**
   - Scale leftover penalty by workload fraction or apply scenario-specific weights (e.g., ≤0.2 for large84) so short-lived staging spikes are tolerable.
   - Tie mobilisation penalties to staged-volume trends (decay costs when leftovers shrink) so the solver is rewarded for progress rather than punished for movement.
   - Add diversification triggers (stalled iterations ⇒ block rotation, seed injection from partial MILP, or enforced mobilisation shake) so `_repair_schedule_cover_blocks` does not snap everything back to the greedy seed.
3. **Instrumentation**
   - Emit per-iteration metrics: acceptance rate, `_repair_schedule` time, `_evaluate_schedule` time, operator proposal/accept counts, staged-volume deltas.
   - Track staged-volume trajectories and mobilisation spend over time to validate that changes actually reduce leftovers even when the objective lags.

**Task queue**
- [x] Profile SA/ILS/Tabu on large84 with `cProfile` to capture time spent in neighbour generation vs. scoring vs. repair.
  - SA (200 iters, mobilisation preset): 56.8 s total; `evaluate_schedule` 41.1 s (72 %), `_repair_schedule_cover_blocks` 40.7 s (72 %), `pending_blocks_for`/`select_block` 29 s/17 s. >1 M calls into block-selection helpers, 0 accepted moves. After removing the redundant pre-evaluation repair call, runtime drops to 50.4 s and `_repair_schedule_cover_blocks` shrinks to 34.6 s (only the evaluation-time repairs remain).
  - ILS (200 iters): 83.5 s total; `_local_search` spends 67 s with 1.5 k `evaluate_schedule` calls (60 s) plus 3.2 k repair passes. 2 M+ hits on `pending_blocks_for`.
  - Tabu (200 iters): 57.6 s total with the same evaluate/repair split as SA.
  - Takeaway: ~70 % runtime is tied up in whole-plan repair + scoring; operator logic itself <2 s, so incremental plan/score caching is the highest leverage fix.
- [x] Reduce plan-cloning overhead so operators only copy the machines they mutate (swap/move/block insertion/etc.), cutting per-neighbour copying from O(#machines) to O(#touched-machines) and prepping the codebase for array-backed plans.
- [x] Cache shift ordering/index inside `OperationalProblem` and refactor the greedy seed, repair loop, and evaluator to reuse it (no more per-call `sorted(pb.shifts)`), shaving a few more seconds from SA/ILS/Tabu runs and paving the way for per-shift state caches.
- [x] Add array-backed schedule storage: `Schedule` now carries a dense per-machine shift matrix, `_repair_schedule_cover_blocks`/`init_greedy_schedule` keep plan + matrix in sync, and helper routines (`_ensure_machine_matrix`, `_set_assignment`) let future operators work directly on arrays with O(1) slot updates.
- [x] Wire the operator registry into the same array-backed helpers: `OperatorContext` now carries `shift_keys`/`shift_index`, `_clone_schedule` returns full Schedule clones (plan + matrix), and all operators (`swap`, `move`, `block_insertion`, `coverage_injection`, `cross_exchange`, `mobilisation_shake`) mutate schedules through `_set_slot`, ensuring matrix/dict parity without extra repairs.
- [x] Introduce per-machine mobilisation caches (`MobilisationStats`) so `_repair_schedule_cover_blocks` marks machines dirty, `_ensure_mobilisation_stats` recomputes only the touched rows, and `evaluate_schedule` reuses the cached mobilisation/transition totals instead of re-deriving them inside the shift loop.
- [x] Track dirty blocks so `_repair_schedule_cover_blocks` only replays blocks touched by operator moves; `_set_assignment` now stamps previous/new block IDs into a dirty set and the repair loop skips untouched blocks, avoiding full-plan rescans on every evaluation.
- [x] Start tracking per-block slot lists: `Schedule.block_slots` now records ordered `(shift_idx, machine_id)` entries, `_set_assignment`/operator clones keep the index in sync, and helpers can grab block-specific slot ranges without rescanning every machine.
- [ ] **In-flight incremental repair design (do not forget):**
  - Current state: `_repair_schedule_cover_blocks` still walks every shift for each dirty block because we discarded the earlier `_repair_block_assignments` experiment. We now have the necessary ingredients for a more surgical approach (dirty-block set + per-slot production cache), but block-level slot ordering and prefix-state tracking are still missing. Operators clone schedules without any block-slot metadata, so every repair pass has to rebuild the chronological order from scratch.
  - TODO (next coding session):
    1. ✅ Reintroduced a `block_slots` index on `Schedule` (ordered `(shift_idx, machine_id)` tuples per block) and kept it in sync inside `_set_assignment` / `_clone_schedule`. This lets us enumerate only the affected slots when a block is marked dirty.
    2. ✅ Rebuilt `_repair_block_assignments` so it consumes `block_slots` and the dirty set instead of replaying the full plan. Successful repairs now remove blocks from `dirty_blocks`; failed ones stay dirty for the next iteration. The helper iterates only the machines that can serve the block (plus any locked machines), walks their shift rows, and reassigns/cleans slots in chronological order while preserving the staged-volume/head-start rules. Idle slots are filled only when the block still has demand, so per-iteration repair cost is now proportional to the touched machines rather than the entire roster.
    3. Once block-level replay exists, extend the slot cache to store cumulative staged volume / head-start counters per `(block, role, shift_idx)` so that repairing a block only updates the suffix influenced by a slot change (true incremental bookkeeping). This is the “prefix array” step we discussed—memory-heavy but acceptable per user guidance.
    4. Update `evaluate_schedule` and the playback/KPI adapters to consume the new cached prefix data so scoring and telemetry are always consistent with the incremental repair logic.
  - Reminder: capture the exact design + test plan in this file after each subtask so we stop losing context. Include which commands/smoke tests prove the new caches are working (tiny7 SA/ILS, med42 bench slice, etc.).
- 2025-11-30: While testing the block-scoped helper we discovered the remaining-work caches were never reset, so every subsequent repair saw zero demand and emptied the plan. `_repair_schedule_cover_blocks` now rebuilds the block/role demand dictionaries on every pass, retains the original shift sweep (with the dirty-set short circuit), and `generate_neighbors` sanitizes candidates with `fill_voids=False` so operators drop infeasible loader slots without immediately snapping back to the greedy assignment. The med42 playback/KPI fixtures, the stochastic snapshot, the regression baseline, and the tiny7 SA benchmark were refreshed to capture the new staged-volume footprint (≈12 k m³ staged vs. 63 k m³) and the updated SA objective (~2061 instead of 1928).
- **2025-11-30 heuristic recovery plan (tiny7/small21 focus)**
  1. *Expose progress clearly.* Update the watch telemetry so it reports both “best vs. initial” and “best vs. last tick” deltas, plus dump the greedy objective and Hamming distance in every run log. No more reading tea leaves when the solver stalls.
  2. *Stop repairs from undoing moves.* Keep the fresh demand caches, but limit `_repair_schedule_cover_blocks` to replay only the blocks flagged dirty by the operator (no global fill). That way block-level tweaks survive long enough to be evaluated.
  3. *Rebalance the objective while we debug.* Temporarily scale mobilisation weight (or upweight delivered volume) on tiny7/small21 so the solver is rewarded for staging changes instead of immediately reverting to the greedy plan purely to avoid move costs.
  4. *Instrument greedy vs. best differences.* Every SA/ILS/Tabu run should emit the greedy score, best score, and number of slots changed so we can see at a glance whether a change actually optimises anything before touching large scenarios again.
- [x] Consolidate block/role remaining caches: `init_greedy_schedule` seeds the shared dictionaries, `_repair_schedule_cover_blocks` now reuses and refreshes them in place, and the NameErrors from the half-integrated cache work are gone—paving the way for incremental staged-volume bookkeeping.
- [ ] Prototype an incremental schedule representation (array-backed plan + cached per-role inventory/mobilisation stats) and swap `_repair_schedule_cover_blocks` to operate on diffs.
- [ ] Implement bounded sampling for heavy operators (block insertion, cross exchange, coverage injection) and add configuration knobs for per-operator candidate budgets.
- [ ] Add optional `batch_size` + `max_workers` defaults to SA/ILS/Tabu and surface them through CLI presets so large scenarios evaluate multiple neighbours per iteration.
- [ ] Introduce scenario-scaled leftover weights and mobilisation-decay rules; document them in the scenario contract and update `evaluate_schedule`.
- [ ] Extend telemetry/watch output with per-iteration timing + staged-volume traces; persist the same info to JSONL for offline analysis.

**2025-12-21 objective-weight overrides + CLI plumbing**
- Added `resolve_objective_weight_overrides` + `override_objective_weights`, so heuristics rebuild the `OperationalProblem` with either explicit overrides or scenario defaults. Tiny7 and Small21 now auto-scale mobilisation weight to 0.2 (production/transitions/landing stay unchanged) which lets the search accept short bursts of staging without immediately falling back to greedy.
- Exposed overrides through `--objective-weight mobilisation=0.5` on `solve-heur`, `solve-ils`, `solve-tabu`, and `fhops bench suite`. The bench harness forwards the mapping to every solver invocation, and telemetry/meta output now record both the override dict and the final `objective_weights` snapshot so future runs explain why objectives shifted.
- Evidence that the heuristics are finally moving: `solve_sa(pb, iters=400, seed=7, use_local_repairs=True)` on Tiny7 improved from the greedy −4 146.78 to −542.59 (+3.6 k delta) and Small21 jumped from −5 839.62 to −271.85 (+5.6 k). The CLI runs mirror that behaviour (`fhops solve-heur examples/tiny7/scenario.yaml --iters 200` now reports 2 093.54 vs. the previous 2 061.60), and the tiny7 benchmark fixture was refreshed accordingly.
- Next: keep the overrides enabled while we finish the incremental staging caches, then rerun Small21/Med42 smoke tests to see if the heuristics maintain positive deltas once mobilisation penalties ramp up again. Only after we have reliable acceptance on tiny/small should we unlock fixture refreshes for the rest of the ladder.
- Next: apply the same “make it feasible” pass to `examples/large84` (scale block workloads, keep full-horizon windows, confirm MILP sequencing is enforced) so the entire dataset ladder (tiny/small/med/large) provides trustworthy MILP baselines.

**2025-12-23 auto-batch + mobilisation shake safeguards (tiny7 focus)**
- Added scenario-aware defaults in `solve_sa`: `FHOPS Tiny7` now auto-enables batched neighbour sampling (`batch_size=4`, `max_workers=4`) unless the caller explicitly sets the knobs, and the same flags are persisted in both the telemetry config snapshot and solver metadata so dashboards explain why extra workers engage.
- Implemented an automatic mobilisation-shake trigger for Tiny7: after 50 stalled iterations the solver temporarily triples the shake operator weight, then reverts once an improving move lands. Telemetry records how many triggers fired, keeping acceptance debugging transparent.
- Regression tests (`tests/heuristics/test_sa_batch.py`) cover the preset weight snapshot, auto-batch injection, and explicit override behaviour; docs + changelog note the new defaults so users understand why Tiny7 behaves differently while we dig out of the gap.


## New coding agent quote (it is being flakey)

Here’s exactly where we stand on the subsection you called out, plus the focused work plan to finish it:
Objective Tuning + Presets
Already in place: resolve_objective_weight_overrides + CLI flags mean SA/ILS/Tabu accept explicit overrides, and we auto-detect Tiny7/Small21 to drop mobilisation weight to 0.2 (see AUTO_OBJECTIVE_WEIGHT_OVERRIDES in src/fhops/optimization/heuristics/common.py).
Still to do: extend that mapping so Tiny7/Small21 also set transitions=0.1, landing_surplus=0.05 while keeping production at 1.0; surface the same overrides when a user picks the mobilisation-oriented presets (--preset explore|mobilisation) so behaviour is consistent.
Tests/docs: add a small preset fixture (e.g., tests/fixtures/presets/tiny7_explore.yaml) plus a regression in tests/heuristics/test_sa_batch.py that calls fhops solve-heur via Click runner or directly exercises build_operational_problem to ensure the preset yields deterministic objective weights. Update CLI docs/change log accordingly.
Search Diversification
Tiny7 bounded sampling: implement an auto-config hook (probably alongside the existing profile auto-detect) that sets batch_size=4 and max_workers=4 when the scenario name is Tiny7 (unless the user overrides). Tune the watch/telemetry output to show the new batch settings.
Mobilisation-shake trigger: the operator exists; add a stall detector (e.g., if stalled_steps >= 50 in SA) that temporarily boosts the mobilisation-shake weight or injects a direct shake move before the next evaluation.
Small21 restart seeding: load the partial MILP schedule from examples/small21/operational_mip.yaml (or from the scenario metadata) and feed the top-2 shift assignments as restart seeds when SA restarts. That means capturing the MILP plan once at startup and, on restart, blending those assignments into init_greedy_schedule.
Benchmarks: once the above toggles are in, run fhops bench suite --scenario examples/tiny7/scenario.yaml --scenario examples/small21/scenario.yaml --include-sa --sa-iters 2000 --preset mobilisation --objective-weight mobilisation=0.2 (plus ILS/Tabu for comparison) and record the MILP vs heuristic gaps in tmp/bench_gap/summary.{csv,md} and notes/metaheuristic_roadmap.md. Targets remain ≤5 % gap on tiny7, ≤10 % on small21.
Schedule Locking & Contracts
Code already honours ScheduleLock entries in the greedy seed, repair loop, and operators (_locked_assignments in registry.py). MIP parity is covered (see tests/test_schedule_locking.py), but we still need the specific small21 regression you mentioned.
Action: add a small21 fixture update (e.g., add a loader lock in examples/small21/scenario.yaml or a test stub) and a new test that runs SA or Tabu on small21 with that lock and asserts the assignment never moves. Document the workflow in the data-contract + CLI guides and log it in the changelog.
If you’re good with this breakdown, I’ll start implementing the objective-weight/preset wiring and the small21 lock regression, then move on to the bounded-sampling + restart hooks and benchmarking.

## TODO – Large84 Sequencing Enforcement
- [ ] Extend `apply_system_sequencing_constraints` with loader metadata (role counts + batch volumes) so constraints can be built from scenario data. *Subtasks:* expose loader-role counts, loader batch volumes, and upstream role mapping inside the helper.
- [ ] Add cumulative buffer constraints so loader production up to a shift is bounded by upstream production minus the loader batch requirement (mirroring `SequencingTracker`). *Subtasks:* derive ordered shift prefixes, build Pyomo constraints per `(block, loader_role, prereq_role)` triple, reuse existing `prod` variables.
- [ ] Re-run the `large84` MILP (Gurobi, `--gap=0.01`, generous time-limit) and confirm sequencing violations drop to zero; if infeasible, tweak `work_scale` slightly. *Subtasks:* execute solve, inspect KPI summary, iterate on scaling only if needed.
- [ ] Add a regression test that runs `solve_mip-operational` on the large84 bundle, feeds assignments through `SequencingTracker`, and asserts `sequencing_violation_count == 0`. *Subtasks:* add bundle fixture if needed, integrate tracker call in a new pytest.

## 7. Large84 sequencing parity plan (2025-12-01)

- [x] **Loader metadata plumbing (Pyomo layer)**
  - [x] Thread `loader_roles`, `loader_batch_volume`, and upstream role ordering from `OperationalProblem` into `apply_system_sequencing_constraints` via the existing `system_ctx`.
  - [x] Add helper accessors so each block/system pair exposes `(upstream_role, loader_role, batch_volume, head_start_shifts)` without recomputing inside the constraint builder. *(Solved by reusing `OperationalProblem.allowed_roles`, `prereq_roles`, and `loader_batch_volume` instead of rebuilding them locally.)*
  - [x] Capture these metadata fields inside the MILP bundle snapshot so unit tests / regression fixtures can assert we are building constraints with the right parameters. *(Already available via `OperationalMilpBundle`; constraint builder now consumes the shared context directly.)*

- [ ] **Prefix-balance constraints (SequencingTracker parity)**
  - [x] Build ordered shift indices per machine/role (reuse `shift_keys` + `shift_index`) so the MILP can reference per-shift production prefixes without re-sorting. *(`apply_system_sequencing_constraints` now consumes the precomputed `ctx.shift_keys` ordering when building prefix sets.)*
  - [x] Introduce cumulative variables or expressions (e.g., `prod_prefix[block, role, t]`) that sum `prod` up to shift `t`; enforce `loader_prefix ≤ upstream_prefix − batch_volume` for every `(block, loader_role, upstream_role, shift)` combination once the head-start window opens. *(Loader buffer constraints now reuse the shared prefix ordering, and the new headstart guard uses per-role activation binaries to mirror SequencingTracker’s “counts before current shift” check.)*
  - [ ] Include landing-level staging where relevant by ensuring total loader draws cannot exceed upstream deliveries at the landing, mirroring the evaluator’s `SequencingTracker` logic.
  - [ ] Gate all new constraints behind the sequencing flag so we can still debug/disable them on pathological datasets.

- [ ] **Solver validation + dataset tuning**
  - [ ] Run `fhops solve-mip-operational examples/large84/scenario.yaml --solver gurobi --time-limit 900 --gap 0.01 --sequencing-debug` and record runtime, objective, and sequencing counters.
  - [ ] If the model declares infeasible, adjust `work_scale` (start at −2 %) in `scripts/rebuild_reference_datasets.py`, regenerate large84, and retry until Gurobi reports 0 violations with all blocks complete inside 84 days.
  - [ ] Capture the successful command sequence + KPI deltas in `CHANGE_LOG.md` and `notes/metaheuristic_roadmap.md` so future runs know which configuration produced the clean baseline.

- [ ] **Regression guardrail**
  - [ ] Add `tests/mip/test_large84_sequencing.py` (or extend the existing MILP test module) to call the operational solver on large84, parse the CSV assignments into `SequencingTracker`, and assert `sequencing_violation_count == 0`.
  - [ ] Stub/memoize the solver output so the test can run with a shortened horizon or cached fixture (e.g., ship a trimmed large84 instance) if runtime exceeds CI limits.
  - [ ] Extend the regression harness to fail fast when `solve-mip-operational` emits any sequencing warnings, ensuring future MILP edits keep the parity intact.

- [ ] **Documentation + follow-on tasks**
  - [ ] Update this planning note, `notes/metaheuristic_roadmap.md`, and the large84 README with the new sequencing constraints, mentioning loader prefix caps and any dataset rescale we performed.
  - [ ] Re-run the heuristic smoke (`fhops solve-heur ... --iters 200 --preset mobilisation`) on large84 and record the new MILP vs heuristic gap so maintainers can see the restored benchmark.
  - [ ] Queue the next steps (objective tweaks, landing-surplus telemetry) once the sequencing fix is merged so we keep pressure on heuristics rather than chasing MILP parity bugs.
