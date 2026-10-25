"""Optional FHOPS web service and artefact discovery.

The FastAPI application lives in :mod:`fhops.web.app` and is imported only when the
``fhops[web]`` extra is installed. Run discovery and manifest handling in
:mod:`fhops.web.discovery` have no web-framework dependency.
"""

from .discovery import (
    DOMAINS,
    RUN_MANIFEST_SCHEMA_VERSION,
    RunRecord,
    build_run_manifest,
    classify_run,
    discover_runs,
    load_run_manifest,
    write_run_manifest,
)

__all__ = [
    "DOMAINS",
    "RUN_MANIFEST_SCHEMA_VERSION",
    "RunRecord",
    "build_run_manifest",
    "classify_run",
    "discover_runs",
    "load_run_manifest",
    "write_run_manifest",
]
