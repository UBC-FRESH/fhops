Tactical–Operational Scenario Contract
======================================

Phase 6 adds a TOPM-inspired aggregate planning layer beside the existing day/shift operational
scheduler. The tactical–operational contract is intentionally separate from schema ``1.0.0`` so
current operational scenario bundles remain unchanged.

Use the tactical contract for 1–5 year plans that need:

- planning periods (four-week periods, months, seasons, or custom tables);
- block × harvest-system × period alternatives;
- partial, semi-continuous, or whole-block harvest quantities;
- product-specific yields;
- facilities, demand envelopes, transport arcs, and opening inventories;
- outside purchases and discounted economics; and
- later road, silviculture, and fleet-investment modules.

Loading and validation
----------------------

The Python loader accepts either inline YAML sections or a ``data:`` section that points each
long-form table at a CSV file:

.. code-block:: python

   from fhops.planning import load_tactical_operational_scenario

   scenario = load_tactical_operational_scenario(
       "tests/fixtures/tactical_operational/topm-mini/specification.yaml"
   )
   print(scenario.dimension_summary())

The CLI validates the same contract and reports model dimensions before any solver model is built:

.. code-block:: bash

   fhops validate tactical-operational tests/fixtures/tactical_operational/topm-mini/specification.yaml

The legacy operational form remains supported:

.. code-block:: bash

   fhops validate examples/tiny7/scenario.yaml

Period templates
----------------

:mod:`fhops.planning.tactical_operational.time` provides two starter templates:

- ``four_week_periods(year)`` — up to thirteen 28-day periods with optional effective annual
  discounting;
- ``seasonal_periods(year)`` — winter/spring/summer/fall periods with season tags.

Both produce validated :class:`~fhops.planning.tactical_operational.models.PlanningPeriod` objects.
Custom period tables can define explicit ``parent_period_id`` values for roll-up reporting.

Core MILP formulation
---------------------

The Phase 6 core model chooses a harvest area ``H[o] >= 0`` and activation ``Z[o] ∈ {0,1}`` for
each eligible block × system × period option ``o``. Product volumes are derived from area using
unit-specific yields:

.. math::

   V[o,p] = Y[b(o),p] H[o]

Semi-continuous mode enforces option-specific minimum and maximum active areas without arbitrary
big-M constants:

.. math::

   L_o Z_o \le H_o \le U_o Z_o

Continuous mode drops the lower bound; whole-block mode uses
``H_o = operable_area[b(o)] Z_o``. Block area, option productivity, fleet capacity, and
facility-demand targets complete the harvest core.

Product flows, purchases, consumption, and facility inventories are coupled to that harvest core.
For transport arc ``a``, external supply ``u``, facility/product/period ``(m,p,t)``, and previous
period ``t-1``:

.. math::

   \sum_{a \in out(b,p,t)} F_a \le \sum_{o:b(o)=b,t(o)=t} V[o,p]

.. math::

   I[m,p,t] = I[m,p,t-1] + \sum_{a \in in(m,p,t)} F_a + P_u - C[m,p,t]

Consumption is bounded by the facility demand envelope (or fixed at the target when
``--demand-basis target``). Transport arc capacities and external purchase bounds apply directly.
The default objective is discounted harvest + transport + purchase cost:

.. math::

   \min \sum_o d_{t(o)} (F_o Z_o + c_o Y^{total}_{b(o)} H_o)
   + \sum_a d_{t(a)} c_a F_a
   + \sum_u d_{t(u)} c_u P_u

Two value-oriented profiles are also available when demand rows carry ``value_per_m3``:
``max_discounted_profit`` maximizes delivered product value minus cost, and ``max_npv`` adds the
final-period value of declared terminal inventory. Override the scenario value with
``--objective-profile``.

Optional infrastructure modules
-------------------------------

The contract now includes optional long-form tables for:

- road projects, dependencies, and block access (``roads``, ``road_dependencies``,
  ``block_road_access``);
- silviculture follow-up transitions by block/system (``silviculture_transitions``); and
- fleet acquisition options with economic-life capacity (``fleet_options``).

These modules are disabled by default so the harvest/product-flow core remains reproducible.
Enable them independently from the CLI:

.. code-block:: bash

   fhops plan tactical-operational \
     tests/fixtures/tactical_operational/topm-mini/specification.yaml \
     --enable-roads \
     --out-roads-csv tmp/topm-mini-roads.csv

Road activation uses build/available binaries, cumulative timing, prerequisite links, access gates,
and active-road capacity. Silviculture transitions schedule required follow-up area in eligible
periods and add discounted per-hectare costs. Fleet acquisition variables add capacity during their
economic life and charge the purchase-period discounted cost.

The code mapping is intentionally direct:

- ``area`` / ``harvest_active``: ``fhops.model.milp.tactical_operational.model.area`` and
  ``model.harvest_active``.
