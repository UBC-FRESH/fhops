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
