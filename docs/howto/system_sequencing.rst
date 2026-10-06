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
       work_required: 16   # m³ delivered by the terminal (loader) role
       harvest_system_id: ground_fb_skid

Machines should specify roles that satisfy the system jobs. The synthetic generator helper
:func:`fhops.scenario.synthetic.generate_with_systems` can produce sample scenarios with the correct
role mix:

.. code-block:: python

   from fhops.scenario.synthetic import SyntheticScenarioSpec, generate_with_systems

   spec = SyntheticScenarioSpec(num_days=5, num_blocks=6, num_machines=8)
   scenario = generate_with_systems(spec)  # assigns systems round-robin

Sequencing Semantics
--------------------

The operational MILP (:doc:`optimization_formulation`), the heuristics (SA/ILS/Tabu evaluation and
repair), and deterministic playback (:class:`fhops.evaluation.sequencing.SequencingTracker`) apply
the same rules, so a MILP plan replays with zero sequencing violations and playback delivers the
MILP's terminal production:

* **Staged output moves on at the next shift slot.** Volume a role outputs in slot ``(day,
  shift)`` is available to its downstream role from the next slot, i.e. the next shift of the same
  day in multi-shift scenarios (formulation E7: ``I_start(s) = I(prev(s))``). Slots follow the
  scenario's shift order (``timeline.shifts`` definition order), not the alphabetical order of
  shift labels.
* **Production is capped by staged input.** A downstream role cannot output more than the volume
  its upstream role(s) have staged (minimum over upstream roles); machines of the same role in one
  slot draw from it in turn.
* **No role handles more wood than the block holds.** Each role's cumulative output on a block is
  capped by ``work_required`` (or the carried-in ``initial_state`` ``role_remaining``).
* **Head starts are staged volume.** ``role_headstart_shifts`` = ``β`` means the downstream role may
  work only when at least ``β × Σ`` (upstream machines' rates on the block, m³/shift) is staged at
  the start of the slot. The buffer is waived once every upstream role has output its whole volume
  (the pipeline is draining). Shift counts (``initial_state.role_shift_counts``) are informational.
* **Loaders need a truckload staged.** A loader may work only when the volume staged at the start of
  the slot covers ``loader_batch_volume_m3``, or the remaining block volume when that is smaller
  (playback and heuristics use the volume still to deliver; the MILP uses the remaining volume at
  the start of its horizon, which is never less strict).
* **Blocks without** ``harvest_system_id`` have no role obligations: any machine may work them and
  every machine's output counts towards ``work_required``.

Playback flags an assignment with ``sequencing_violation = "missing_prereq"`` when its planned
production exceeds the staged input or a head-start/truckload threshold is not met (volume
tolerance 1e-6 m³, which absorbs MILP solver feasibility noise). Rolling-horizon MILP runs store
the planned production in their locks, so stitched plans replay the MILP plan rather than the full
production rate (:doc:`rolling_horizon`).

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

   fhops evaluate examples/med42/scenario.yaml --assignments tmp/med42_sa.csv

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
