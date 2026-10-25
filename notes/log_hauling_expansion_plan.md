# Log Hauling and Mill Delivery Expansion Plan (Ghotb-Inspired)

Date: 2026-10-25
Status: complete; PR #185 merged as `52462d2`; parent #170 closed.
Phase: P11
Branch: `feature/p11-log-hauling` (created from `main` at activation)
Parent issue: #170
Formulation audit: `notes/hauling_formulation_audit.md`
Primary source: Ghotb, S. (2023), *Optimization of Log Logistics at the Operational Level
Considering Sorting Decisions and Synchronization Requirements*, PhD thesis, University of British
Columbia. Handle: <https://hdl.handle.net/2429/85563>
Related papers:
- Ghotb, S., Sowlati, T., Mortyn, J., Roeser, D., and Griess, V. C. (2022). A goal programming
  model for the optimization of log logistics considering sorting decisions and social objective.
  *Canadian Journal of Forest Research* 52(5), 716-726. <https://doi.org/10.1139/cjfr-2021-0203>
- Ghotb, S., Sowlati, T., and Mortyn, J. (2024). An optimization model for detailed scheduling of
  a heterogeneous fleet of log trucks considering synchronization. *International Journal of Forest
  Engineering* 35(2), 313-325. <https://doi.org/10.1080/14942119.2023.2291960>
- Ghotb, S., Sowlati, T., and Mortyn, J. (2024). Scheduling of log logistics using a metaheuristic
  approach. *Expert Systems with Applications* 238, 122008.
  <https://doi.org/10.1016/j.eswa.2023.122008>

## 1. Executive recommendation

FHOPS already schedules harvesting machines to blocks and already carries product flows from
planning units to facilities in the tactical-operational model. The missing operational layer is
**log hauling**: how the harvested volume leaves the block/landing, which contractor and truck type
carries each load, when each truck and loader works, how much inventory waits at a sort yard, and
how the mill demand is met without violating fleet, compatibility, synchronisation, and overtime
limits.

Implement Ghotb's two-phase decomposition as an **additional planning layer** under a new
`fhops.hauling` package:

1. **Phase I - daily flows for a month.** A bi-objective mixed-integer program decides the daily
   volume and truckloads of sorted and unsorted log sorts from blocks to sort yards, the volume
   sorted at each yard, and the inventory at blocks and yards. Objective 1 minimises transport and
   roadside-inventory cost; objective 2 balances contractor workload. A goal-programming
   reformulation produces the trade-off.
2. **Phase II - daily routing and scheduling.** A continuous-time pickup-and-delivery MIP assigns
   each truckload from Phase I to a compatible truck and contractor, routes the trucks from a
   central depot, and synchronises trucks with stationary loaders at both pickups and deliveries.
   It decides arrival, waiting, loading/unloading, return-to-depot, and overtime.
3. **Phase III - large-instance solution.** A simulated-annealing solver with an SPT schedule
   decoder reproduces the thesis solution approach: permutation-with-delimiters representation,
   feasibility-preserving initial solutions, swap/reversion/insertion moves, overtime penalty, and
   Taguchi-calibrated defaults.

The new layer must consume existing FHOPS entities and outputs, not duplicate them. Blocks,
landings, products, loaders (machines), calendars, and tactical facility demand remain the source
of truth; hauling adds contractors, truck types/fleets, depots, sort yards, log sorts, haul arcs,
and driver policies.

## 2. Goal and non-goals

### Goal

Make FHOPS able to answer, for a redistributable or synthetic case:

- Which log sort, in what daily volume, moves from each block/landing to each sort yard or mill?
- Which contractor and truck type carries each truckload, and which individual truck carries it?
- When does each truck arrive, wait, load, unload, and return to the depot?
- When is each loader busy, and where do trucks queue?
- How much unsorted inventory is stored at each yard, and how much is processed each day?
- How much overtime is assigned, and what does the plan cost?
- How balanced is the workload across contractors, and what does balance cost?

### Non-goals (first release)

