# Tactical–Operational Expansion Plan (TOPM-Inspired)

Date: 2026-09-24
Status: #37 merged via PR #45; #38 in progress on branch
`issue-38-phase-6.1-contract-time`; GitHub parent issue #36, child issues #37–#44, phase branch
`feature/phase6-tactical-operational-expansion`
Primary historical source: Oborn (1996), *A Mathematical Programming Application with
Semi-Continuous Variables for Multi-Faceted Forest Operations Planning*
Modern design context: Jaffray, Coupland, and Paradis (2026), *Forest harvesting operational
planning tools: a systematic review of optimization, simulation, and spatial decision support
systems*

## 1. Executive recommendation

FHOPS should expand from a single-resolution, shift-indexed machine scheduling system into a
**two-level planning platform**:

1. **Operational scheduling** — retain the current detailed machine × block × shift model for
   approximately 1–16 week horizons.
2. **Tactical–operational planning** — add a separate aggregate model for approximately 1–5 year
   horizons using configurable periods such as months, four-week accounting periods, or seasons.
3. **Integrated planning** — connect the two through a business/anticipation horizon: detailed
   scheduling near term, aggregate planning farther out, with rolling re-planning and feedback.

The new capability should be TOPM-like in functional scope, but it should **not** be implemented by
stretching the current day/shift tensor to five years or by adding many unrelated optional fields to
the current `Scenario`. The recommended design is a new tactical–operational contract and MILP that
reuse shared FHOPS domain entities, solver drivers, telemetry, costing/productivity helpers, and
evaluation services.

The minimum useful release is not merely “a longer horizon.” It must jointly choose harvest
quantity, harvest system, time period, product destination, and inventory trajectory. Roads,
silviculture, and fleet investment can then be added as optional modules without redesigning the
core.

## 2. Source interpretation and terminology

### 2.1 What TOPM means here

Oborn's TOPM is a flexible, multi-year and multi-season mathematical-programming system that
integrates:

- harvest quantities by block, system, year, and season;
- semi-continuous minimum harvest quantities;
- multiple species/products and mills;
- transport flows and outside wood purchases;
- mill consumption and inventory carry-over;
- tertiary, access, and primary/secondary road costs and activation;
- silvicultural consequences of harvest-system choices;
- equipment capacity, purchase timing, and economic life;
- cost-minimization and discounted profit/NPV objectives; and
- scenario storage/comparison through a user-facing interface.

“TOPM-like” therefore refers to this integrated decision scope and temporal structure, not to a
literal reimplementation of its 1990s Windows interface, MPS writer, or MIPIII branch-and-bound
algorithm.

Post-thesis TOPM spin-offs reinforce that scope. Public accounts describe the FORCE/Robak
**OperMAX** line as a commercial evolution of the same planning family: a stand-alone GUI with
scenario/data validation and pre/post-solver workflows, later coupled to RoadOpt. Lehoux et al.
(2012) characterize Force/Robak OperMAX as a multi-year operations-planning optimizer spanning
harvest, transport, silviculture, road construction, wood purchases, mill-yard inventories,
roadside/sublicensed sales, and inter-mill deliveries. The modern FHOPS lesson is to preserve that
integrated decision scope while replacing the proprietary shell with explicit versioned contracts,
reproducible scenario overlays, solver telemetry, and testable reporting.

### 2.2 Relationship to the Jaffray review

The published Jaffray review formally screened studies from 2005–2024, so the extracted review text
does not directly include the 1996 TOPM thesis. Oborn should be cited directly for the historical
formulation. Jaffray et al. supplies the modern acceptance criteria:

- parameterize site specificity rather than hard-coding a case study;
- state model scope, horizon, time step, assumptions, and minimum inputs;
- support re-planning and changing operational conditions;
- expose data, code, validation, and feasibility checks;
- document computational requirements and solution methods;
- support multi-criteria trade-offs and practitioner interpretation; and
- make feedback from implementation/evaluation available to subsequent plans.

### 2.3 Planning-level definitions for FHOPS

