Quickstart
==========

The quickest way to explore FHOPS is with the bundled ``examples/minitoy`` scenario.

Bootstrap Environment
---------------------

.. code-block:: bash

   python -m venv .venv
   source .venv/bin/activate
   pip install -e .[dev]

Workbench: ``examples/minitoy``
--------------------------------

.. code-block:: bash

   fhops validate examples/minitoy/scenario.yaml
   fhops solve-mip examples/minitoy/scenario.yaml --out examples/minitoy/out/mip_solution.csv
   fhops solve-heur examples/minitoy/scenario.yaml --out examples/minitoy/out/sa_solution.csv
   fhops evaluate examples/minitoy/scenario.yaml examples/minitoy/out/mip_solution.csv

What those commands do:

- ``fhops validate`` ensures CSV/YAML inputs satisfy the data contract.
- ``fhops solve-mip`` builds a Pyomo model and solves it with HiGHS. The resulting CSV
  lists the selected machine/block assignments.
- ``fhops solve-heur`` runs the simulated annealing heuristic.
- ``fhops evaluate`` replays a schedule CSV and reports KPIs such as production,
  mobilisation cost, and sequencing health (when harvest systems are configured).

Regression Fixture (Phase 1 Baseline)
-------------------------------------

The repository ships a deterministic scenario that exercises mobilisation penalties,
machine blackouts, and harvest-system sequencing:
``tests/fixtures/regression/regression.yaml``. The companion ``baseline.yaml`` file stores
expected KPI/objective values the automated tests assert against.

.. code-block:: bash

   fhops solve-mip tests/fixtures/regression/regression.yaml --out /tmp/regression_mip.csv
   fhops solve-heur tests/fixtures/regression/regression.yaml --out /tmp/regression_sa.csv
   fhops evaluate tests/fixtures/regression/regression.yaml /tmp/regression_sa.csv

The regression baseline encodes these expected values:

.. list-table::
   :header-rows: 1

   * - Metric
     - Expected
   * - SA objective (seed 123, 2 000 iters)
     - ``2.0``
   * - Total production
     - ``8.0``
   * - Mobilisation cost
     - ``6.0``
   * - Sequencing violations
     - ``0`` (clean schedule)

Compare the CLI output against the table to confirm your environment matches the regression
baseline. The fixture is also useful when iterating on mobilisation or sequencing logic.

For more examples and advanced options, see the CLI reference (:doc:`../reference/cli`) and
the data contract guide (:doc:`data_contract`).
