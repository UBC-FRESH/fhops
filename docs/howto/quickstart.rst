Quickstart
==========

The quickest way to explore FHOPS is with the bundled ``examples/minitoy`` scenario.

.. code-block:: bash

   python -m venv .venv
   source .venv/bin/activate
   pip install -e .[dev]
   fhops validate examples/minitoy/scenario.yaml
   fhops solve-mip examples/minitoy/scenario.yaml --out examples/minitoy/out/mip_solution.csv
   fhops evaluate examples/minitoy/scenario.yaml examples/minitoy/out/mip_solution.csv

What the commands do:

- ``fhops validate`` ensures CSV/YAML inputs satisfy the data contract.
- ``fhops solve-mip`` builds a Pyomo model and solves it with HiGHS.
- ``fhops evaluate`` replays the resulting schedule and reports KPIs.

For more examples and advanced options, see the CLI reference (:doc:`../reference/cli`).

Regression Fixture
------------------

For automated regression checks, the repository ships a deterministic scenario that
exercises mobilisation penalties, blackout calendars, and harvest-system sequencing:
``tests/fixtures/regression/regression.yaml``. The companion ``baseline.yaml`` file stores
expected KPI/objective values that the test suite asserts against. You can experiment
with it manually:

.. code-block:: bash

   fhops solve-mip tests/fixtures/regression/regression.yaml --out /tmp/regression_mip.csv
   fhops solve-heur tests/fixtures/regression/regression.yaml --out /tmp/regression_sa.csv
   fhops evaluate tests/fixtures/regression/regression.yaml /tmp/regression_sa.csv

Use these outputs to validate CLI changes or to understand how mobilisation costs and
sequencing metrics appear in the KPI report.
