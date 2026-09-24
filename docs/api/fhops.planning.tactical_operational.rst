``fhops.planning.tactical_operational`` Package
===============================================

Tactical–operational planning contracts, period templates, scenario overlays, reporting, scale
benchmarks, and tactical→operational handoff helpers introduced in Phase 6.

Typical usage:

.. code-block:: python

   from fhops.planning.tactical_operational import load_tactical_operational_scenario
   from fhops.model.milp.tactical_operational import (
       build_tactical_operational_bundle,
       solve_tactical_operational_milp,
   )

   scenario = load_tactical_operational_scenario(
       "tests/fixtures/tactical_operational/topm-mini/specification.yaml"
   )
   bundle = build_tactical_operational_bundle(scenario)
   result = solve_tactical_operational_milp(bundle)
   print(result["objective"], result["objective_components"])

.. automodule:: fhops.planning.tactical_operational
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: fhops.planning.tactical_operational.models
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:

.. automodule:: fhops.planning.tactical_operational.io
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:

.. automodule:: fhops.planning.tactical_operational.time
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:

.. automodule:: fhops.planning.tactical_operational.scenario
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:

.. automodule:: fhops.planning.tactical_operational.integration
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:

.. automodule:: fhops.planning.tactical_operational.scale
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:
