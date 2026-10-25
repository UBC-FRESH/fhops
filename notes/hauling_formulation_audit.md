# Log Hauling Formulation Audit

Date: 2026-10-25
Phase: P11
Task: #172 (P11.1)
Source: Ghotb, S. (2023), *Optimization of Log Logistics at the Operational Level Considering
Sorting Decisions and Synchronization Requirements*, PhD thesis, University of British Columbia,
<https://hdl.handle.net/2429/85563>

This note is the equation-level bridge between the thesis and the FHOPS implementation. It records
what each equation means, how the contract represents its inputs, and every deliberate correction or
clarification. P11.2-P11.4 must cite this note when they implement the models and solver.

## 1. Thesis structure

| Chapter | Content | FHOPS task |
|---|---|---|
| 3 | Bi-objective monthly flow MIP (cost and contractor workload) solved by goal programming | P11.2 |
| 4 | One-day continuous-time pickup-and-delivery MIP with truck/loader synchronization | P11.3 |
| 5 | Simulated-annealing solution approach with an SPT schedule decoder and Taguchi calibration | P11.4 |
| 6 | Conclusions, strengths, limitations, future work | Out of scope |

The published journal versions are:

- Ghotb et al. (2022), *Canadian Journal of Forest Research* 52(5), 716-726, for Chapter 3.
- Ghotb et al. (2024), *International Journal of Forest Engineering* 35(2), 313-325, for Chapter 4.
- Ghotb et al. (2024), *Expert Systems with Applications* 238, 122008, for Chapter 5.

## 2. Phase I equation map (Chapter 3)

### 2.1 Sets and parameters

| Thesis | Meaning | FHOPS contract |
|---|---|---|
| `B` | Cut blocks | `Scenario.blocks` |
| `Y` | Sort yards | `HaulingConfig.sort_yards` |
| `S` | Log sorts | `HaulingConfig.log_sorts` |
| `R` | Truck types | `HaulingConfig.truck_types` |
| `O` | Contractors | `HaulingConfig.contractors` |
| `T` | Days | `HaulingConfig.planning_horizon_days`, `start_day` |
| `TT_byr` | Round-trip travel time including loading/unloading (hours) | `HaulArc.travel_minutes` + service times; Phase I derives the round trip |
| `TC_r` | Transport cost per truck-hour | `TruckType.variable_cost_per_minute` (convert) |
| `SW_bs`, `SC_bs` | Sorted/unsorted supply (m3) | `HaulingSupply.sorted_m3`, `unsorted_m3` |
| `Q_r` | Truck capacity (m3) | `TruckType.capacity_m3` |
| `alpha_bo` | Contractor can serve block | `HaulingConfig.contractor_blocks` allowlist |
| `beta_ro` | Contractor owns truck type | `HaulingConfig.trucks` |
| `N_ro` | Number of trucks of type `r` owned by `o` | Count of `Truck` records |
| `phi_o` | Preferred daily truckloads | `Contractor.preferred_daily_truckloads` |
| `gamma_r`, `epsilon_r` | Truck type can carry sorted/unsorted | `TruckType.can_carry_sorted`, `can_carry_unsorted` |
| `D_yst` | Demand volume | `HaulingDemand.volume_m3` |
| `SC_y`, `CW_y`, `CC_y`, `CY_y` | Yard storage and processing capacities | `SortYard` fields |
| `Tmax` | Maximum daily driving time | `DriverPolicy.regular_minutes` |
| `P` | Roadside-inventory penalty | `HaulingConfig.roadside_inventory_penalty_per_m3` |
| `M` | Big-M | Computed from tight supply/fleet bounds; never a magic constant |

### 2.2 Objective functions

- **(3-1)** `min Z1 =` transport cost `(sum_s nw + nc) * TC_r * TT_byr` plus
  `P * (ibw + ibc)` for roadside inventory at the horizon end.
- **(3-2)** `min Z2 = sum_o u_o`, where `u_o` is the maximum absolute deviation of contractor `o`'s
  daily truckloads from `phi_o`.

Implementation notes:

- The transport term is per truckload, not per cubic metre. A load that is not full still pays a
  truck cycle.
- `TT_byr` in the thesis includes the back-and-forth trip and loading/unloading. The FHOPS contract
  stores loaded travel only; P11.2 derives the cycle as `2 * loaded_travel + load_service +
  unload_service` (or the configured one-way/return pair when the return leg differs).
- `P` is applied only to end-of-horizon inventory at the block, not to yard inventory.

### 2.3 Constraints

- **(3-3)/(3-4)** Supply balance for sorted and unsorted volume:
  `sum_{t,o,r,y} volume + end_inventory = supply`.
- **(3-5)/(3-6)** Compatibility big-M: incompatible contractor/block/truck combinations are zero.
  FHOPS uses tight bounds derived from supply and fleet capacity rather than a single `M`.
- **(3-7)/(3-8)** Truckload linking:
  `(n - 1) * Q <= volume <= n * Q`. A sorted load carries one sort; an unsorted load may mix sorts.
- **(3-9)** Workload deviation: `|daily_truckloads_o - phi_o| <= u_o`. The absolute value is
  linearised in P11.2 with two inequalities (or a positive/negative deviation pair).
- **(3-10)/(3-11)** Yard inventory:
  - unsorted: `ic_t = ic_{t-1} + delivered_unsorted - processed`;
  - water: `iw_t = iw_{t-1} + delivered_sorted + processed - demand`.
  Initial conditions are the `SortYard.initial_*` fields. The thesis leaves the boundary implicit;
  FHOPS makes it explicit.
- **(3-12)** Unsorted storage: `sum_s ic_yst <= SC_y`.
- **(3-13)** Sorted processing: the delivered sorted volume is treated as processed at the yard.
- **(3-14)** Unsorted processing: `sum_s pv_yst <= CC_y`.
- **(3-15)** Total processing: delivered sorted plus processed unsorted `<= CY_y`.
- **(3-16)** Fleet capacity: `sum_{b,y} truckloads * TT_byr <= N_ro * Tmax` for each contractor and
  truck type on each day.
- **(3-17)/(3-18)** Domains: volumes, inventories, and processed volume non-negative; truckloads,
  `u_o` integer.

Clarifications:

- The thesis writes equation (3-9) with an absolute value; the implementation must linearise it.
- The thesis writes `u_o` as integer. The contract stores truckloads as integers, so an integer
  deviation is natural, but a non-negative continuous deviation is equivalent for the objective and
  is more solver-friendly. P11.2 must choose one and document it.
- Equations (3-13)-(3-15) use "process" for sorted logs. The intended reading is that a sorted load
  passes through the yard's processing capacity when it is delivered; the implementation must state
  this rather than treating sorted volume as free.

### 2.4 Goal programming

- **(3-19)** `min Z = w1 * dev1+ + w2 * dev2+`.
- **(3-20)** `Z1 - dev1+ <= Goal1`.
- **(3-21)** `Z2 - dev2+ <= Goal2`.
- **(3-22)/(3-23)** Domain of deviations.

Inconsistency to resolve: the thesis says `dev1+ >= 0` and `dev2+` integer, while the CJFR paper
says `dev1+` integer and `dev2+ >= 0`. The implementation should use non-negative continuous
deviations for both (goal deviations are costs and truckload counts; integrality is not required for
the objective) and record the deviation in P11.2. The normalisation of `Z1` and `Z2` must be
documented because the two objectives have different scales.

## 3. Phase II equation map (Chapter 4)

### 3.1 Networks

The thesis builds three coupled networks:

1. **Pickup loaders** `G1 = (N1, A1)`, with virtual depot `c+`/`c-` and one node per pickup.
2. **Trucks** `G2 = (N2, A2)`, with real depot `f+`/`f-` and pickup plus delivery nodes.
3. **Delivery loaders** `G3 = (N3, A3)`, with virtual depot `g+`/`g-` and one node per delivery.