- Emissions or carbon objectives, electric-truck range and charging (thesis future work).
- Stochastic supply, demand, or loader breakdowns; robust or scenario-based optimisation.
- Lunch breaks, driver changes, and hours-of-service rules beyond the regular/overtime model.
- Contractor collaboration or shared blocks.
- Live dispatch, GPS, telematics, or a commercial transport-management system.
- Replacing the existing operational MILP or tactical-operational MILP.
- Shipping proprietary Western Forest Products data. The thesis case is not redistributable; the
  repository carries only synthetic or clearly licensed instances.

## 3. Provenance and what "replicate" means

The thesis is the formulation authority. The implementation must record, for every constraint and
objective term, the thesis equation and any deliberate clarification. Exact numerical reproduction
of the company case is **not** an acceptance criterion because the cost, capacity, and compatibility
inputs are confidential and are not published. The defensible acceptance target is:

- structural fidelity to the published model;
- exact MIP-versus-SA parity on synthetic instances shaped like the thesis test problems;
- reproduction of the published qualitative findings (balanced workload at a small cost premium;
  overtime cheaper than dispatching an extra truck; yard waiting concentrated where volume is
  highest);
- a transparent statement of every deviation from the thesis text.

The thesis contains transcription issues that must be resolved in the first task and documented in
`notes/hauling_formulation_audit.md`:

- Equation (4-14) indexes the destination as `N1`; the intended set is `N2`.
- Equation (4-15) uses `e+`/`e-`; the intended depot nodes are `f+`/`f-`.
- The absolute-value workload constraint (3-9) needs an explicit linearisation.
- The inventory recursions (3-10)/(3-11) need stated initial conditions.
- The synchronisation equalities (4-25)/(4-26) must be linked to the machines actually assigned to
  the node; a literal sum over every loader or truck is not correct for multiple visitors.

These are not reasons to change the model's intent. They are a formulation audit that belongs in
P11.1 and must be reflected in the canonical formulation assets.

## 4. Current FHOPS baseline and gap

### Reusable foundations

- Validated scenario bundles, schema-version checks, Pydantic contract, CSV/YAML loaders.
- Blocks, landings, machines, calendars, shift calendars, production rates, harvest systems.
- Operational MILP and SA/ILS/Tabu solvers with shift-level assignments.
- Tactical-operational contract with products, planning units, facility demand, transport arcs,
  inventory, roads, and external supply.
- Rolling-horizon planning, schedule locks, playback, KPIs, telemetry, costing, and benchmarks.
- `fhops geo distances` for distance matrices from block/landing geometry.

### Gaps

| Capability | Current FHOPS | Required for hauling |
|---|---|---|
| Log sorts | Aggregate `work_required`; products only in tactical contract | Sorted and unsorted sorts by species/grade/diameter, with supply at block/landing |
| Contractors | Not represented | Contractor eligibility, fleet ownership, preferred daily workload |
| Trucks | Not represented | Truck types, individual trucks, capacity, fixed/variable/overtime cost, compatibility |
| Depots | Not represented | Central depot(s), start/end travel |
| Sort yards / mills | Tactical `Facility` has demand but no processing capacity | Yard storage, daily sorted/unsorted processing capacity, water inventory, mill demand |
| Haul arcs | Tactical `TransportArc` has a cost/period, no time or equipment | Travel time by truck type, back-and-forth cycle, loading/unloading times |
| Loaders | Machines with roles, but no location binding for hauling | One or more loaders per pickup/delivery location, calendars, service times |
| Synchronisation | Not represented | Truck and loader start together; waiting on both sides |
| Overtime | Not represented | Regular minutes, maximum overtime, overtime cost |
| Daily truck routing | Not represented | Pickup-and-delivery routes, truckload assignment, return to depot |

The tactical-operational model can remain the source of mill demand and product flow. The hauling
layer turns a selected tactical period into a monthly haul plan and then daily truck schedules. A
standalone scenario with an explicit `hauling:` block must also work, so the feature is useful
without a tactical model.

