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

`topm-mini` acceptance fixture
------------------------------

``tests/fixtures/tactical_operational/topm-mini/specification.yaml`` is the copyright-safe
executable specification for the expansion. It contains hand-calculated checks for:

- continuous vs. semi-continuous vs. whole-block harvest activation;
- a two-option economic dispatch case;
- product-specific yield conversion; and
- facility inventory balances.

See ``notes/topm_mini_specification.md`` for the current expected values and implementation notes.
