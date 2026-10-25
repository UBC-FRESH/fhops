Log Hauling
===========

FHOPS can carry an optional **log-hauling layer** on top of the operational scenario. The layer adds
the entities that the harvesting and tactical-operational contracts do not carry: log sorts,
contractors, truck types and trucks, depots, sort yards, haul arcs, loader location bindings, and a
driver policy.

The model follows the two-phase decomposition in Ghotb (2023):

1. **Phase I** decides daily sorted and unsorted log flows from blocks and landings to sort yards,
   yard processing, inventory, and contractor workload.
2. **Phase II** assigns the resulting truckloads to compatible trucks and contractors and schedules
   trucks and loaders with continuous time, synchronization, and overtime.
3. **Phase III** solves the large daily scheduling instances with simulated annealing and an SPT
   schedule decoder.

P11.1 ships the contract and validation. P11.2 adds the Phase I flow model and goal programming.
P11.3 adds the Phase II continuous-time scheduling model and its simulator/validator. P11.4 adds
the simulated-annealing solver for larger days. P11.5 adds the `fhops haul` CLI, the operational/
tactical bridges, and the stable run artefacts. P11.7 adds the explicit marine/barge path
(`TransportMode`, barges, ports, water arcs, and port-to-port cycles). The Phase I/II/III models
remain available from Python.

Schema version
--------------

The hauling extension uses ``schema_version: "1.1.0"``. The loader still accepts ``1.0.0``
scenarios, which have no hauling section. A scenario that contains ``hauling:`` with
``schema_version: 1.0.0`` is refused: the version is the guard that tells an older reader the file
has a section it does not understand.

Minimal example
---------------

The complete example is in ``examples/hauling/``. The core bundle is a normal FHOPS scenario; the
``hauling:`` section is additive.

.. code-block:: yaml

   name: Hauling demo
   num_days: 20
   schema_version: 1.1.0
   data:
     blocks: blocks.csv
     machines: machines.csv
     landings: landings.csv
     calendar: calendar.csv
     prod_rates: production_rates.csv
   hauling:
     planning_horizon_days: 5
     start_day: 1
     log_sorts:
       - {id: fir_saw, product_id: fir_saw, sorted: true}
       - {id: mixed_unsorted, sorted: false}
     contractors:
       - {id: c1, preferred_daily_truckloads: 8}
     truck_types:
       - id: highway
         capacity_m3: 45
         fixed_cost: 120.0
         variable_cost_per_minute: 1.2
         overtime_cost_per_minute: 1.8
         can_carry_sorted: true
         can_carry_unsorted: true
     trucks:
       - {id: c1_h1, contractor_id: c1, truck_type_id: highway}
     depots:
       - {id: depot}
     sort_yards:
       - id: y1
         unsorted_storage_m3: 5000
         sorted_processing_m3_per_day: 1500
         unsorted_processing_m3_per_day: 800
         total_processing_m3_per_day: 2000
     loader_locations:
       - {loader_id: ldr_b1, location_id: b1, location_kind: pickup}
       - {loader_id: ldr_y1, location_id: y1, location_kind: delivery}
     supply:
       - {block_id: b1, log_sort_id: fir_saw, sorted_m3: 800, unsorted_m3: 0}
     demand:
       - {yard_id: y1, log_sort_id: fir_saw, day: 1, volume_m3: 160}
     haul_arcs:
       - {block_id: b1, yard_id: y1, truck_type_id: highway, travel_minutes: 150}
     depot_legs:
       - {depot_id: depot, location_id: b1, truck_type_id: highway, travel_minutes: 35}
       - {depot_id: depot, location_id: y1, truck_type_id: highway, travel_minutes: 30}
     contractor_blocks:
       - {contractor_id: c1, block_id: b1}
     driver_policy:
       regular_minutes: 510
       max_overtime_minutes: 150
       overtime_violation_penalty_per_minute: 10

The section may also live in a separate YAML file referenced from ``data.hauling``:

.. code-block:: yaml

   data:
     hauling: hauling.yaml