Each truckload is a fixed pickup-to-delivery pair. A truck may chain a delivery to the next pickup.
A loader is stationary at a location in the thesis case; P11.3 generalises to a configured loader
set per location.

### 3.2 Parameters and decisions

| Thesis | Meaning | FHOPS contract |
|---|---|---|
| `FC_k` | Fixed truck cost | `TruckType.fixed_cost` |
| `VC_k` | Variable truck cost per minute | `TruckType.variable_cost_per_minute` |
| `OC_k` | Overtime cost per minute | `TruckType.overtime_cost_per_minute` |
| `DC_l` | Loader travel cost per km | `HaulingConfig.loader_travel_cost_per_km` |
| `DIS(i,j)` | Distance between nodes | `HaulArc.distance_km`, `DepotLeg` |
| `D_ijl`, `D_ijk` | Loader/truck travel time | `DepotLeg`, `HaulArc` |
| `S_i` | Service time at node | `LoaderLocation.service_minutes` or `default_loader_service_minutes` |
| `Tmax` | Regular minutes | `DriverPolicy.regular_minutes` |
| `Emax` | Maximum overtime | `DriverPolicy.max_overtime_minutes` |
| `x_ijl`, `y_ijokv`, `z_ijl` | Loader/truck arcs | Phase II decisions |
| `t_il`, `t_iokv` | Arrival times | Phase II decisions |
| `w_i`, `u_i` | Truck/loader waiting | Phase II decisions |
| `e_okv` | Overtime | Phase II decisions |

### 3.3 Objective

- **(4-1)** Fixed dispatch cost + variable regular-time cost + overtime cost + loader travel cost.

Implementation notes:

- Charge the fixed cost once per dispatched truck (`y_{f+ j}`), not once per load.
- The variable cost is `VC_k * (return_time - overtime)`, i.e. regular minutes only.
- With stationary loaders, the loader travel terms are zero; the implementation should not invent
  inter-location travel. The `loader_locations` binding enforces the stationary case without a
  big-M distance matrix.

### 3.4 Constraints

- **(4-2)-(4-7)** Pickup loaders: depot start/end, at most one departure, flow balance, arrival-time
  propagation, and big-M linking.
- **(4-8)-(4-15)** Trucks: depot start/end, optional dispatch, flow balance, compatibility, fleet
  size, arrival-time propagation, and big-M linking.
- **(4-16)-(4-21)** Delivery loaders: the same structure for unloading.
- **(4-22)-(4-24)** Each pickup/delivery node is visited exactly once by the appropriate loader and
  by one truck; every truckload is delivered.
- **(4-25)/(4-26)** Synchronization at pickup and delivery: the loader and truck start service
  together, and the earlier one waits.
- **(4-27)/(4-28)** Overtime: return time `<= Tmax + e` and `e <= Emax`.
- **(4-29)/(4-30)** Domains.

Corrections and clarifications:

1. **Equation (4-14)** indexes the destination as `N1`; the intended set is `N2`.
2. **Equation (4-15)** uses `e+`/`e-`; the intended depot nodes are `f+`/`f-`.
3. **Synchronization (4-25)/(4-26)** is the critical correction. The thesis writes a sum of arrival
   times over every loader or truck at the node. That is only correct if exactly one machine is at
   the node. The implementation must link the assigned loader and truck explicitly, for example with
   an assignment variable and a big-M, or with a start-time variable per (node, machine) and a
   constraint that equals the assigned pair. A literal sum over all machines is not correct when
   multiple trucks visit a node.
4. **Waiting variables** `w_i` and `u_i` are defined per node in the thesis. With multiple visitors,
   they must be per node and machine (or per truckload) rather than a single node value.
