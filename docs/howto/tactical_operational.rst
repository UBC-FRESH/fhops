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
facility-demand targets complete the core. The initial objective is discounted harvest cost:

.. math::

   \min \sum_o d_{t(o)} (F_o Z_o + c_o Y^{total}_{b(o)} H_o)

The code mapping is intentionally direct:

- ``area`` / ``harvest_active``: ``fhops.model.milp.tactical_operational.model.area`` and
  ``model.harvest_active``.
- Product conversion: ``model.product_conversion``.
- Area/productivity/fleet/demand limits: ``model.block_area``, ``model.productivity_cap``,
  ``model.fleet_capacity``, and ``model.demand``.
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

`topm-mini` acceptance fixture
------------------------------

``tests/fixtures/tactical_operational/topm-mini/specification.yaml`` is the copyright-safe
executable specification for the expansion. It contains hand-calculated checks for:

- continuous vs. semi-continuous vs. whole-block harvest activation;
- a two-option economic dispatch case;
- product-specific yield conversion; and
- facility inventory balances.

See ``notes/topm_mini_specification.md`` for the current expected values and implementation notes.