Marine and barge legs
---------------------

A barge is **not** a truck type. The contract gives marine transport its own equipment and
topology so the model can report water volume, barge trips, terminal handling, and port
synchronization instead of silently applying truck capacity and a road cycle.

The marine path is a four-part chain:

1. a **road pickup leg** from a block to an origin :class:`Port`;
2. **terminal handling** at the origin port;
3. a **water leg** on a :class:`WaterArc` operated by a :class:`Barge` of a
   :class:`BargeType`;
4. **terminal handling** at the destination port and a **road delivery leg** to the sort yard.

A :class:`MarineRoute` binds those parts to a block, yard, contractor, drayage truck type, port
pair, and water arc. Phase I treats the marine route as an alternative supply path with separate
pickup, water, and delivery volumes. Phase II schedules the road drayage loads in the truck/loader
MIP and schedules the barge cycles with :mod:`fhops.hauling.marine`. The barge scheduler assigns
port loaders, loads, sails, unloads, returns empty, and reports the synchronized pickup and delivery
truck windows.

The redistributable fixture is ``examples/hauling_marine/``. It represents a synthetic Sunshine
Coast pickup, a Sechelt terminal, a water leg to Howe Sound, and a Howe Sound terminal feeding a
sort yard:

.. code-block:: yaml

   hauling:
     log_sorts:
       - {id: fir_saw, sorted: true}
     truck_types:
       - {id: highway, capacity_m3: 45, variable_cost_per_minute: 1.2}
     trucks:
       - {id: c1_h1, contractor_id: c1, truck_type_id: highway}
     barge_types:
       - {id: log_barge, capacity_m3: 3000, load_minutes: 30, unload_minutes: 30}
     barges:
       - {id: c1_b1, contractor_id: c1, barge_type_id: log_barge}
     ports:
       - {id: sechelt, storage_m3: 500, handling_minutes_per_trip: 20,
          handling_cost_per_trip: 100, daily_handling_m3: 1000}
       - {id: howe_sound, storage_m3: 500, handling_minutes_per_trip: 25,
          handling_cost_per_trip: 120, daily_handling_m3: 1000}
     water_arcs:
       - {id: sc_hs, origin_port_id: sechelt, destination_port_id: howe_sound,
          barge_type_id: log_barge, travel_minutes: 200, distance_km: 80,
          return_travel_minutes: 200, load_minutes: 30, unload_minutes: 30}
     port_legs:
       - {port_id: sechelt, location_id: b_sc, side: origin,
          truck_type_id: highway, travel_minutes: 35, return_travel_minutes: 35}
       - {port_id: howe_sound, location_id: y1, side: destination,
          truck_type_id: highway, travel_minutes: 30, return_travel_minutes: 30}
     marine_routes:
       - {id: sc_hs_y1, block_id: b_sc, yard_id: y1, origin_port_id: sechelt,
          destination_port_id: howe_sound, water_arc_id: sc_hs,
          contractor_id: c1, truck_type_id: highway}
     loader_locations:
       - {loader_id: loader_sechelt, location_id: sechelt, location_kind: port}
       - {loader_id: loader_howe_sound, location_id: howe_sound, location_kind: port}

Run the fixture with:

.. code-block:: bash

   fhops haul validate examples/hauling_marine/scenario.yaml
   fhops haul plan examples/hauling_marine/scenario.yaml --out-dir runs/marine-plan
   fhops haul schedule examples/hauling_marine/scenario.yaml --day 1 \
       --flow-dir runs/marine-plan --out-dir runs/marine-day1
   fhops haul report runs/marine-day1

The contract rejects a barge-named ``TruckType`` (``barge``, ``vessel``, ``ferry``, ``marine``, or
``ship``) with a message that names the marine entities to declare instead. A ``HaulArc`` accepts
only ``mode: road``; water legs must use a ``WaterArc`` and ``MarineRoute``. If any marine entity is
present but no ``MarineRoute`` connects it to a block and yard, validation fails rather than
silently ignoring the marine data.