5. **Overtime** is a lower-bound variable in (4-27). Because the objective minimises overtime cost,
   it will equal `max(0, return_time - Tmax)` when the cost is positive. P11.3 must document what
   happens when overtime cost is zero.
6. **Node identity** must be unique per truckload pickup/delivery. A block or yard can have several
   nodes; the network builder must not collapse them.
7. **Stationary loaders.** The thesis sets within-location distance to zero and between-location
   distance to a very large number. FHOPS uses `loader_locations` instead, which is clearer and
   avoids a big-M. P11.3 must reject a loader assigned to two locations.

## 4. Phase III solution approach (Chapter 5)

### 4.1 Representation

- A solution is a permutation of truckloads and delimiters.
- Delimiters separate trucks, truck types, and contractors.
- Each truckload has a fixed pickup and delivery.
- The depot is prepended and appended to each truck's route.

### 4.2 Initial solution

- For each contractor and truck type, generate a random permutation of the eligible truckloads.
- Concatenate the strings with delimiters.
- Compatibility is feasible by construction: each truckload is assigned only to its responsible
  contractor and compatible truck type.

### 4.3 SPT decoder (Algorithm 2)

1. Compute each truckload's arrival time at its delivery assuming no waiting.
2. Sort the truckloads by arrival time (shortest processing time first) into `Pool`.
3. For each truckload in `Pool`:
   - compute arrival at the pickup;
   - wait for the pickup loader if busy, then load;
   - travel to the delivery;
   - wait for the delivery loader if busy, then unload.
4. If either wait is positive, update the remaining arrival times and re-sort `Pool`.
5. After all truckloads, add the return-to-depot travel, split regular and overtime minutes, and add
   the overtime-violation penalty.

Implementation requirements:

- Deterministic tie-breaking in the `Pool` sort.
- The decoder must be usable as a standalone oracle for the Phase II MIP.
- The waiting-time update must be local to the affected truck and loaders, not a full recomputation
  that changes unrelated arrival times.

### 4.4 Neighbourhood and acceptance

- Swap two random cells.
- Reverse the segment between two random cells.
- Remove one cell and insert it after another.
- Apply an operator to a randomly selected contractor's truckloads.
- Accept improving solutions; accept worse solutions with probability `exp(-delta / T)`.
- Cool geometrically `T <- alpha * T`; stop at `T_min`.

The thesis writes `p = e(-delta/T)`; the intended expression is `exp(-delta/T)`.

### 4.5 Calibration

The Taguchi L9 study selects:

| Parameter | Thesis value |
|---|---|
| Initial temperature `T0` | 300 |
| Minimum temperature `Tmin` | 0.0005 * T0 |
| Cooling rate `alpha` | 0.95 |
| Iterations per temperature | 90 |

These are FHOPS defaults, not hard-coded case values. P11.4 must expose them and record the
calibration evidence.

## 5. Contract coverage check

| Thesis input | Contract field | Status |
|---|---|---|
| Blocks, machines, landings | `Scenario` | Reused |
| Log sorts | `LogSort` | Added |
| Contractors and preferred workload | `Contractor` | Added |
| Truck types, capacity, costs, compatibility | `TruckType` | Added |
| Individual trucks and ownership | `Truck` | Added |
| Central depot | `Depot` | Added |
| Depot-to-location travel | `DepotLeg` | Added |
| Yard storage/processing capacities | `SortYard` | Added |
| Loader availability and location | `LoaderLocation` + `Scenario.machines` | Added |
| Supply and demand | `HaulingSupply`, `HaulingDemand` | Added |
| Haul arcs and travel time | `HaulArc` | Added |
| Contractor-block eligibility | `ContractorBlock` | Added |
| Driver regular/overtime policy | `DriverPolicy` | Added |
| Roadside inventory penalty | `HaulingConfig.roadside_inventory_penalty_per_m3` | Added |
| Loader travel cost | `HaulingConfig.loader_travel_cost_per_km` | Added (zero for stationary loaders) |