## 5. Architecture

```text
scenario.yaml
  blocks / landings / machines / products / demand
  hauling:
    log_sorts, contractors, truck_types, trucks, depots
    sort_yards, supply, demand, haul_arcs
    loader_locations, compatibility, driver_policy
        |
        +--> fhops.hauling.contract   (Pydantic models + cross-validation)
        +--> fhops.hauling.flow       (Phase I: monthly daily-flow MILP + goal programming)
        +--> fhops.hauling.schedule   (Phase II: daily continuous-time routing/scheduling MIP)
        +--> fhops.hauling.heuristic  (Phase III: SA + SPT decoder)
        +--> fhops.hauling.integration (bridge from operational/tactical outputs)
        +--> fhops.hauling.reporting  (CSV/JSON/Markdown outputs and KPIs)
        |
        +--> CLI: fhops haul plan | schedule | solve | report
```

### Package layout

- `src/fhops/hauling/__init__.py` - public exports and versioned schema.
- `src/fhops/hauling/contract.py` - hauling entities and validation.
- `src/fhops/hauling/network.py` - node/arc construction, travel-time lookup, compatibility masks.
- `src/fhops/hauling/flow.py` - Phase I Pyomo model, single-objective solves, goal programming.
- `src/fhops/hauling/schedule.py` - Phase II Pyomo model and exact driver.
- `src/fhops/hauling/heuristic.py` - solution representation, SPT decoder, SA, operators.
- `src/fhops/hauling/integration.py` - build a hauling problem from FHOPS outputs.
- `src/fhops/hauling/reporting.py` - DataFrames, summaries, KPI payloads.
- `src/fhops/cli/hauling.py` - Typer sub-app.
- `tests/hauling/` - unit, contract, formulation, parity, integration, and regression tests.
- `examples/hauling/` - a redistributable synthetic case shaped like the thesis case.
- `docs/howto/hauling.rst`, `docs/reference/hauling.rst`, and formulation assets.

### Contract extension

Add an optional `hauling:` section to `Scenario`. The extension is additive; every existing
scenario must continue to load unchanged. The candidate schema is:

```yaml
schema_version: "1.1.0"
hauling:
  planning_horizon_days: 20
  start_day: 1
  log_sorts:
    - id: hemlock_saw_1
      product_id: hemlock_saw        # optional link to the tactical Product
      sorted: true
  contractors:
    - id: c1
      preferred_daily_truckloads: 12
  truck_types:
    - id: highway
      capacity_m3: 45
      fixed_cost: 120.0
      variable_cost_per_minute: 1.4
      overtime_cost_per_minute: 2.1
      can_carry_sorted: true
      can_carry_unsorted: true
  trucks:
    - id: c1_h1
      contractor_id: c1
      truck_type_id: highway
  depots:
    - id: depot
  sort_yards:
    - id: yard1
      facility_id: mill_a               # optional link to a tactical Facility
      unsorted_storage_m3: 5000
      sorted_processing_m3_per_day: 1200
      unsorted_processing_m3_per_day: 800
      total_processing_m3_per_day: 1600
  depot_legs:
    - {depot_id: depot, location_id: b1, truck_type_id: highway, travel_minutes: 35}
    - {depot_id: depot, location_id: yard1, truck_type_id: highway, travel_minutes: 30}
  loader_locations:
    - loader_id: loader_yard1
      location_id: yard1
      location_kind: delivery
  supply:
    - block_id: b1
      log_sort_id: hemlock_saw_1
      sorted_m3: 1200
      unsorted_m3: 800
  demand:
    - yard_id: yard1
      log_sort_id: hemlock_saw_1
      day: 1
      volume_m3: 200
  haul_arcs:
    - {block_id: b1, yard_id: yard1, truck_type_id: highway, travel_minutes: 180}
  contractor_blocks:
    - {contractor_id: c1, block_id: b1}
  driver_policy:
    regular_minutes: 510
    max_overtime_minutes: 150
    overtime_violation_penalty_per_minute: 10
  roadside_inventory_penalty_per_m3: 25
  loader_travel_cost_per_km: 0
  default_loader_service_minutes: 20
```

