Hydrology Quickstart — FEMIC to WS4 to FHOPS
=============================================

This page gives one pinned, synthetic path through the three repositories. It
demonstrates the contracts and fail-closed behavior. It is **not** a real
watershed analysis, flood map, or regulatory result.

Version Matrix
--------------

The quickstart was tested from source against:

.. list-table::
   :header-rows: 1

   * - Package
     - Version
     - Source
   * - FEMIC
     - ``0.2.0a1``
     - ``<path-to-femic>``
   * - WS4
     - ``0.2.0``
     - ``<path-to-ws4>``
   * - FHOPS
     - ``1.1.0``
     - ``<path-to-fhops>``

These are source versions, not a claim that every published wheel is
interchangeable. The generated ``quickstart.json`` records the versions found in
the environment.

Install the three packages in one environment, for example:

.. code-block:: bash

   python -m venv .venv
   . .venv/bin/activate
   python -m pip install -e "<path-to-femic>"
   python -m pip install -e "<path-to-ws4>"
   python -m pip install -e "<path-to-fhops>"

Build the Synthetic Workspace
-----------------------------

From the FHOPS checkout:

.. code-block:: bash

   python scripts/build_hydrology_quickstart.py --out build/hydrology_quickstart

The script creates:

.. code-block:: text

   build/hydrology_quickstart/
     bundle/                         shared FEMIC response bundle
     ws4/dataset/                    compiled WS4 dataset
     ws4/crosswalk.csv               explicit WS4 support mapping
     ws4/crosswalk.meta.json         reviewed crosswalk metadata
     ws4/schedule.csv                WS4 schedule
     ws4/exposure.json               schedule-bound WS4 exposure
     fhops/scenario/                 FHOPS scenario copy
     fhops/crosswalk.csv             explicit FHOPS support mapping
     fhops/screen_schedule.csv       FHOPS screen schedule
     fhops/hazard_schedule.csv       FHOPS hazard-check schedule
     fhops/exposure.json             schedule-bound FHOPS exposure
     fhops/hazard.json               operational hazard windows
     fhops/assets.json               road/culvert assets
     quickstart.json                 versions and expected counts

WS4 Landscape Screening
-----------------------

Register the shared bundle, preflight the mapping, and screen the schedule:

.. code-block:: bash

   ws4 hydrology register \
     --dataset build/hydrology_quickstart/ws4/dataset \
     --bundle build/hydrology_quickstart/bundle

   ws4 hydrology preflight \
     --dataset build/hydrology_quickstart/ws4/dataset \
     --crosswalk build/hydrology_quickstart/ws4/crosswalk.csv \
     --metadata build/hydrology_quickstart/ws4/crosswalk.meta.json \
     --policy require_reviewed \
     --json

   ws4 hydrology map \
     --dataset build/hydrology_quickstart/ws4/dataset \
     --crosswalk build/hydrology_quickstart/ws4/crosswalk.csv \
     --metadata build/hydrology_quickstart/ws4/crosswalk.meta.json \
     --out build/hydrology_quickstart/ws4/mapping

   ws4 hydrology screen \
     --dataset build/hydrology_quickstart/ws4/dataset \
     --mapping build/hydrology_quickstart/ws4/mapping \
     --schedule build/hydrology_quickstart/ws4/schedule.csv \
     --exposure build/hydrology_quickstart/ws4/exposure.json \
     --readiness-policy require_reviewed \
     --out build/hydrology_quickstart/ws4/screen

Expected: ``preflight`` reports ``screening_ready: true``; the screen manifest
reports 2 receptor rows and 0 refusals.

FHOPS Consumer and Operational Check
------------------------------------

Register the bundle in the copied scenario, map support, screen the schedule, and
run the hazard check:

.. code-block:: bash

   fhops scenario hydrology register \
     build/hydrology_quickstart/fhops/scenario/scenario.yaml \
     build/hydrology_quickstart/bundle

   fhops scenario hydrology map \
     build/hydrology_quickstart/fhops/scenario/scenario.yaml \
     build/hydrology_quickstart/bundle \
     build/hydrology_quickstart/fhops/crosswalk.csv \
     --metadata build/hydrology_quickstart/fhops/crosswalk.meta.json \
     --out build/hydrology_quickstart/fhops/mapping

   fhops scenario hydrology screen \
     build/hydrology_quickstart/fhops/scenario/scenario.yaml \
     build/hydrology_quickstart/bundle \
     build/hydrology_quickstart/fhops/mapping \
     build/hydrology_quickstart/fhops/screen_schedule.csv \
     build/hydrology_quickstart/fhops/exposure.json \
     --out build/hydrology_quickstart/fhops/screen

   fhops scenario hydrology constraint-check \
     build/hydrology_quickstart/fhops/scenario/scenario.yaml \
     build/hydrology_quickstart/fhops/mapping \
     build/hydrology_quickstart/fhops/hazard_schedule.csv \
     build/hydrology_quickstart/fhops/hazard.json \
     --assets build/hydrology_quickstart/fhops/assets.json

Expected:

- FHOPS screen: 2 rows, 0 refusals.
- Constraint check: 3 events — one watch, one warning, one closure.
- The constraint check exits 1 by default because of closure activity.
- Re-run with ``--no-fail-on-closure`` to write outputs and exit 0.

What This Demonstrates
----------------------

- A producer bundle can be consumed by both WS4 and FHOPS.
- WS4 maps supports through an explicit reviewed crosswalk and screens a schedule.
- FHOPS registers the same bundle, maps support, screens a schedule, and checks
  operational exposure against fixed hazard windows and assets.
- Missing or unreviewed evidence refuses.

What This Does Not Prove
------------------------

- It is not a real watershed, gauge record, receptor inventory, or flood map.
- It does not include a current gauge series, DEM vertical audit, culvert field
  inventory, or hydrologist review.
- FHOPS does not optimize watershed flood response. The constraint check is an
  operational exposure control against a fixed hazard.
- The WS4 landscape path is a screening consumer, not a regulatory determination.

Troubleshooting
---------------

.. list-table::
   :header-rows: 1

   * - Symptom
     - Cause
     - Fix
   * - ``screening_ready: false``
     - Missing/reviewed crosswalk or readiness evidence
     - Use the generated reviewed metadata and the ready bundle.
   * - ``schedule hash`` mismatch
     - Exposure belongs to a different schedule
     - Regenerate exposure for the exact assignments CSV.
   * - ``unmapped`` support
     - Crosswalk is incomplete
     - Regenerate the workspace or add the missing support row.
   * - ``closure-window`` failure
     - Scheduled activity in a closure window
     - Move the activity or explicitly use ``--no-fail-on-closure`` for a report.
   * - ``not pinned``
     - Bundle was not registered in the scenario or dataset
     - Run the registration step for that consumer.

Further Reference
-----------------

- :doc:`../reference/hydrology_contract_index`

- :doc:`../reference/femic_hydrology`
- FEMIC hydrology guides in the FEMIC repository.
- WS4 ``docs/reference/femic-hydrology.rst``.
