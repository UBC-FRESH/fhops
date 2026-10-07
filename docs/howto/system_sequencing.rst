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
* **Production is capped by staged input, per upstream role.** Each role's output that is not yet
  consumed is staged separately (``initial_state`` ``staged_inventory`` per role). A downstream
  role consumes its output from the staged volume of **every** upstream role, so a role with
  several upstream roles (a join) cannot output more than the smallest of them has staged;
  machines of the same role in one slot draw from it in turn. The MILP keeps one staged inventory
  per upstream role (formulation E7, 1.0.1 audit #115); before, it pooled the upstream outputs of
  a join.
* **No role handles more wood than the block holds.** Each role's cumulative output on a block is
  capped by ``min(role_remaining, work_required)`` (``role_remaining`` from ``initial_state``,
  ``work_required`` by default), and no assignment outputs more than the block still has to
  deliver.
* **Head starts are staged volume.** ``role_headstart_shifts`` = ``β`` means the downstream role may
  work only when at least ``β × Σ`` (upstream machines' rates on the block, m³/shift) is staged at
  the start of the slot by every upstream role. When no upstream machine has a positive rate on
  the block, the role's own fleet rate is used. The buffer is waived once every upstream role has
  output its whole carried-in remaining volume before the slot (the pipeline is draining); an
  upstream role finishing the block in the same slot does not waive it (MILP ``upstream_done`` uses
  output up to the previous slot; heuristics and playback since 1.0.1, #116). Shift counts
  (``initial_state.role_shift_counts``) are informational.
* **Loaders need a truckload staged.** A loader may work only when the volume staged at the start of
  the slot covers ``loader_batch_volume_m3``, or the volume the block still has to deliver when
  that is smaller (``work_required`` minus the terminal output delivered before the slot), so the
  last partial truckload of a block can be loaded. The MILP linearises this rule exactly with a
  binary per block and slot, created only for slots in which the remaining volume can have fallen
  to one truckload.
* **Blocks without** ``harvest_system_id`` have no role obligations: any machine may work them and
  every machine's output counts towards ``work_required``.

Landing capacity is not a sequencing rule and is modelled differently by the solvers: the MILP
limits machine-shifts per landing and day to ``Landing.daily_capacity`` plus a slack priced by the
``landing_surplus`` weight (free at weight 0), while the heuristics count machines per landing in
each shift and charge 1000 per machine beyond ``daily_capacity`` when ``landing_surplus`` is 0
(otherwise the weighted surplus). Because
staged output moves on at the next shift, a multi-shift heuristic repair could put every role of a
block on its landing in the same shift; on days with more than one shift the heuristic repair
therefore only keeps or fills an assignment when the block's landing has room in that shift
(scenarios that weight ``landing_surplus`` at 0, the default). Machines the repair has not reached
yet in that shift count only through their locks, so repairing an already repaired plan leaves it
unchanged and the heuristic score equals a fresh evaluation of the exported plan (1.0.1, #131).
Single-shift days are unchanged.

Playback flags an assignment with ``sequencing_violation = "missing_prereq"`` when its planned
production exceeds the staged input or a head-start/truckload threshold is not met (volume
tolerance 1e-6 m³, which absorbs MILP solver feasibility noise). Rolling-horizon MILP runs store
the planned production in their locks, so stitched plans replay the MILP plan rather than the full
production rate (:doc:`rolling_horizon`).

Locks and the operational MILP
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A locked machine is always assigned to its block, but it does not have to produce: when its role
has nothing to process (a loader before a truckload is staged, a head-start role before its buffer)
the MILP keeps it idle (``assigned = 1``, ``production = 0``) instead of becoming infeasible. Only
unlocked assigned machines force the role's head-start/truckload checks. Playback still reports a
locked idle machine of a buffered role as ``missing_prereq`` (the lock places it there before the
buffer exists). Locks that contradict the model (a day outside the block window, a machine whose
role is not part of the block's harvest system) are rejected by scenario validation; if such a lock
reaches the MILP anyway (e.g. a hand-edited bundle) it is pinned to idle and listed in the solve
result's ``warnings``.

Running the Solvers
-------------------

MIP
^^^

.. code-block:: bash

   fhops solve-mip-operational examples/tiny7/scenario.yaml --out tmp/tiny7_mip.csv --time-limit 60

(``fhops solve-mip`` is a deprecated alias of this command since FHOPS 1.0.1. On med42 the MILP
needs long time limits or Gurobi; with HiGHS and a 600 s limit it typically stops at an incumbent
that assigns no machines.) If sequencing conflicts exist (e.g., machine roles missing), blocks stay unassigned. The
operational MILP (``fhops solve-mip-operational``) reports an ``outcome`` (``optimal``,
``feasible``, ``infeasible``, ``no_solution``, ``error``) and never raises for infeasible models or
time limits without an incumbent; see :doc:`mip_warm_starts` for the result fields.

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