### Decisions resolved in P11.1

- **Schema version.** `1.1.0` is the hauling schema. `1.0.0` remains accepted without a hauling
  section; a `1.0.0` file that contains `hauling:` is refused. The loader previously ignored the
  YAML `schema_version` field; it now passes it through, which is required for the guard to work.
- **Log sorts versus products.** `LogSort.product_id` is an optional link. `LogSort` carries the
  sorted/unsorted distinction that `Product` does not.
- **Loaders.** Loaders are FHOPS `Machine` records, bound to a block or yard by
  `LoaderLocation`. Availability remains in the normal calendar/shift calendar.
- **Yards versus facilities.** `SortYard.facility_id` is an optional link to a tactical `Facility`.
  The hauling layer owns storage and processing capacities; it does not create a second facility
  registry.
- **Temporal resolution.** Phase I is day-level within one month; Phase II is one continuous working
  day. Shift calendars constrain availability but do not become a separate time index in the first
  release.
- **Compatibility.** `contractor_blocks` is an optional allowlist. Truck ownership and the
  truck-type sorted/unsorted flags carry the rest. The `compatibility` list is reserved for later
  exceptions.
- **Costs and services.** `roadside_inventory_penalty_per_m3`, `loader_travel_cost_per_km`, and
  `default_loader_service_minutes` cover the remaining thesis parameters. The full equation map is
  in `notes/hauling_formulation_audit.md`.

## 6. Phase I model (monthly daily flows)

### Indices and sets

- `B` blocks; `Y` sort yards; `S` log sorts; `R` truck types; `O` contractors; `T` days.
- Compatibility parameters `alpha[b,o]` (contractor can serve block), `beta[r,o]` (contractor owns
  truck type), `gamma[r]` (truck type can carry sorted logs), `epsilon[r]` (truck type can carry
  unsorted logs).

### Parameters

- `TT[b,y,r]` round-trip travel time including loading and unloading (hours).
- `TC[r]` transport cost per truck-hour.
- `SW[b,s]`, `SC[b,s]` sorted/unsorted supply volume (m3).
- `Q[r]` truck capacity (m3).
- `N[r,o]` number of trucks of type `r` owned by contractor `o`.
- `phi[o]` preferred daily truckloads for contractor `o`.
- `D[y,s,t]` demand for sort `s` at yard `y` on day `t`.
- `SCap[y]` unsorted storage capacity; `CW[y]`, `CC[y]`, `CY[y]` daily sorted, unsorted, and total
  processing capacities.
- `Tmax` maximum daily driving time; `P` penalty for roadside inventory at the horizon end.

### Decisions

- `vw[b,y,s,o,r,t]`, `vc[b,y,s,o,r,t]`: sorted/unsorted volume moved.
- `nw[b,y,s,o,r,t]`: integer truckloads of one sorted sort.
- `nc[b,y,o,r,t]`: integer truckloads of mixed unsorted logs.
- `ibw[b,s]`, `ibc[b,s]`: sorted/unsorted roadside inventory at the horizon end.
- `iw[y,s,t]`, `ic[y,s,t]`: water and unsorted inventory at the yard.
- `pv[y,s,t]`: unsorted volume of sort `s` processed at yard `y` on day `t`.
- `u[o]`: maximum absolute deviation from the contractor's preferred daily truckloads.

### Objectives

```text
min Z1 = sum_{t,b,y,r,o} (sum_s nw[b,y,s,o,r,t] + nc[b,y,o,r,t]) * TC[r] * TT[b,y,r]
       + sum_{b,s} P * (ibw[b,s] + ibc[b,s])

min Z2 = sum_o u[o]
```

`Z1` is transport cost plus the penalty for leaving wood at the roadside. `Z2` is the social
objective: the sum of each contractor's maximum daily deviation from its preferred workload.

### Core constraints