Marine assumptions and limits:

- Phase I uses the barge capacity for the water leg, the truck capacity for the drayage legs, and
  charges barge variable and per-trip terminal handling separately from drayage cost. The barge
  scheduler charges the barge type's fixed dispatch cost once per used barge.
- Port inventory carries over between days; ``storage_m3`` caps it (zero means no storage
  constraint) and ``daily_handling_m3`` caps the handled water volume (``None`` means uncapped).
- The barge fleet is constrained by ``DriverPolicy.regular_minutes`` exactly like the truck fleet.
- Phase I currently assumes a same-day barge cycle. A multi-day voyage is not yet
  represented; the Quatsino Sound -> Ladysmith regression case and the proposed
  model are tracked at `UBC-FRESH/fhops#196`_ and
  ``notes/multiday_marine_cycles.md``.
- Phase II schedules the road drayage loads and the barge cycles separately. The returned
  ``pickup_truck_depart``/``delivery_truck_arrive`` columns are the synchronization handoff; the
  first release reports them rather than hard-linking the two MIPs.
- A truck cannot be at both the origin and destination port in one road movement. A missing
  cross-stage empty leg is represented by a full-day deadhead so an unsupported transfer is
  infeasible rather than invented as a short road trip.
- Tide, weather, naval architecture, customs, and a full coastal network remain out of scope.

.. _UBC-FRESH/fhops#196: https://github.com/UBC-FRESH/fhops/issues/196

Validate a scenario with the normal command:

.. code-block:: bash

   fhops validate examples/hauling/scenario.yaml

The output reports the hauling dimensions in addition to the core scenario counts.

Entity rules
------------

The contract validates identifiers, units, ranges, and cross references. The important rules are:

- Every ``block_id`` in supply, haul arcs, contractor eligibility, and compatibility must exist in
  the scenario's blocks.
- Every ``loader_id`` must be a machine in the scenario. A pickup loader points at a block, a
  delivery loader points at a sort yard, and a port loader points at a port.
- Every truck references a known contractor and truck type. A truck type must be able to carry
  sorted or unsorted logs (or both). Barge-named truck types are rejected.
- A sort yard's total daily processing capacity must be at least its sorted and unsorted component
  capacities.
- Demand days are one-indexed **relative to the hauling horizon**, not the parent scenario. The
  hauling horizon must fit inside the parent ``num_days``.
- Supply, demand, haul arcs, and contractor-block pairs are unique. Marine routes are unique by
  block, yard, truck type, and barge type.
- A hauling section needs at least one truck, one depot, and one haul arc **or** one marine route.
- A marine route needs an origin and destination port, a matching water arc, an origin and
  destination port leg, an enabled barge of the water arc's type, and an enabled truck of the
  drayage type.

Contractor eligibility
----------------------

``contractor_blocks`` is optional. When the list is empty, every contractor may serve every block.
When it contains entries, it is an allowlist: only the listed contractor/block pairs are eligible.
This mirrors Ghotb's ``alpha_bo`` parameter.

Truck-type compatibility comes from the truck type's ``can_carry_sorted`` and
``can_carry_unsorted`` flags and from truck ownership. A contractor can only dispatch trucks it
owns. The optional ``compatibility`` list is reserved for later exceptions and is not required for
the first release.

Units and defaults
------------------

- Volumes: cubic metres (m³).
- Travel and service times: minutes.
- Costs: scenario currency; fixed cost is per dispatched truck per day, variable and overtime costs
  are per minute.
- ``planning_horizon_days`` defaults to 20 (four weeks); ``start_day`` defaults to 1.
- ``driver_policy.regular_minutes`` defaults to 510 (8.5 h); ``max_overtime_minutes`` defaults to
  150 (2.5 h). These match the thesis case.

Phase I solve
-------------

The Phase I model is a Python API in :mod:`fhops.hauling.flow`:

.. code-block:: python

   from fhops.scenario.io import load_scenario
   from fhops.hauling.flow import build_flow_problem, solve_flow, summarize_flow_result

   scenario = load_scenario("examples/hauling/scenario.yaml")
   problem = build_flow_problem(scenario)
   cost = solve_flow(problem)                      # Ghotb's Z1
   balanced = solve_flow(problem, objective="goal", weights=(1.0, 0.5))
   print(summarize_flow_result(balanced))
   print(balanced.flows.head())
   print(balanced.contractor_workload.head())

``solve_flow`` accepts ``objective="cost"``, ``"workload"``, or ``"goal"``. A goal solve with no
explicit ``goals`` runs a cost-only solve first, uses its objective as ``Goal1``, sets ``Goal2`` to
zero, and derives each contractor's preferred daily truckloads from that cost plan unless the
contract or the caller supplies them. The normalized goal objective is

``w1 * dev_cost / max(|Goal1|, 1) + w2 * dev_workload / max(sum(phi), 1)``.

The result payload carries:

- ``flows``: block/yard/sort/contractor/type/day volumes;
- ``truckloads``: sorted and unsorted load counts per block/yard/contractor/type/day;
- ``yard_inventory``: unsorted and water inventory, processed volume, and demand;
- ``block_inventory``: sorted and unsorted roadside inventory at the horizon end;
- ``contractor_workload``: daily truckloads, preferred level, and deviation;
- ``marine_flows`` and ``barge_trips``: water-leg volume, barge trips, terminal handling, and leg
  cost/time provenance;
- ``port_inventory``: opening, inbound, outbound, ending inventory, and handled volume per port/sort;
- ``marine_truckloads``: pickup and delivery drayage load counts for Phase II;
- objective values, goal deviations, solver provenance, and diagnostics.

Units and assumptions:

- ``cycle_minutes = 2 * HaulArc.travel_minutes + pickup service + delivery service``.
- Transport cost per started truckload is ``TruckType.variable_cost_per_minute * cycle_minutes``.
  The fixed truck cost belongs to Phase II, which decides whether to dispatch a truck or pay
  overtime.
- The fleet-capacity constraint uses ``DriverPolicy.regular_minutes``.
- A zero ``roadside_inventory_penalty_per_m3`` lets the model leave supply at the block for free.
  Set a positive penalty for a meaningful flow plan.
- Compatibility is enforced by omitting infeasible variables, not by a big-M.
- The workload deviation is linearised with two inequalities; goal deviations are non-negative
  continuous variables.

Phase II schedule
-----------------

The Phase II model turns the Phase I integer truckloads into a single-day truck and loader
schedule:

.. code-block:: python

   from fhops.hauling import (
       build_schedule_problem,
       solve_schedule,
       simulate_plan,
       validate_schedule,
   )

   flow_problem = build_flow_problem(scenario)
   flow_result = solve_flow(flow_problem)
   schedule_problem = build_schedule_problem(scenario, flow_result, day=1)
   result = solve_schedule(schedule_problem, time_limit=60)
   print(result.schedule.head())
   print(result.truck_summary.head())
   print(result.loader_summary.head())
   print(validate_schedule(schedule_problem, result.schedule))

The model assigns every truckload to exactly one compatible truck, routes each truck from the
central depot through its loads and back, assigns each pickup/delivery load to a loader at its
location, and orders the loads at each loader. Time is continuous. Regular minutes and overtime are
separate variables, so the objective charges:

``sum fixed_cost * used_truck + sum variable_cost * regular_minutes
+ sum overtime_cost * overtime_minutes``.

The result contains:

- ``schedule``: one row per load with the truck, contractor, type, pickup/delivery loaders,
  arrival, service start/finish, waiting, route order, and truck return/regular/overtime minutes;
- ``truck_summary``: used trucks, load counts, return time, regular/overtime minutes, and cost
  components;
- ``loader_summary``: loader kind/location, load count, busy minutes, first start, and last finish;
- ``barge_schedule``: one row per barge trip with the barge, port loaders, load/sail/unload/return
  times, waiting, synchronized pickup/delivery truck windows, and cost components;