## 6. Open questions for P11.2-P11.4

1. Should Phase I represent `TT_byr` as a stored round-trip time or derive it from loaded travel,
   empty return, and service times? Recommendation: derive it, with an optional explicit override.
2. Should `u_o` and the goal deviations be integer or continuous? Recommendation: continuous
   deviations; integer truckloads.
3. How should a partial truckload be charged? Recommendation: one truckload cycle per started load,
   as in the thesis.
4. How should a yard's sorted-processing capacity interact with a sorted load that is not actually
   processed? Recommendation: treat delivery to a sort yard as processing for the sorted capacity,
   as the thesis does, and document it.
5. Should Phase II allow a truck to wait at the depot or return mid-day? The thesis routes a truck
   from the depot through its loads and back; no mid-day depot return. Recommendation: keep that
   restriction in the first release.
6. How should missing depot legs or loader bindings be handled? Recommendation: fail with a named
   diagnostic; never invent a travel time or a loader.

## 7. Acceptance for P11.1

- The contract covers every thesis input listed in section 5.
- A scenario with a valid `hauling:` section loads and reports its dimensions.
- A `1.0.0` scenario without hauling still loads; a `1.0.0` scenario with hauling is refused.
- Unknown references, duplicate records, invalid capacities, and horizon overflow are refused with a
  named field and record.
- The example in `examples/hauling/` validates.
- This audit is the reference for P11.2-P11.4.

## 8. P11.2 implementation decisions

The Phase I model is in `src/fhops/hauling/flow.py`. Its choices are:

1. **Compatibility by index restriction.** Instead of Ghotb's big-M constraints (3-5)/(3-6), the
   model only creates a sorted or unsorted variable when the contractor can serve the block, owns a
   truck of the type, the type can carry that load kind, and a haul arc exists. This is equivalent
   and tighter. A supply that has no feasible arc remains at the block and pays the roadside
   inventory penalty.
2. **Workload linearisation.** The absolute-value constraint (3-9) is implemented as
   `loads - phi_o <= u_o` and `phi_o - loads <= u_o`.
3. **Continuous goal deviations.** `dev_cost` and `dev_workload` are non-negative continuous
   variables. This resolves the thesis/paper disagreement and avoids integrality that the objective
   does not need.
4. **Goal normalisation.** The goal objective is
   `w1 * dev_cost / max(|Goal1|, 1) + w2 * dev_workload / max(sum(phi), 1)`.
   The second scale is the sum of preferred daily truckloads, not `Goal2` (which is usually zero).
5. **Cycle time.** `cycle_minutes = 2 * HaulArc.travel_minutes + pickup_service +
   delivery_service`. The pickup/delivery service is the fastest configured loader at that
   location, or `HaulingConfig.default_loader_service_minutes` when no loader binding supplies a
   value.
6. **Transport cost.** `TruckType.variable_cost_per_minute * cycle_minutes` is charged per started
   truckload. `TruckType.fixed_cost` is intentionally not used in Phase I; Phase II charges it when
   a truck is dispatched.
7. **Fleet capacity.** The model uses `TruckType` counts from enabled `Truck` records and the
   `DriverPolicy.regular_minutes` limit. It does not add `max_overtime_minutes` to Phase I.
8. **Roadside penalty.** The contract accepts a zero penalty, but a zero penalty makes leaving all
   supply at the block cost-free. The example sets a positive penalty and the how-to says so.
9. **Goal goals.** A goal solve with no explicit goals runs a cost-only solve, uses `Z1` as
   `Goal1`, sets `Goal2 = 0`, and derives `phi_o` from the cost plan's average daily truckloads.
10. **Solver.** HiGHS is the default. `gurobi` is accepted when installed and licensed. Infeasible
    HiGHS solves are reported as `status="infeasible"` rather than a generic error.

The result payload is documented in `docs/howto/hauling.rst` and in the `FlowSolveResult`
docstring.