- Supply balance: every sorted and unsorted volume leaves the block or remains as end inventory.
- Compatibility: incompatible contractor/block/truck/sort combinations are forced to zero.
- Truckload linking: volume lies between `(n-1)Q` and `nQ`; a sorted load carries one sort, an
  unsorted load may mix sorts.
- Workload deviation: `|daily_truckloads[o,t] - phi[o]| <= u[o]`, linearised.
- Yard inventory: unsorted inventory carries over; processed volume becomes water inventory; demand
  is deducted from water inventory.
- Yard capacities: unsorted storage, sorted processing, unsorted processing, and total processing.
- Fleet capacity: truckloads times round-trip time cannot exceed owned trucks times `Tmax`.

### Goal programming

Solve the cost-only model to obtain `Goal1`; derive each contractor's desired daily load from that
solution unless the contractor supplies `phi[o]`; set `Goal2 = 0`; then minimise normalized positive
deviations:

```text
min w1 * dev1+ + w2 * dev2+
s.t. Z1 - dev1+ <= Goal1
     Z2 - dev2+ <= Goal2
```

The thesis reports that a small weight on balance (0.1-0.5) gives a smooth contractor workload at a
cost premium below 1 percent on its case. The implementation must expose the weights and record the
normalisation rule.

### Expected model size and solver strategy

The thesis case has roughly 3.08 million variables (1.04 million integer/binary) and 2.11 million
constraints for 20 days, 100+ blocks, 44 sorts, three yards, multiple contractors, and truck types.
That is not a routine CI instance. The implementation must:

- build sparse index sets, not dense cross-products;
- allow a rolling monthly window and a reduced sort/truck-type set;
- default to HiGHS with an explicit time limit;
- support `--driver gurobi` for larger cases;
- publish a synthetic case small enough for CI and a scale case for manual benchmarking.

## 7. Phase II model (daily routing and scheduling)

### Network representation

The thesis builds three coupled networks:

1. **Pickup loaders**: virtual start/sink plus one node per pickup; each pickup node is visited
   exactly once by a loader.
2. **Trucks**: central depot start/sink plus pickup and delivery nodes; each truckload has a fixed
   pickup-to-delivery arc; a truck may chain delivery-to-next-pickup arcs; every truckload node is
   visited exactly once.
3. **Delivery loaders**: virtual start/sink plus one node per delivery; each delivery node is
   visited exactly once by a loader.

Each truckload from Phase I fixes the pickup, delivery, responsible contractor, and compatible
truck type. There is one stationary loader at each pickup and delivery location in the thesis case;
P11.3 should generalise to a configurable loader set per location without changing the node
contract.

### Decisions

- `x[i,j,l]`: pickup loader `l` traverses arc `i -> j`.
- `y[i,j,o,k,v]`: contractor `o` uses truck `v` of type `k` on arc `i -> j`.
- `z[i,j,l]`: delivery loader `l` traverses arc `i -> j`.
- `t[i,l]`, `t[i,o,k,v]`: arrival times for loaders and trucks.
- `w[i]`, `u[i]`: truck and loader waiting time at node `i`.
- `e[o,k,v]`: overtime assigned to a truck.

### Objective

```text
min Z = sum fixed_cost[k] * dispatched[y]
      + sum variable_cost[k] * (return_time - overtime)
      + sum overtime_cost[k] * overtime
      + sum loader_travel_cost[l] * distance * x_or_z
```

The fixed cost is what makes "pay overtime" and "dispatch another truck" comparable. The thesis
finds that overtime is generally cheaper than dispatching an extra truck.

### Core constraints

- Depot start/end and flow balance for every loader and truck.
- Each pickup/delivery node visited exactly once by a loader and once by a truck.
- Truckloads assigned only to the contractor and compatible truck type fixed by Phase I.
- Fleet size and truck ownership.
- Time propagation with service time, travel time, and waiting time.
- Big-M linking: arrival times are computed only for visited nodes.
- Truck-loader synchronisation at pickup and delivery: both machines start service together; the
  earlier one waits.
