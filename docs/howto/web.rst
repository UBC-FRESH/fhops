FHOPS Web UI
============

The web UI is an optional browser surface over the artefacts the FHOPS CLI writes. It follows the
WS4 web UI design: FastAPI + uvicorn behind an optional extra, a vanilla ES module SPA, MapLibre
with an SVG fallback, JSON skin manifests, SSE for live runs, and loopback-only defaults.

The same application covers three planning lenses:

- **Shift-level operational:** machine/crew day-shift Gantt, assignments, playback, production,
  utilisation, mobilisation, and sequencing.
- **Ghotb log hauling:** Phase I flows and truckloads, Phase II/III truck and loader schedules, yard
  inventory, contractor workload, and haul KPIs.
- **TOPM-style tactical–operational:** period harvest decisions, production, product flows,
  facility demand and inventory, roads, silviculture, and fleet.

P12.1 ships the service skeleton, run discovery, the `run.json` manifest, and a minimal run browser.
The domain panels, map/layer tree, Gantt, reports, comparison, live SSE, and editing land in
P12.2–P12.6.

Install and run
---------------

.. code-block:: bash

   pip install 'fhops[web]'
   fhops web --runs runs/
   # open http://127.0.0.1:8765/

The default bind is loopback. A non-loopback bind is refused unless ``--allow-remote`` is passed;
the service has no authentication in this release.

Useful options:

.. code-block:: bash

   fhops web --runs runs/ --runs examples/ --port 9000
   fhops web --runs runs/ --root-path /user/me/proxy/8765

``--root-path`` makes the SPA and API prefix-relative, so a notebook proxy can publish the service
under a subpath.

Run discovery
-------------

The service scans each configured root, including immediate child and grandchild directories. A
directory is a run when it contains ``run.json`` or a known artefact. The three domains are
classified from the files:

- operational: assignment CSVs, telemetry JSONL, playback day/shift summaries, rolling iterations;
- hauling: ``haul_flows.csv``, ``haul_truckloads.csv``, ``haul_schedule.csv``, ``haul_summary.json``,
  and the other ``haul_*`` files;
- tactical–operational: ``harvest_decisions.csv``, ``production.csv``, ``flows.csv``,
  ``purchases.csv``, ``inventory.csv``, ``roads.csv``, ``silviculture.csv``, ``fleet.csv``.

The API/CLI report unclassified or multi-domain runs with a warning rather than silently mixing
domains.

Run manifest
------------

``run.json`` is a small additive manifest:

.. code-block:: json

   {
     "schema_version": "1.0.0",
     "run_id": "run-a",
     "domain": "hauling",
     "run_type": "haul_solve",
     "status": "optimal",
     "command": "fhops haul solve examples/hauling/scenario.yaml --out ...",
     "scenario": "examples/hauling/scenario.yaml",
     "solver": "mip",
     "seed": 42,
     "files": {
       "haul_flows": "haul_flows.csv",
       "haul_schedule": "haul_schedule.csv",
       "haul_summary": "haul_summary.json"
     },
     "warnings": [],
     "generated_at": "2026-10-25T..."
   }

The `fhops haul plan`, `fhops haul schedule`, and `fhops haul solve` commands write one
automatically. It is optional for old runs. Write or refresh one from a run directory:

.. code-block:: bash

   fhops web manifest runs/haul-solve --status optimal
   fhops web discover runs/

The service reads ``run.json`` when present and otherwise classifies from files. When no manifest
status is available it reads the status from a summary artefact; it never invents one.

Service surface
---------------

P12.1 provides:

- ``GET /api/health``
- ``GET /api/runs``
- ``GET /api/runs/{run_id}``
- ``GET /`` and ``/static/*``

P12.2 adds the read-only artefact endpoints for the three domains, P12.3 the map/layers, P12.4 the
domain panels, P12.5 live runs/SSE, and P12.6 editing/skins.

Security and limits
-------------------

- Loopback only by default; ``--allow-remote`` is an explicit operator decision.
- No authentication in this release.
- Run roots are allowlisted; the service does not serve arbitrary paths.
- The service is a reader. It does not import the optimizer into the request process.
- The assistant is not part of P12.1; it lands opt-in in P12.6.
