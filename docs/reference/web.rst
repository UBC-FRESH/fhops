``fhops.web`` Package
=====================

Run discovery and the ``run.json`` manifest are implemented in
:mod:`fhops.web.discovery`. The FastAPI application factory lives in :mod:`fhops.web.app` and is
imported only when the optional ``fhops[web]`` extra is installed.

.. automodule:: fhops.web.discovery
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:

.. automodule:: fhops.web.app
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:

Key objects
-----------

- :class:`fhops.web.discovery.RunRecord` – one discovered run directory.
- :func:`fhops.web.discovery.discover_runs` – scan roots and classify operational, hauling, and
  tactical runs.
- :func:`fhops.web.discovery.build_run_manifest` / :func:`fhops.web.discovery.write_run_manifest` –
  build or write ``run.json``.
- :class:`fhops.web.app.ServiceConfig` – roots, bind, proxy prefix, and remote-bind opt-in.
- :func:`fhops.web.app.create_app` – FastAPI factory.
- :func:`fhops.web.app.validate_bind` – loopback/remote-bind guard.
- :func:`fhops.web.skins.load_skins` / :func:`fhops.web.skins.validate_skin` – skin registry.
- :class:`fhops.web.skins.SkinManifest` – validated domain skin.
- :func:`fhops.web.mapdata.load_block_geometry` – resolve block geometry from ``--geometry``, the
  scenario, or a run-local GeoJSON.
- :func:`fhops.web.mapdata.layer_registry` – available/unavailable map layers with reasons.
- :func:`fhops.web.mapdata.time_payload` – day/shift/period control values.
- :func:`fhops.web.mapdata.map_payload` – GeoJSON FeatureCollection for the requested layers.

CLI
---

.. code-block:: bash

   fhops web --runs runs/
   fhops web manifest runs/run-a --status optimal
   fhops web discover runs/