- Regular-time limit and maximum overtime per truck.
- Binary/integer domains and non-negative time/waiting variables.

### Exact-solver scope

The thesis solves test problems up to 12 truckloads and 30 nodes with CPLEX at zero gap; at 13
truckloads the MIP becomes intractable. The real case has 81 truckloads and 168 nodes per day. The
implementation therefore uses the MIP for validation and small cases, and the SA solver for anything
larger.

## 8. Phase III simulated annealing

### Representation

A solution is a permutation of truckloads and delimiters. Delimiters separate trucks, truck types,
and contractors. A truckload carries a known pickup and delivery; the depot is prepended and
appended to each truck's route. The representation makes contractor and truck-type compatibility
structural, not a repair after the fact.

### Initial solution

Generate a random permutation for each truck type of each contractor, then concatenate the strings
with delimiters. Every truckload is assigned only to its responsible contractor and compatible truck
type, so compatibility is feasible by construction.

### SPT decoder

The decoder is the heart of the evaluation:

1. Compute each truckload's arrival time at its delivery assuming no waiting.
2. Put the truckloads in a `Pool` sorted by arrival time (shortest processing time first).
3. For each truckload in `Pool`: compute arrival at the pickup, wait for the pickup loader if busy,
   load, travel to the delivery, wait for the delivery loader if busy, unload.
4. If either wait is positive, update the arrival times of the remaining truckloads and re-sort the
   `Pool`.
5. After all truckloads, add the return-to-depot travel, split regular and overtime minutes, and add
   a penalty for overtime above the maximum.

The decoder returns the full schedule, overtime, and cost. It must be deterministic for a fixed
solution and instance.

### Neighbourhood and acceptance

- Swap two random cells.
- Reverse the segment between two random cells.
- Remove one cell and insert it after another.
- Apply one operator to a randomly selected contractor's truckloads.
- Accept an improving solution; accept a worse solution with probability `exp(-delta / T)`.
- Cool geometrically: `T <- alpha * T`; stop at `T_min`.

The thesis calibrates `T0`, `T_min`, `alpha`, and the iterations per temperature with a Taguchi L9
design. Its selected defaults are `T0 = 300`, `T_min = 0.0005 * T0`, `alpha = 0.95`, and 90
iterations per temperature. These become FHOPS defaults but remain configurable; FHOPS must not
hard-code a case-specific calibration.

### Expected performance

The thesis reports zero-gap matches to CPLEX on eight small test problems, with SA times of
0.33-1.23 seconds versus 3-3,417 seconds for CPLEX, and a 125.8-second solution for the 81-truckload,
168-node case. Those are the benchmark targets for a comparable synthetic instance.

## 9. Integration with FHOPS

### From operational plans

The operational solver produces `(machine, block, day, shift)` assignments and completed work. The
hauling bridge should accept either:

- an assignment CSV plus a scenario, then derive delivered volume from block `work_required` and
  productivity; or
- an explicit supply table, which is the only option when the harvest plan is external.

The bridge must not invent a log-sort split silently. If the scenario carries only aggregate volume,
it must either require a supplied split or apply a documented, visible default.

### From tactical plans

The tactical-operational model already has products, planning units, facility demand, transport
arcs, and inventory. The bridge should:

- select a tactical period (or a contiguous set of days) as the hauling horizon;
- turn `production`/`product_volume` into `supply`;
- turn `facility_demand`/`consumption` into `demand`;
- turn `transport_arcs` into candidate `haul_arcs`, enriching them with travel times and truck-type
  eligibility;
- map `Facility` identity to `sort_yards`/mills;
- report any tactical flow that the hauling model cannot reproduce.

The hauling layer must not silently override a tactical plan. It reports the residual or refuses
the handoff when the demand cannot be met.

### Loaders and calendars

Reuse `Machine` for loaders, with a location binding in `hauling.loader_locations`. Reuse
`calendar`/`shift_calendar` for availability. A loader that is unavailable on a day must be absent
from that day's pickup or delivery network, and the model must report infeasibility rather than
schedule it.