| Level | Default horizon | Native resolution | Primary decisions |
|---|---:|---|---|
| Operational | 1 day–16 weeks | shift/day | individual machine activity, sequencing, movement, staging |
| Tactical–operational | 1–5 years | month, four-week period, season | block/system timing, harvest quantity, product flows, roads, fleet capacity |
| Tactical (future boundary) | 5–25 years | year/multi-year period | adjacency, sustained yield, landscape constraints, major infrastructure |
| Strategic (out of scope) | 50–100+ years | multi-year period | forest estate sustainability and long-run policy |

The proposed work targets the first two rows and their interface. It does not attempt to turn FHOPS
into a strategic forest-estate model.

## 3. Current FHOPS baseline and gap analysis

### 3.1 Capabilities to preserve and reuse

FHOPS already provides strong foundations that TOPM did not have:

- validated scenario bundles and schema-version checks;
- block, machine, landing, calendar, and harvest-system entities;
- day/shift operational MILP and SA/ILS/Tabu solvers;
- explicit job precedence, staged volume, loader batching, and machine movement;
- productivity/cost helper libraries and harvest-system presets;
- geospatial distance generation and mobilisation costs;
- rolling-horizon orchestration and schedule locking;
- deterministic/stochastic playback, KPIs, telemetry, and benchmark automation; and
- CLI, Python APIs, Sphinx docs, tests, and reproducible synthetic datasets.

These should remain the operational layer. Existing `Scenario` inputs and `fhops solve-*` workflows
must continue to work unchanged during the expansion.

### 3.2 TOPM capability matrix

| Capability | Current FHOPS | Required expansion | Priority |
|---|---|---|---|
| Multi-year periods | Integer `num_days`; practical target ≤16 weeks | Explicit period hierarchy without materializing every shift | Foundation |
| Harvest-system choice | One `harvest_system_id` per block | Many feasible block-system-treatment options chosen by model | Core |
| Harvest quantity | Block workload/volume completed by machines | Area or volume by block/system/period, partial or whole-block modes | Core |
| Minimum cut size | Not represented | Semi-continuous `0` or `[minimum, maximum]` harvest quantities | Core |
| Products/yields | One aggregate `work_required` | Species/product yields by block/system/treatment/period | Core |
| Multiple mills/customers | Not represented | Facilities, demand/consumption, product acceptance, value | Core |
| Transport flow/cost | Machine mobilisation only | Product flow on block–facility arcs by transport mode and period | Core |
| Mill inventory | Not represented | Initial stock, balance, min/max/safety stock, ageing/freshness hooks | Core |
| Outside purchases | Not represented | Bounded external supply contracts and delivered prices | Core |
| Seasonal access | Daily windows/blackouts | Repeating seasonal eligibility and bearing/access classes | Core |
| Discounted economics | Production-weighted operational objective | Period discount factors, delivered cost, profit, and NPV | Core |
| Road activation | Road costing metadata only | Build/upgrade/maintain decisions and access dependencies | Module 2 |
| Silviculture | Not represented in optimization | System × forest-state transition actions/costs | Module 2 |
| Fleet acquisition/life | Fixed machine roster | Buy/lease/retire and period/economic-life capacity | Module 2 |
| Scenario comparison | Files + telemetry, no inheritance/diff model | Overlays, provenance, scenario diff and comparison reports | Interface |
| Multi-resolution coupling | Rolling detailed windows only | Tactical commitments compiled into operational subproblems | Integration |
| Uncertainty | Stochastic playback after solving | Scenario ensembles first; robust/stochastic optimization later | Future |

### 3.3 Structural limitations that must be corrected first

1. `Block.work_required` conflates volume/work semantics and has no explicit area or product yield.
2. `Block.harvest_system_id` fixes one system instead of exposing alternatives.
3. `Scenario.num_days` is the only horizon representation.
4. Operational production rates are indexed only by machine and block, with no period economics or
   treatment-dependent yields.
5. The current operational MILP maximizes terminal production and penalties; it is not a delivered
   wood/profit model.
6. Rolling slicing rebases windows and locks but does not yet carry every state required by a
   multi-year integrated model (mill inventory, roadside inventory, road state, fleet state, and
   contracts).

## 4. Target architecture

### 4.1 Keep separate models behind shared domain objects

Recommended package boundaries:

```text
fhops/
  domain/
    time.py             # period hierarchy and calendar templates
    forest.py           # planning units, treatments, product yields
    products.py         # products, grades, facilities, demand, inventory
    infrastructure.py   # roads, dependencies, transport arcs
    fleet.py            # equipment types, fleet state, acquisition options
    economics.py        # costs, values, currencies, discounting
  planning/
    tactical_operational/
      contracts.py      # validated aggregate planning contract
      compiler.py       # contract -> normalized model bundle
      reporting.py      # decision tables and accounting summaries
    integrated.py       # tactical commitments <-> operational scenarios
    rolling.py          # existing engine, generalized state handoff
  model/milp/
    operational.py      # existing shift model
    tactical_operational.py
    tactical_data.py
```

The exact paths can be refined in an architecture decision record, but the separation is important:

- do not make a five-year shift model;
- do not make one giant MILP with every feature always enabled;
- do not overload the operational `Scenario` with dozens of nullable supply-chain fields; and
- do share identifiers, units, time aggregation, economics, provenance, solver drivers, and result
  schemas.

### 4.2 Contracts and compatibility

Introduce a new manifest type, tentatively `TacticalOperationalScenario`, under a new schema line.
Keep the existing `Scenario` and schema `1.0.0` as the stable operational contract.

Recommended migration strategy:

1. Add explicit contract dispatch using `planning_level` and `schema_version`.
2. Continue loading legacy operational bundles exactly as today.
3. Add an adapter that derives shared domain objects from an operational `Scenario`.
4. Add export helpers that compile a tactical decision into operational windows, locks, candidate
   blocks, system options, and capacity budgets.
5. Do not rename the existing public `Scenario` until a major release; if a clearer
   `OperationalScenario` name is introduced, retain `Scenario` as an alias.

### 4.3 Time model

Replace “horizon equals a number of days” as the universal assumption with a period table:

| Field | Meaning |
|---|---|
| `period_id` | Stable identifier such as `Y01-SUMMER` or `2027-P03` |
| `start_date`, `end_date` | Calendar bounds |
| `duration_days`, `available_hours` | Capacity scaling |
| `level` | shift, day, week, four-week, month, season, year |
| `parent_period_id` | Aggregation hierarchy |
| `sequence` | Total ordering |
| `discount_factor` | Economic timing |
| `season_tags` | winter, breakup, fire season, etc. |

Provide templates for:

- years × four seasons;
- 13 four-week periods per year;
- calendar months; and
- multi-resolution business/anticipation horizons.

Operational shifts should map into this hierarchy for roll-up reporting, but tactical models should
instantiate only their own aggregate periods.

### 4.4 Unit discipline

Every quantity must declare stable units in names or metadata:

- area: ha;
- standing, roadside, delivered, and inventory quantities: m³ by product;
- machine capacity: PMH/period or m³/period;
- transport capacity: m³/period or loads/period;
- roads: km and currency/km;
- costs/values: scenario currency and base year;
- discount rate: effective annual rate with documented timing convention.

The model must distinguish area harvested from role work, harvested volume, roadside volume,
transported volume, delivered volume, consumed volume, and inventory. The current generic
`work_required` remains a legacy operational field, not the tactical data foundation.

## 5. Proposed tactical–operational data contract

### 5.1 Required core tables

1. **Periods** — ordered periods and discount factors.
2. **Planning units** — block/stand ID, gross area, forest class, ownership/tenure, initial state.
3. **Products** — species/product/grade IDs and unit metadata.
4. **Block product yields** — m³/ha by block, product, treatment/system option, and optionally period.
5. **Harvest system options** — many-to-many block/system eligibility, productivity, variable cost,
   fixed/setup cost, minimum/maximum cut, and seasonal eligibility.
6. **Fleet capacity** — available systems/equipment and PMH or production capacity by period.
7. **Facilities** — mills/customers/terminals and accepted products.
8. **Demand or consumption** — min/target/max by facility/product/period.
9. **Transport arcs** — origin, destination, mode, distance/time, cost, capacity, seasonal access.
10. **Initial inventory** — facility/product quantities at the planning start.
11. **Economics** — objective sense, base currency/year, discount rate, cost/value conventions.

### 5.2 Optional module tables

- **External supply** — seller/source, product, period bounds, contract minimums, delivered cost.
- **Road assets/projects** — road ID, build/upgrade cost, availability, prerequisite roads, blocks
  enabled, maintenance cost/capacity.
