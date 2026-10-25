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
P12.2 adds the read-only artefact API for all three domains, the navigable SPA shell, and the skin
loader. P12.3 adds the map, layer tree, and day/shift/period control (MapLibre with an SVG
fallback). P12.4 adds the domain panels: operational shift Gantt, hauling truck/loader Gantt and
charts, tactical period Gantt, KPI cards, report builder, and run comparison. Live SSE and editing
land in P12.5–P12.6.

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
   fhops web --runs runs/ --geometry examples/hauling/blocks.geojson --geometry-crs EPSG:3005

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

The read-only API provides:

- ``GET /api/health``
- ``GET /api/runs`` and ``GET /api/runs/{run_id}``
- ``GET /api/runs/{run_id}/summary`` and ``/kpis``
- ``GET /api/runs/{run_id}/assignments`` and ``/playback``
- ``GET /api/runs/{run_id}/hauling/{flows,truckloads,schedule,yard-inventory,contractor-workload,trucks,loaders}``
- ``GET /api/runs/{run_id}/tactical/{harvest,production,flows,inventory,purchases,roads,silviculture,fleet}``
- ``GET /api/runs/{run_id}/reports`` and ``/reports/{path}``
- ``GET /api/skins`` and ``/api/skins/{id}``
- ``GET /`` and ``/static/*``

Table endpoints return ``columns``, ``rows``, ``total``, and ``returned``. Filters are optional
query parameters; an unknown filter column is a 400, and a missing artefact is a 404 naming the
logical file. The SPA shell selects a skin and run, shows the skin's tabs, and renders the selected
domain table/KPI/report from the API. The map, full Gantt, comparison, live SSE, and editing land in
P12.3–P12.6.

Map and layers
--------------

The map panel reads:

- ``GET /api/runs/{id}/time`` – the domain's control values: days plus shifts for operational,
  days for hauling, periods for tactical.
- ``GET /api/runs/{id}/layers`` – every known layer with an ``available`` flag and a reason when it
  is not drawable.
- ``GET /api/runs/{id}/map?day=&period=&shift=&layers=`` – a GeoJSON FeatureCollection.

Block geometry is resolved in this order:

1. ``--geometry path/to/blocks.geojson`` passed to ``fhops web``;
2. the scenario's ``geo_block_path``, read through the run manifest's ``scenario`` path;
3. a ``blocks.geojson`` file inside the run directory.

MapLibre expects WGS84 longitude/latitude. The service transforms projected coordinates with
``pyproj`` before returning the FeatureCollection. The source CRS comes from ``--geometry-crs``, the
scenario ``geo_crs``, the GeoJSON ``crs`` member, or EPSG:4326 in that order. Invalid or
out-of-range coordinates are a named 400, not a MapLibre crash.

The first cut draws block geometry, operational treatments/machines, hauling block flow volumes, and
tactical harvested areas. Roads, mills/sort yards, haul routes, and tactical facilities are reported
as unavailable until a geometry source exists; the service never invents coordinates. The layer tree
shows those reasons.

The renderer is MapLibre GL JS with an OpenStreetMap raster basemap; SVG is the fallback and is
switchable in the panel. The time control is day/shift for operational and hauling and period for
tactical.

Domain panels
--------------

- **Operational:** the Schedule tab renders a machine × day/shift Gantt from the assignment CSV,
  followed by the assignment table. KPIs and Reports read the run's own payloads.
- **Hauling:** the Haul tab shows the run provenance, then a dataset chooser for flows, truckloads,
  the truck/loader schedule (Gantt by truck/minute), yard inventory (grouped bars), contractor
  workload (grouped bars), trucks, and loaders.
- **Tactical:** the Tactical tab shows a period Gantt of harvest decisions plus production, flows,
  inventory, purchases, roads, silviculture, and fleet tables.
- **KPIs:** numeric KPI cards plus the full key/value payload and the run summary.
- **Reports:** the file tree plus a report builder over the current domain's artefact tables.
  Every table has a client-side CSV download.
- **Compare:** two run selectors, summaries, and a KPI table with `B − A` deltas.

Skins
-----
Domain panels
--------------

- **Operational:** the Schedule tab renders a machine × day/shift Gantt from the assignment CSV,
  followed by the assignment table. KPIs and Reports read the run's own payloads.
- **Hauling:** the Haul tab shows the run provenance, then a dataset chooser for flows, truckloads,
  the truck/loader schedule (Gantt by truck/minute), yard inventory (grouped bars), contractor
  workload (grouped bars), trucks, and loaders.
- **Tactical:** the Tactical tab shows a period Gantt of harvest decisions plus production, flows,
  inventory, purchases, roads, silviculture, and fleet tables.
- **KPIs:** numeric KPI cards plus the full key/value payload and the run summary.
- **Reports:** the file tree plus a report builder over the current domain's artefact tables.
  Every table has a client-side CSV download.
- **Compare:** two run selectors, summaries, and a KPI table with `B − A` deltas.

Skins
-----

Skins are JSON manifests in ``src/fhops/web/skins/``. The loader validates every panel, layer, and
action against a registry; an unknown name is refused with the name. ``read_only`` removes every
mutating action. The shipped skins are:

- ``operational-planner`` – schedule, objectives/locks, run control, KPIs, reports.
- ``hauling-planner`` – hauling flows/schedule/inventory, driver policy, run control, KPIs.
- ``tactical-planner`` – tactical decisions/flows/inventory, overlays, run control, KPIs.
- ``reviewer`` – read-only access to schedule/haul/tactical, KPIs, reports, and comparison.

Security and limits
-------------------

- Loopback only by default; ``--allow-remote`` is an explicit operator decision.
- No authentication in this release.
- Run roots are allowlisted; the service does not serve arbitrary paths.
- The service is a reader. It does not import the optimizer into the request process.
- The assistant is not part of P12.1; it lands opt-in in P12.6.