### Time

- Phase I: one month, daily buckets; `planning_horizon_days` defaults to 20 working days.
- Phase II: one day, continuous minutes; `driver_policy.regular_minutes` defaults to 510 (8.5 h) and
  `max_overtime_minutes` to 150 (2.5 h), matching the thesis.
- Shift calendars constrain which day/shift a loader or truck may work. The first release schedules
  within a day and treats shifts as availability windows; a shift-indexed continuous-time extension
  is out of scope unless P11.3 proves it necessary.

## 10. Outputs and KPIs

### Files

| File | Contents |
|---|---|
| `haul_flows.csv` | Day, block, yard, sort, contractor, truck type, volume, truckloads |
| `haul_yard_inventory.csv` | Day, yard, sort, unsorted inventory, water inventory, processed volume |
| `haul_contractor_workload.csv` | Day, contractor, truckloads, deviation from preferred |
| `haul_truckloads.csv` | Truckload id, block, yard, sort, contractor, truck type, volume |
| `haul_schedule.csv` | Truckload, truck, loader(s), arrival/wait/start/finish at pickup and delivery |
| `haul_truck_summary.csv` | Truck, contractor, type, dispatched, truckloads, regular/overtime minutes, cost |
| `haul_kpis.json` | Cost, transport cost, overtime cost, inventory penalty, workload deviation, utilisation, waiting |
| `haul_summary.json` | Run metadata, status, seed, objective, solver, horizon, file manifest |

### KPIs

- Total logistics cost, split into transport, overtime, loader travel, and roadside inventory penalty.
- Contractor workload mean, maximum deviation, and Gini-like balance index (optional).
- Truck utilisation: dispatched trucks, loads per truck, regular and overtime minutes.
- Loader utilisation and total waiting time at each pickup/delivery.
- Yard storage peak and processing utilisation.
- Delivered volume versus demand, by sort and yard.
- Feasibility diagnostics: unmet demand, incompatible assignments, overtime violations, capacity
  violations.

## 11. CLI and Python API

Proposed CLI:

```bash
fhops haul validate examples/hauling/scenario.yaml
fhops haul plan examples/hauling/scenario.yaml --out-dir runs/haul-plan
fhops haul schedule runs/haul-plan --day 3 --out-dir runs/haul-day3
fhops haul solve examples/hauling/scenario.yaml --day 3 --solver sa --iters 50000
fhops haul report runs/haul-day3 --format markdown
```

Proposed Python API:

```python
from fhops.hauling import (
    build_hauling_problem,
    solve_monthly_flow,
    solve_daily_schedule,
    solve_daily_schedule_sa,
    summarize_hauling_run,
)
```

Names are provisional; P11.1 fixes the public surface and docstrings.

## 12. Validation plan

### Unit and contract tests

- Every new Pydantic model accepts valid data and rejects unknown IDs, negative capacities, and
  impossible compatibility.
- Round-trip YAML/CSV loading.
- Existing 1.0.0 scenarios load unchanged.
- Synthetic bundles with a `hauling:` block load and validate.

### Formulation tests

- Supply balance, inventory balance, capacity, compatibility, and fleet constraints hold on a
  hand-checkable tiny instance.
- The goal-programming model reproduces the single-objective cost when `w2 = 0`.
- The Phase II MIP produces a feasible schedule with zero synchronisation violations.
- The SA decoder produces exactly the same schedule as a direct simulation of the decoded routes.

### Parity and regression

- Phase II MIP versus SA on thesis-shaped TP1-TP8 (9-12 truckloads, 24-30 nodes): zero gap or a
  stated tolerance; record objective and runtime.
- A 13-truckload instance that is intractable for the MIP but solvable by SA.
- The 81-truckload/168-node synthetic case: SA under three minutes on the reference host; schedule
  feasible; waiting time reported by yard.
- Golden files for the tiny case, regenerated only with a documented reason.

### Integration tests