- **Silviculture transitions** — forest class × treatment/system → activities, timing, costs, next
  state.
- **Fleet assets/options** — existing counts/age, purchase/lease options, seasonal capacity,
  economic life, salvage value.
- **Policy envelopes** — annual allowable cut, area/volume targets, habitat/adjacency hooks, budget
  limits, species mix, contractor obligations.
- **Scenario overlays** — sparse changes to base assumptions with parent ID and provenance.

### 5.3 Recommended file layout

```text
scenario.yaml
data/
  periods.csv
  planning_units.csv
  products.csv
  block_product_yields.csv
  block_system_options.csv
  fleet_capacity.csv
  facilities.csv
  facility_demand.csv
  initial_inventory.csv
  transport_arcs.csv
  external_supply.csv             # optional
  roads.csv                       # optional
  road_dependencies.csv           # optional
  silviculture_transitions.csv    # optional
  fleet_options.csv               # optional
```

Wide tables should be avoided for products and periods. Long-form tables permit arbitrary
dimensions and match TOPM's goal of avoiding hard-coded counts.

## 6. Core mathematical formulation

### 6.1 Principal indices

- `b`: planning unit/block;
- `h`: harvest system/treatment option;
- `t`: tactical–operational period;
- `k`: product/species-grade;
- `m`: facility/mill/customer;
- `v`: transport mode;
- `r`: road asset/project;
- `e`: fleet/equipment type; and
- `a`: silviculture activity.

### 6.2 Core decision variables

- `H[b,h,t] >= 0`: area harvested (ha).
- `Z[b,h,t] in {0,1}`: harvest activation when minimum cuts or fixed costs apply.
- `F[b,k,m,v,t] >= 0`: product flow from block to facility (m³).
- `I[m,k,t] >= 0`: ending facility inventory (m³).
- `P[src,m,k,t] >= 0`: external wood purchase (m³).
- `R[r,t] in {0,1}`: road project active/built by period.
- `N[e,t] in nonnegative integers`: equipment units bought/leased.
- `U[e,t] >= 0`: fleet utilization/capacity consumed.
- `S[b,a,t] >= 0` or binary: silviculture activity quantity/activation where scheduling is explicit.

### 6.3 Required core constraints

1. **Block area balance** — cumulative harvested area cannot exceed operable area; optional minimum
   completion by horizon.
2. **System eligibility** — generate variables only for valid block/system/period combinations.
3. **Semi-continuous cut size** — for each active harvest:

   ```text
   L[b,h,t] * Z[b,h,t] <= H[b,h,t] <= U[b,h,t] * Z[b,h,t]
   ```

4. **Yield conversion** — harvested area creates product-specific roadside supply.
5. **Product conservation** — outbound product flows cannot exceed current and carry-over supply.
6. **Facility inventory balance** — prior inventory + deliveries + purchases − consumption = ending
   inventory.
7. **Demand/consumption bounds** — hard bounds or penalized target deviations.
8. **Seasonal/fleet capacity** — harvest and transport hours/volume cannot exceed period capacity.
9. **Transport arc eligibility/capacity** — only valid modes/routes/products are generated.
10. **Economic accounting** — all objective components are traceable by activity and period.

### 6.4 Optional module constraints

- road access and prerequisite chains;
- road construction/maintenance budgets and timing;
- silviculture transition and delayed activity requirements;
- equipment acquisition, retirement, seasonal capacity, and economic-life limits;
- product freshness/age classes;
- species/product mix requirements;
- annual or multi-year harvest envelopes;
- whole-block and single-entry modes;
- adjacency/green-up constraints in a later tactical module; and
- tactical commitments/locks supplied by external plans.

### 6.5 Objectives

Support explicit, named objective profiles rather than one overloaded weighted expression:

1. `min_discounted_delivered_cost` — recommended first profile.
2. `max_discounted_profit` — product revenue/value less harvest, silviculture, roads, transport,
   purchases, and fleet costs.
3. `max_npv` — multi-year value with terminal asset/inventory treatment.
4. `goal_programming` — weighted deviations from demand, budget, flow, and policy targets.

Every solve result must include an objective decomposition table. TOPM's approximation of wood
value by purchase price should be available only as an explicit fallback, never an undocumented
default.

### 6.6 Semi-continuous implementation strategy

TOPM's historical contribution was an efficient solver-native semi-continuous treatment. Modern
FHOPS should preserve the **planning semantics**, not recreate MIPIII internals.

Recommended implementation:

1. Portable default: continuous harvest variable plus a tightly bounded activation binary.
2. Optional native semi-continuous domain for solver backends that support it cleanly.
3. No arbitrary big-M: use the physical upper bound (remaining block area or allowed period cut).
4. Keep three selectable modes for validation:
   - continuous partial cut;
   - semi-continuous partial cut; and
   - whole-block/all-or-nothing.
5. Benchmark model size, root relaxation, solve time, objective, and decision-vector differences.

The semi-continuous minimum should be configurable by block/system/treatment, not one global value.

## 7. Tactical–operational and operational coupling

### 7.1 Recommended hierarchical workflow

1. Solve the tactical–operational model over 1–5 years.
2. Select the next business window (typically 4–16 weeks).
3. Compile tactical decisions into an operational scenario:
   - candidate blocks and systems;
   - target/min/max quantities;
   - block access and road state;
   - machine/fleet availability;
   - mill/product delivery targets;
   - fixed contractual decisions; and
   - opening roadside/mill inventories.
4. Solve the detailed machine schedule with the existing operational engine.
5. Play back/evaluate the schedule.
6. Return realized production, inventory, delays, costs, and state changes to the next tactical
   iteration.

### 7.2 Business and anticipation periods

Use a multi-resolution horizon rather than treating five years uniformly:

- **Business horizon:** shift/day detail, current operational model.
- **Anticipation horizon:** four-week/month/season aggregate tactical model.
- **Roll frequency:** configurable and independent of both horizon lengths.

This generalizes the existing `fhops.planning.rolling` machinery. The rolling state object must grow
from a list of machine locks into a structured state snapshot containing:

- machine last location and availability;
- block area/volume remaining by role/product;
- roadside and facility inventory;
- active roads and completed projects;
- fleet acquisitions/retirements;
- outstanding purchase and delivery commitments; and
- incurred/carry-forward costs.

### 7.3 Why not one monolithic model

A monolithic five-year shift-indexed MILP would multiply the current machine × block × shift tensor
by years while adding product, destination, road, and fleet dimensions. It would be difficult to
solve, difficult to explain, and would couple every future feature to one formulation. Separate
models with explicit contracts permit exact tactical solutions, heuristic operational schedules,
rolling feedback, and later decomposition.

## 8. User interface and result contract

### 8.1 CLI/API surface

Proposed commands:

```text
fhops validate tactical-operational scenario.yaml
fhops plan tactical-operational scenario.yaml --solver highs --out-dir results/base
fhops plan integrated scenario.yaml --business-horizon 16w --roll-every 4w
fhops scenario overlay base.yaml low-demand.yaml --out scenario-low.yaml
fhops scenario diff base.yaml scenario-low.yaml
fhops report tactical results/base --format csv,parquet,markdown
```

Python APIs should call the same validators, compiler, solver, and report builders.

### 8.2 Scenario management

Translate TOPM/OperMAX's multi-scenario shell strength into reproducible file/API behavior:

- immutable base scenario plus sparse overlays;
- parent/child provenance and content hashes;
- named assumptions and tags;
- side-by-side parameter and result diffs;
- batch solve manifests; and
- no manual copying of coefficient matrices or solver output.

A browser GUI can be considered later. The first interface milestone should prioritize a stable
contract, clear diagnostics, and comparison-ready outputs over building forms around an unstable
schema.

### 8.3 Required result tables

Every tactical solve should emit normalized tables for:

- harvest area/volume by block, system, product, and period;
- product flow by origin, destination, mode, and period;
- opening/delivery/consumption/closing inventory by facility/product/period;
- external purchases and contract utilization;
- road build/upgrade/maintenance decisions;
- fleet capacity, acquisitions, utilization, and retirements;
- silviculture obligations/activities;
- objective decomposition and discounted cash flow;
- constraint utilization/slack and infeasibility diagnostics; and
- solver status, gap, bounds, runtime, model dimensions, and configuration.