- ``barge_summary``: trips, volume, sailing/load/unload/return minutes, and barge/handling cost;
- ``plan``: the truck routes and loader orders.

``simulate_plan`` recomputes the earliest schedule for the result's route and loader order by
fixed-point iteration, without using the MIP's time variables. ``validate_schedule`` checks
compatibility, synchronisation, loader overlap, route travel, and return-time consistency. Use both
as independent oracles.

The exact MIP is intended for small and medium daily instances. The real case in the thesis has 81
truckloads and 168 nodes; Phase III (P11.4) handles that scale with simulated annealing.

Phase III simulated annealing
-----------------------------

The exact scheduling MIP is the oracle for small days. For large days, use the SA solver:

.. code-block:: python

   from fhops.hauling import SAConfig, solve_sa, summarize_sa_result

   result = solve_sa(
       schedule_problem,
       SAConfig(
           initial_temperature=300,
           min_temperature_ratio=0.0005,
           cooling_rate=0.95,
           iterations_per_temperature=90,
           max_iterations=50_000,
           seed=42,
       ),
   )
   print(summarize_sa_result(result))
   print(result.schedule.head())

The solution is a permutation of truck routes. The decoder assigns each load to the fastest loader
at its location, derives pickup and delivery loader orders from projected arrival times (SPT), and
calls the same :func:`~fhops.hauling.schedule.simulate_plan` used by the Phase II oracle. The
neighbourhood operators are swap, reversion, and insertion; insertion may move a load to another
compatible truck. The acceptance rule is the usual Metropolis rule with geometric cooling.

``SAConfig`` defaults come from the thesis Taguchi calibration: ``T0=300``,
``T_min = 0.0005 * T0``, ``alpha=0.95``, and 90 moves per temperature. They are configurable. The
result carries the best schedule, truck/loader summaries, route plan, objective components,
iterations, accepted moves, runtime, seed, and a per-move history. An overtime violation above
``regular_minutes + max_overtime_minutes`` is soft-penalized in the SA cost; the exact MIP treats it
as hard.

For a small day, the SA solver should match the MIP objective. The example day-1 case currently
reaches the same 2992.50 objective with both methods. For a parameter sweep, run:

.. code-block:: bash

   python scripts/benchmark_hauling.py --solver both --day 1
   python scripts/benchmark_hauling.py --solver sa --calibrate --sa-iters 500      --out-dir tmp/hauling-calibration

CLI
---

The `fhops haul` commands are:

.. code-block:: bash

   fhops haul validate examples/hauling/scenario.yaml
   fhops haul plan examples/hauling/scenario.yaml --out-dir runs/haul-plan
   fhops haul schedule examples/hauling/scenario.yaml --out-dir runs/haul-day1      --flow-dir runs/haul-plan --day 1 --solver sa --sa-iters 5000
   fhops haul solve examples/hauling/scenario.yaml --out-dir runs/haul-solve      --day 1 --solver mip --time-limit 60
   fhops haul report runs/haul-solve

``plan`` solves Phase I and writes the flow artefacts. ``schedule`` solves Phase II/III for one day;
it reads an existing Phase I run with ``--flow-dir`` or solves Phase I in memory. ``solve`` runs both
and writes a merged summary. ``report`` renders a Markdown report from any run directory.

Stable artefacts
----------------

The writers in :mod:`fhops.hauling.reporting` use these names:

Phase I:

- ``haul_flows.csv``
- ``haul_truckloads.csv``
- ``haul_yard_inventory.csv``
- ``haul_block_inventory.csv``
- ``haul_contractor_workload.csv``
- ``haul_marine_flows.csv``
- ``haul_marine_truckloads.csv``
- ``haul_barge_trips.csv``
- ``haul_port_inventory.csv``
- ``haul_kpis.json``
- ``haul_summary.json``

Phase II/III:

- ``haul_schedule.csv``
- ``haul_truck_summary.csv``
- ``haul_loader_summary.csv``
- ``haul_barge_schedule.csv``
- ``haul_barge_summary.csv``
- ``haul_kpis.json``
- ``haul_summary.json``

The marine files are present but empty for road-only scenarios.

A combined solve writes both families and a merged ``haul_summary.json`` with phase ``I+II/III``.

Operational and tactical handoff
--------------------------------

The operational model does not carry product yields, and the tactical model uses a different
contract. The bridge is explicit:

.. code-block:: python

   from fhops.hauling import (
       scenario_from_operational_plan,
       scenario_from_tactical_plan,
   )

   # Operational assignments -> block/sort supply. Without sort_shares, equal shares are used
   # and a warning is recorded.
   bridged = scenario_from_operational_plan(
       scenario,
       assignments,
       sort_shares={"fir_saw": 0.5, "hemlock_pulp": 0.3, "mixed_unsorted": 0.2},
   )

   # Tactical production + facility demand -> hauling supply/demand.
   bridged = scenario_from_tactical_plan(
       scenario,
       tactical,
       period_id="p1",
       production=tactical_result["production"],
   )

The tactical bridge maps products to log sorts through ``LogSort.product_id`` (or a matching
``LogSort.id``), facilities to yards through ``SortYard.facility_id``, and spreads period demand
evenly over the hauling horizon. It records a warning when a product/facility has no link, when no
production table is supplied, or when the even split is used. It does not invent a missing haul arc;
the base scenario's arcs remain the travel-time source.

``residual_report`` returns supply, demand, and the residual per log sort before a solve. A positive
residual means demand exceeds supply.

Scale case
----------

``examples/hauling_scale/`` is a generated stress case: 13 blocks, 3 yards, 4 contractors, 60
trucks, 3 log sorts, block polygons, and about 90 truckloads/day. Regenerate it with:

.. code-block:: bash

   python scripts/generate_hauling_scale_case.py

It is deliberately larger than the CI slice in ``examples/hauling/``. The Phase I model may need a
time limit and return a feasible incumbent rather than a proven optimum; the SA scheduler is the
intended Phase II/III path at this size. The case allows 300 overtime minutes so a full day remains
feasible without turning the exercise into a fleet-sizing study.

Limitations
-----------

- The first cut is deterministic. Emissions, electric-truck charging, stochastic supply/demand,
  loader breakdowns, lunch breaks, driver changes, and contractor collaboration are out of scope.
- Phase II requires exactly one depot and a depot leg for every used block/yard and truck type. A
  missing leg is a named error, never an invented travel time.
- Phase II uses the same loaded travel time for the empty yard-to-block leg unless
  ``HaulArc.return_travel_minutes`` is supplied.
- The exact schedule MIP is for small/medium days. The SA solver is the large-case path.
- The SA decoder assigns each load to the fastest loader at its location. Multiple-loader
  balancing is left to the exact MIP; a future SA variant can add loader assignment moves.
- Marine drayage and barge cycles are scheduled by separate solvers. The barge scheduler reports the
  synchronized road windows, but the first release does not add them as hard time windows in the
  truck MIP. Tide, weather, naval architecture, customs, and a full coastal network are out of
  scope.
- A truck may not transfer from a destination-port delivery leg to an origin-block pickup leg
  without a modelled deadhead; a missing cross-stage leg is treated as a full-day deadhead so the
  unsupported transfer cannot appear as a short invented road trip.
- The operational bridge needs a sort split; equal shares are a visible default, not a real yield
  model. Supply a ``sort_shares`` mapping when the product split matters.
- The tactical bridge needs a tactical production table for supply and spreads period demand evenly
  across the hauling horizon. It does not create missing haul arcs.
- The confidential company case in the thesis is not redistributable. The repository example is
  synthetic; exact reproduction of the case's dollar values is not a project target.

See also
--------

- :doc:`../reference/hauling` for the API reference.
- :doc:`../howto/data_contract` for the core scenario bundle.
- :doc:`../howto/tactical_operational` for the product/facility layer that can supply hauling
  demand.