- Operational assignment -> hauling supply -> Phase I -> Phase II -> KPI report.
- Tactical period -> hauling demand -> Phase I -> Phase II -> report.
- A scenario with an unavailable loader or an incompatible truck must fail with a named diagnostic,
  not an empty plan.

### Documentation and gates

- `docs/howto/hauling.rst`: data authoring, CLI, outputs, interpretation, limitations.
- `docs/reference/hauling.rst`: API and model reference.
- Canonical formulation Markdown/TeX/RST, regenerated and drift-checked like the existing
  operational and tactical formulations.
- `notes/log_hauling_expansion_plan.md` updated as tasks close.
- `ROADMAP.md`, `CHANGE_LOG.md`, and the issue tree kept in step.
- All FHOPS gates green: `ruff format`, `ruff check`, `mypy`, `pytest`, pre-commit, Sphinx, and
  formulation asset checks.

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| The thesis case data is confidential, so exact dollar reproduction is impossible. | State the limit; validate structural fidelity and synthetic parity; do not claim a case replication. |
| Phase I is huge (millions of variables). | Sparse indices, reduced instances, time limits, Gurobi option, rolling monthly windows. |
| Continuous-time MIP does not scale beyond ~12 truckloads. | Use the MIP for validation, SA for production; publish the crossover point. |
| Thesis equations contain typos or ambiguous indexing. | Formulation audit in P11.1; record each clarification; test the intended semantics. |
| Hauling duplicates tactical transport arcs. | Make the tactical layer the source of demand and candidate arcs; hauling adds time, equipment, and synchronization. |
| Loader/truck synchronization constraints are easy to state and hard to linearise correctly. | Build a direct simulation oracle and property tests before trusting the MIP. |
| SA calibration is case-specific. | Ship thesis defaults but require per-instance calibration; expose Taguchi/parameter sweeps. |
| The web UI (P12) needs hauling outputs. | Define the output files in P11.5 and keep them stable; P12 reads artefacts, not internals. |
| Scope creep into emissions, uncertainty, or live dispatch. | Keep them explicitly out of scope; record as future work. |

## 14. Child tasks

- **#172 P11.1** Provenance, contract, and formulation audit. Complete (`1e32fce`).
- **#173 P11.2** Phase I monthly flow MILP and goal programming. Complete (`77aea82`).
- **#174 P11.3** Phase II daily routing and scheduling MILP. Complete (`3bb621c`).
- **#175 P11.4** SA solution approach, SPT decoder, and calibration. Complete (`d06c3be`).
- **#176 P11.5** FHOPS integration, CLI, reporting, and example case. Complete (`5143743`).
- **#177 P11.6** Validation, documentation, formulation sync, and close-out. Complete; see `notes/reports/p11-closeout.md`.
- **#177 P11.6** Validation, documentation, formulation sync, and close-out.

The detailed issue bodies carry the subtasks, acceptance criteria, and verification commands.

## 15. Acceptance criteria for the phase

- A synthetic FHOPS scenario with a `hauling:` block validates, builds a Phase I model, solves it,
  and writes the documented flow outputs.
- The Phase II MIP produces a feasible daily schedule with zero synchronization violations on a
  small case.
- The SA solver matches the MIP objective on the thesis-shaped small cases and solves the scaled
  synthetic case within the stated time budget.
- The operational and tactical handoff paths both produce a feasible haul plan, or fail with a
  named, actionable diagnostic.
- Existing scenarios and workflows are unchanged without the `hauling:` block.
- The public formulation, docs, CLI help, tests, and changelog are complete.
- All FHOPS gates are green on the phase branch.

## 16. Out-of-scope follow-ups to record, not start

- Emissions and carbon accounting for hauling.
- Electric-truck range and charging-station synchronization.
- Robust/stochastic supply, demand, and loader breakdowns.
- Lunch breaks, driver changes, and full hours-of-service rules.
- Contractor collaboration and shared blocks.
- Dynamic re-optimization after disruptions.
- Integration with a commercial transport-management system.
