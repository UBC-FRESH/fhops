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
machine–block–day/shift schedule for small instances (e.g., minitoy or a
reduced med42), so we can:

- Validate heuristic schedules against an exact or near-exact optimum.
- Explore objective trade-offs in a controlled setting.

**Top-level tasks:**

1. **Define MILP data contract**
   - 1.1 Identify the minimal subset of the FHOPS scenario contract required:
     - Blocks: `id`, `work_required`, `earliest_start`, `latest_finish`,
       `landing_id`, stand metrics (for productivity, if computed inside).
     - Machines: `id`, `role`, `daily_hours`, `operating_cost`.
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
   - 3.3 Test on minitoy:
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

- [ ] **Define the MILP data interface**
  - [ ] Extract a lightweight JSON/YAML bundle (`tmp/milp_bundle.json`) holding just the
        pieces the MILP needs: blocks, machines, calendar, production rates, objective
        weights, mobilisation parameters, landing capacities, locked assignments.
  - [ ] Implement `fhops.model.milp.data.load_bundle(path)` returning a dataclass with
        normalized arrays/mappings for `(machine, block, day, shift)` combinations.

- [ ] **Formulate sets and variables on the shift grid**
  - [ ] Sets: `M` machines, `B` blocks, `D` days, `S` shift IDs, `TS={(day, shift_id)}`.
  - [ ] Binary assignment variable `x[m,b,t]` for machine m working block b at time slot t.
  - [ ] Continuous production variable `prod[m,b,t]` (m³ per slot) bounded by
        `rate[m,b] * x[m,b,t]`.
  - [ ] Block completion indicator `complete[b]` and leftover volume `leftover[b]`.
  - [ ] Optional transition/landing variables (`y`, `landing_slack`) mirroring the SA
        penalty structure.
  - [ ] Constraints:
        - Machine availability: each `(m,t)` assigned to ≤1 block and zeroed if the calendar
          marks the machine unavailable.
        - Block balance: `Σ_{m,t} prod[m,b,t] + leftover[b] = work_required[b]`.
        - Windows: forbid `x[m,b,t]` outside `[earliest_start[b], latest_finish[b]]`.
        - Finish-the-block via either big-M “once started, stay until done” or cumulative
          coverage constraints per block.

- [ ] **Build the Pyomo model and solver harness**
  - [ ] Add `fhops/model/milp/operational.py` with:
        - Builder `build_operational_model(data)` assembling sets, vars, constraints.
        - Objective replicating SA scoring
          (`production - mobilisation_penalty - transition_penalty - landing_penalty
            - leftover_penalty`).
  - [ ] Provide `solve_operational_milp(data, solver=highs, time_limit, gap)` returning
        assignments DataFrame + KPI summary so downstream evaluation works unchanged.

- [ ] **CLI integration and regression tests**
  - [ ] Add `fhops solve-mip-operational` command that:
        - Accepts `--scenario` (default), or `--bundle-json` for custom data.
        - Emits `assignments.csv` identical in schema to SA/Tabu outputs.
        - Streams telemetry/watch snapshots like the heuristics do.
  - [ ] Create `tests/milp/test_operational.py`:
        - Tiny minitoy fixture → assert optimal objective/KPIs.
        - Compare MILP vs SA results for a seeded scenario (tolerances on KPIs).
  - [ ] Update `tests/test_regression_integration.py` to include the MILP solver once the
        new objective scale/fixtures are in place.

- [ ] **Documentation and changelog**
  - [ ] Expand this note with any modeling trade-offs discovered during coding.
  - [ ] Add README/docs snippets describing the operational MILP (inputs, limitations,
        runtime expectations).
  - [ ] Record completion in `CHANGE_LOG.md` before merging back to main.

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