## 9. Delivery roadmap

Each phase is a vertical slice: contract, model, CLI/API, reports, tests, docs, telemetry, and
changelog land together.

### Phase 0 — Decisions, provenance, and executable specification

- [x] Draft scope, terminology, module boundaries, and defaults in
  `notes/adr/0001-tactical-operational-architecture.md` for maintainer approval.
- [x] Record Oborn (1996) and the public OperMAX/FORCE/Robak lineage in
  `notes/tactical_operational_provenance.md` without redistributing restricted PDFs.
- [x] Catalogue reusable implementation lessons from OperMAX/RoadOpt reports: stand-alone scenario
  validation, pre/post-solver workflows, batch scenario comparison, and infrastructure coupling.
- [x] Define initial equations, units, and equation-to-code expectations before implementation.
- [x] Create the copyright-safe synthetic `topm-mini` executable specification at
  `tests/fixtures/tactical_operational/topm-mini/specification.yaml` with structural tests.
- [x] Capture current operational API/fixture baselines in
  `notes/tactical_operational_compatibility_baseline.md`.

Exit criterion: maintainers approve the ADR, contract sketch, model scope, and acceptance fixtures.

### Phase 1 — Shared time, units, and planning contract

- [x] Implement period hierarchy/calendar templates and roll-up utilities
  (`fhops.planning.tactical_operational.time`).
- [x] Add tactical–operational scenario models and long-form YAML/CSV loaders
  (`fhops.planning.tactical_operational.models` / `.io`).
- [x] Add products, facilities, system options, yields, fleet capacity, and economics models.
- [x] Add schema dispatch/versioning and preserve the legacy operational loader path.
- [x] Provide `fhops validate tactical-operational` with cross-table diagnostics.

Exit criterion: `topm-mini` loads, validates, round-trips, and reports model dimensions without
building a solver model.

### Phase 2 — TOPM core harvest allocation

- [x] Implement area-based harvest decisions by block/system/period.
- [x] Add continuous, semi-continuous, and whole-block modes.
- [x] Add seasonal eligibility, product yields, fleet capacity, fixed/variable harvest costs, and
  discounting.
- [x] Implement discounted harvest-cost minimization and objective decomposition.
- [x] Compare variable modes on the `topm-mini` synthetic fixture.

Exit criterion: exact tiny fixtures reproduce hand-calculated harvest/system/period choices and no
positive harvest lies below its configured minimum.

### Phase 3 — Integrated product flow and mill inventory

- [x] Add products, facilities, transport modes/arcs, and flow conservation.
- [x] Add mill consumption/demand and inventory carry-over.
- [x] Add outside purchases and bounded contracts.
- [x] Add profit/NPV objective profiles.
- [x] Add product/facility/period reporting and balance audits.

Exit criterion: `topm-mini` solves an end-to-end harvest → transport/purchase → mill inventory plan
with every product balance independently verified.

### Phase 4 — Roads, silviculture, and fleet investment

- [x] Add road activation, dependencies, timing, maintenance, and access constraints.
- [x] Add harvest-system/block silviculture transitions and delayed costs/activities.
- [x] Add fleet purchase options and economic-life capacity.
- [x] Add tight bounds/indicator constraints and module toggles.

Exit criterion: enabling each module changes the known tiny optimum as expected; disabling it
returns the Phase 3 optimum.

### Phase 5 — Scenario workflow and decision-support reporting

- [ ] Implement base/overlay scenarios, batch manifests, and scenario diff.
- [ ] Add Markdown/CSV/Parquet summaries and comparison reports.
- [ ] Add infeasibility explanation, utilization/slack reports, and provenance hashes.
- [ ] Add guided examples/notebooks for planners.

Exit criterion: a user can create three sensitivity cases without duplicating the full dataset and
compare decisions, KPIs, and assumptions from one command.

### Phase 6 — Integrated tactical–operational planning

- [ ] Define the tactical commitment/result handoff contract.
- [ ] Compile near-term tactical decisions into current operational scenarios.
- [ ] Generalize rolling state to inventory, roads, fleet, and commitments.
- [ ] Feed operational realization back to the next tactical solve.
- [ ] Add business/anticipation horizon orchestration and warm starts.

