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

P11.1 ships the contract and validation. The Phase I/II models and the SA solver land in
P11.2-P11.4. Until then, ``fhops validate`` accepts a hauling section and reports its dimensions;
the hauling CLI arrives in P11.5.

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

Validate it with the normal command:

.. code-block:: bash

   fhops validate examples/hauling/scenario.yaml

The output reports the hauling dimensions in addition to the core scenario counts.

Entity rules
------------

The contract validates identifiers, units, ranges, and cross references. The important rules are:

- Every ``block_id`` in supply, haul arcs, contractor eligibility, and compatibility must exist in
  the scenario's blocks.
- Every ``loader_id`` must be a machine in the scenario. A pickup loader points at a block; a
  delivery loader points at a sort yard.
- Every truck references a known contractor and truck type. A truck type must be able to carry
  sorted or unsorted logs (or both).
- A sort yard's total daily processing capacity must be at least its sorted and unsorted component
  capacities.
- Demand days are one-indexed **relative to the hauling horizon**, not the parent scenario. The
  hauling horizon must fit inside the parent ``num_days``.
- Supply, demand, haul arcs, and contractor-block pairs are unique.
- A hauling section needs at least one truck, one depot, and one haul arc.

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

Limitations
-----------

- The first cut is deterministic. Emissions, electric-truck charging, stochastic supply/demand,
  loader breakdowns, lunch breaks, driver changes, and contractor collaboration are out of scope.
- The contract does not build or solve a model yet. The Phase I/II models and the SA solver are
  tracked as P11.2-P11.4.
- The confidential company case in the thesis is not redistributable. The repository example is
  synthetic; exact reproduction of the case's dollar values is not a project target.

See also
--------

- :doc:`../reference/hauling` for the API reference.
- :doc:`../howto/data_contract` for the core scenario bundle.
- :doc:`../howto/tactical_operational` for the product/facility layer that can supply hauling
  demand.