- Product conversion: ``model.product_conversion``.
- Area/productivity/fleet limits: ``model.block_area``, ``model.productivity_cap``, and
  ``model.fleet_capacity``.
- Flow supply and arc capacity: ``model.flow_supply`` and ``model.arc_capacity``.
- Purchases, consumption, and inventory: ``model.purchase_lower``/``model.purchase_upper``,
  ``model.consumption_*``, and ``model.inventory_balance``.
- Roads: ``model.road_build``, ``model.road_available``, ``model.road_access``, and
  ``model.road_capacity``.
- Silviculture: ``model.silviculture_area`` and ``model.silviculture_fulfillment``.
- Fleet investment: ``model.fleet_units`` and the capacity augmentation inside
  ``model.fleet_capacity``.
- Objective assembly: ``model.objective``.
- Bundle replay: :func:`fhops.model.milp.tactical_operational.tactical_bundle_to_dict` and
  :func:`~fhops.model.milp.tactical_operational.tactical_bundle_from_dict`.

Solve the fixture from the CLI:

.. code-block:: bash

   fhops plan tactical-operational \
     tests/fixtures/tactical_operational/topm-mini/specification.yaml \
     --harvest-mode semi_continuous \
     --demand-basis target \
     --solver highs \
     --out-json tmp/topm-mini.json \
     --out-harvest-csv tmp/topm-mini-harvest.csv \
     --out-production-csv tmp/topm-mini-production.csv

Scenario overlays, diffs, and batch reports
-------------------------------------------

Phase 6 scenarios support sparse overlays so sensitivity cases can inherit a base contract without
copying every table. Overlay rows are matched by stable identifiers (for example ``block_id``,
``option_id``, ``arc_id``, or composite facility/product/period keys). An overlay can update nested
fields, append rows, and remove rows through ``_remove``.

.. code-block:: yaml

   overlay_id: lower-sawlog-demand
   description: Reduce Y1-P1 sawlog target from 780 to 700 m3.
   facility_demand:
     - facility_id: mill_saw
       product_id: sawlog
       period_id: Y1-P1
       target_m3: 700.0

Apply and inspect the overlay:

.. code-block:: bash

   fhops scenario overlay base.yaml lower-demand.yaml --out scenario-lower.yaml
   fhops scenario diff base.yaml scenario-lower.yaml --out tmp/scenario-diff.csv

A batch manifest can solve base and overlaid cases in one command:

.. code-block:: yaml

   cases:
     - case_id: base
       scenario: base.yaml
     - case_id: lower-demand
       scenario: base.yaml
       overlay: lower-demand.yaml
       enable_roads: true

.. code-block:: bash

   fhops scenario batch batch.yaml --out-dir tmp/tactical-batch
   fhops report tactical tmp/tactical-batch/base/result.json --out-dir tmp/tactical-report

Each batch case writes normalized decision tables and a Markdown objective summary; the batch root
contains ``comparison.csv`` and ``comparison.md``.

Tactical-to-operational handoff
-------------------------------

Use :mod:`fhops.planning.tactical_operational.integration` to convert a tactical solve into an
operational business window. The handoff contract is explicit:

- selected harvest decisions become :class:`TacticalCommitment` records;
- a rolling state tracks remaining block area/product volume, facility inventory, active roads,
  fleet units, and cumulative objective components;
- ``compile_business_window_scenario`` filters an operational scenario to committed blocks, maps
  tactical block IDs to operational IDs, assigns the selected harvest system, and clamps the window;
- ``write_operational_scenario_bundle`` emits a loadable YAML/CSV operational bundle; and
- ``apply_operational_realization`` rolls realized production back into aggregate state.

CLI example using `topm-mini` commitments against the operational tiny7 bundle:

.. code-block:: bash

   fhops plan tactical-operational \
     tests/fixtures/tactical_operational/topm-mini/specification.yaml \
     --out-json tmp/topm-mini-result.json

   fhops plan compile-tactical \
     tmp/topm-mini-result.json \
     examples/tiny7/scenario.yaml \
     --block-map B1=B01 \
     --block-map B2=B02 \
     --horizon-days 7 \
     --out-dir tmp/topm-mini-operational

The output directory contains a normal operational ``scenario.yaml`` + CSV bundle that can be
validated and solved with the existing FHOPS commands.

`topm-mini` acceptance fixture
------------------------------

``tests/fixtures/tactical_operational/topm-mini/specification.yaml`` is the copyright-safe
executable specification for the expansion. It contains hand-calculated checks for:

- continuous vs. semi-continuous vs. whole-block harvest activation;
- a two-option economic dispatch case;
- product-specific yield conversion; and
- facility inventory balances.

See ``notes/topm_mini_specification.md`` for the current expected values and implementation notes.