Exit criterion: a multi-year aggregate plan can produce and re-plan a detailed 4–16 week machine
schedule without manual data rewriting.

### Phase 7 — Scale, decomposition, and uncertainty

- [ ] Benchmark a TOPM-shaped 5-year scenario (hundreds of blocks, multiple systems/products/mills).
- [ ] Add sparse variable generation and solver-native indicators/semi-continuous variables where
  useful.
- [ ] Evaluate Benders/Dantzig–Wolfe, fix-and-optimize, and rolling decomposition only after profiling.
- [ ] Add scenario ensembles/sensitivity automation before robust or stochastic MILP variants.
- [ ] Validate against public or permission-cleared practitioner cases.

Exit criterion: documented scale envelopes, graceful incumbent/gap behavior, and evidence that the
chosen decomposition improves a measured bottleneck.

## 10. Testing and validation strategy

### 10.1 Acceptance datasets

1. **`topm-mini-harvest`** — 4 blocks, 2 systems, 4 periods; known semi-continuous/system-choice
   optimum.
2. **`topm-mini-flow`** — 6 blocks, 3 products, 2 mills, external purchases and inventory.
3. **`topm-mini-full`** — adds road dependency, silviculture transition, and one fleet purchase.
4. **`topm-scale`** — approximately 500–700 blocks, 5 years, 3–4 seasons/year, 5 systems, 10–15
   products, 3–4 mills; performance fixture with no hard-coded optimum.
5. **Integrated rolling fixture** — tactical periods compiled into a tiny operational shift schedule.

Use newly generated data. Do not copy Oborn's YFP appendices into the public repository.

### 10.2 Required test classes

- schema and cross-reference tests for every table;
- unit conversion and discount-factor tests;
- algebraic balance tests independent of Pyomo;
- model component tests with each optional module on/off;
- known-optimum tiny MILP tests;
- continuous vs semi-continuous vs whole-block regression tests;
- result-accounting reconciliation tests;
- tactical-to-operational compilation/state round-trip tests;
- legacy operational scenario and CLI compatibility tests;
- property-based tests for conservation and non-negative inventory;
- solver-driver tests for HiGHS and optional Gurobi; and
- benchmark telemetry for rows, columns, nonzeros, build time, solve time, bound, gap, and memory.

### 10.3 Scientific validation

For every publication/case study report:

- disclose scope, horizon, period resolution, and model modules;
- publish or describe all coefficient sources and assumptions;
- distinguish feasibility, incumbent quality, and proven optimality;
- compare against a baseline/current plan where possible;
- perform sensitivity on minimum cut size, demand, productivity, and costs;
- compare decision vectors, not objective values alone; and
- replay near-term operational schedules to identify aggregate-plan implementation failures.

## 11. Performance strategy

Start with formulation quality, not premature decomposition:

1. Generate only feasible block/system/period and flow arc combinations.
2. Use physical/tight bounds, not generic big-M values.
3. Separate accounting/reporting from constraint rows where possible.
4. Export model statistics before solving.
5. Support solver time/gap limits and preserve incumbents.
6. Warm-start repeated scenarios and rolling iterations.
7. Profile the core model before choosing decomposition.

Likely decomposition boundaries, if needed:

- harvest/road/fleet investment master with product-flow subproblem;
- period rolling horizon with overlap and state carry-over;
- tactical master selecting block-period-system patterns generated by operational subproblems; or
- facility/product flow master with harvest-area subproblems.

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Optional-field “mega schema” becomes unusable | Separate tactical contract, modules, templates, and minimum viable profiles |
| Five-year model becomes intractable | Aggregate periods, sparse generation, tight bounds, profile before decomposition |
| Tactical decisions cannot be scheduled operationally | Explicit handoff contract and operational feasibility feedback in Phase 6 |
| Ambiguous units produce plausible but wrong plans | Named units, validators, balance audits, objective decomposition |
| Semi-continuous binaries dominate solve time | Solver-native option, strong bounds, compare relaxed/whole-block modes |
| Inventory/flow accounting obscures errors | Independent post-solve reconciliation for every product and period |
| New scope destabilizes current users | Preserve schema 1.0.0 and current commands; add explicit contract dispatch |
| Road/fleet/silviculture scope delays useful release | Deliver harvest + mill flow core before optional modules |
| Historical TOPM assumptions are copied uncritically | Treat TOPM as a functional reference and document every modern deviation |
| A GUI freezes an unstable schema | Stabilize CLI/API/contracts first; defer web authoring UI |

## 13. Decisions requested from maintainers

Recommended defaults are shown in **bold**.

1. **Initial horizon:** **1–5 years**, not 20–25 year tactical planning.
2. **Default periods:** arbitrary period table with shipped **four-week and seasonal templates**.
3. **Minimum viable integrated scope:** **harvest/system allocation + products + mills + transport +
   inventory + purchases**.
4. **Block divisibility:** support both, defaulting to **semi-continuous partial area** when area/yield
   data exist and whole-block when policy requires it.
5. **Objective order:** **minimum discounted delivered cost first**, then discounted profit/NPV.
6. **Coupling:** **hierarchical tactical + operational models**, not one monolithic MILP.
7. **Roads/silviculture/fleet:** **second functional module**, designed in Phase 1 but implemented
   after the product-flow core.
8. **Interface:** **CLI/Python + overlays/diff/reports first**; defer browser GUI.
9. **Adjacency/green-up:** defer to a later tactical module unless an immediate case requires it.
10. **Uncertainty:** scenario/sensitivity ensembles first; robust/stochastic optimization later.

## 14. Definition of done for “TOPM-like FHOPS”

The expansion is functionally complete when FHOPS can:

1. load a dimension-flexible 5-year, multi-season scenario;
2. choose blocks, systems, partial/whole cut quantities, and periods;
3. enforce system-specific minimum cut sizes;
4. convert harvest decisions into product flows to multiple facilities;
5. balance transport, purchases, consumption, and inventory through time;
6. optionally activate roads, silviculture transitions, and fleet investments;
7. optimize discounted delivered cost or profit/NPV;
8. emit auditable decision/accounting/solver reports;
9. derive a detailed near-term operational FHOPS scenario from the aggregate plan;
10. roll realized state forward and re-plan; and
11. preserve all current operational workflows and regression fixtures.

## 15. References

- Oborn, R. M. R. 1996. *A Mathematical Programming Application with Semi-Continuous Variables
  for Multi-Faceted Forest Operations Planning*. MScFE thesis, University of New Brunswick.
- Barrett, J. D. 1997. The Canadian Wood Fiber Centre: technology development and delivery.
  *Forestry Chronicle* 73(6):647–652.
- Richard, D. L., and Gunn, E. A. 1996. A model and software system for tactical planning of forest
  harvesting and transportation. In *Proceedings of the 32nd Annual Conference of the Operational
  Research Society of New Zealand*, 163–170.
- Gunn, E. A. 1998. Perspectives on policy analysis and modelling of the forest products sector in
  Atlantic Canada. *Canadian Journal of Forest Research* 28(5):768–777.
- Feller, A., and Richards, E. W. 1999. *MAXPLAN: A Forest Operations Planning System*.
  Forest Engineering Research Institute of Canada, Vancouver, BC.
- Robak, T. 1999. *OperMAX: A Forest Operations Planning System*. FORCE/Robak Associates Ltd.,
  Fredericton, NB.
- Lehoux, N., Marier, P., D’Amours, S., Ouellet, D., and Beaulieu, J. 2012. *Le réseau de création
  de valeur de la fibre de bois canadienne*. CIRRELT-2012-33, Université Laval / CIRRELT.
  https://www.cirrelt.ca/documentstravail/cirrelt-2012-33.pdf
- Jaffray, R., Coupland, K., and Paradis, G. 2026. Forest harvesting operational planning tools: a
  systematic review of optimization, simulation, and spatial decision support systems.
  *International Journal of Forest Engineering*, 1–16. DOI: 10.1080/14942119.2026.2662184.
- Bredström, D., Jönsson, P., and Rönnqvist, M. 2010. Annual planning of harvesting resources in
  the forest industry. *International Transactions in Operational Research* 17(2):155–177.
- Frisk, M., Flisberg, P., Rönnqvist, M., and Andersson, G. 2016. Detailed scheduling of harvest
  teams and robust use of harvest and transportation resources. *Scandinavian Journal of Forest
  Research* 31(7):681–690.
