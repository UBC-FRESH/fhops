Harvest System Sequencing How-to
================================

This guide demonstrates how to configure harvest system sequences, run the solvers, and interpret
the resulting KPI outputs. It assumes familiarity with the data contract (:doc:`data_contract`) and
the harvest system registry (:doc:`../reference/harvest_systems`).

Configuring Scenarios
---------------------

Each block can optionally specify ``harvest_system_id``. If omitted, the solver assumes no
sequencing obligations. You can rely on the default registry or embed custom systems inside the
scenario YAML under ``harvest_systems``.

Minimal snippet:

.. code-block:: yaml

   harvest_systems:
     ground_fb_skid:
       environment: ground-based
       jobs:
         - {name: felling, machine_role: feller-buncher, prerequisites: []}
         - {name: primary_transport, machine_role: grapple_skidder, prerequisites: [felling]}
         - {name: processing, machine_role: roadside_processor, prerequisites: [primary_transport]}
         - {name: loading, machine_role: loader, prerequisites: [processing]}
   blocks:
     - id: B1
       work_required: 16
       harvest_system_id: ground_fb_skid

Machines should specify roles that satisfy the system jobs. The synthetic generator helper
:func:`fhops.scenario.synthetic.generate_with_systems` can produce sample scenarios with the correct
role mix:

.. code-block:: python

   from fhops.scenario.synthetic import SyntheticScenarioSpec, generate_with_systems

   spec = SyntheticScenarioSpec(num_days=5, num_blocks=6, num_machines=8)
   scenario = generate_with_systems(spec)  # assigns systems round-robin

Running the Solvers
-------------------

MIP
^^^

.. code-block:: bash

   fhops solve-mip examples/med42/scenario.yaml --out tmp/med42_mip.csv --time-limit 600

If sequencing conflicts exist (e.g., machine roles missing), the solver will fail or leave blocks
unassigned.

Simulated Annealing
^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   fhops solve-heur examples/med42/scenario.yaml --out tmp/med42_sa.csv \
       --profile explore --show-operator-stats

Iterated Local Search and Tabu Search reuse the same registry metadata:

.. code-block:: bash

   fhops solve-ils examples/med42/scenario.yaml --out tmp/med42_ils.csv --profile explore --include-mip False
   fhops solve-tabu examples/med42/scenario.yaml --out tmp/med42_tabu.csv --profile explore --tabu-tenure 30

Inspection & KPIs
-----------------

Sequencing violations surface in CLI output and KPI dumps. After running a solver, use:

.. code-block:: bash

   fhops evaluate examples/med42/scenario.yaml tmp/med42_sa.csv

Key metrics:

* ``sequencing_violation_count`` – total violations.
* ``sequencing_violation_breakdown`` – machine/job specific counts.
* ``mobilisation_cost`` – useful for understanding trade-offs when switching systems.

Benchmarking with Sequencing
----------------------------

The benchmarking harness respects system sequences automatically. Generate comparison reports with:

.. code-block:: bash

   fhops bench suite --out-dir tmp/bench_systems --include-ils --include-tabu
   python scripts/render_benchmark_plots.py tmp/bench_systems/summary.csv --out-dir docs/_static/benchmarks

Combine the summary’s ``objective_gap_vs_best_heuristic`` column with the sequencing KPIs to see
which heuristic handles system constraints best.

Troubleshooting
---------------

* Ensure machine roles cover every job in the selected system; missing roles will cause infeasible
  schedules.
* Optional or parallel tasks headroom is currently limited—model them as separate jobs with explicit
  prerequisites. Future registry extensions may introduce richer structures (see roadmap notes).
* When extending the registry, update :doc:`../reference/harvest_systems` and regenerate any
  synthetic scenarios or documentation examples.
