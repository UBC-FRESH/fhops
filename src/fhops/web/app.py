"""FastAPI application factory for the optional FHOPS web service.

This module imports FastAPI and is only imported when the ``fhops[web]`` extra is installed. The
core CLI imports :mod:`fhops.cli.web` lazily, so a core install never needs FastAPI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import fhops
from fhops.web.discovery import RunRecord, discover_runs

__all__ = ["ServiceConfig", "create_app", "is_loopback", "run_server", "validate_bind"]

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@dataclass(slots=True)
class ServiceConfig:
    """Web service configuration.

    Attributes
    ----------
    roots:
        Directories scanned for run artefacts.
    host / port:
        Bind address. Loopback is the default; a non-loopback host needs ``allow_remote``.
    root_path:
        Optional proxy prefix (for example a notebook proxy path).
    allow_remote:
        Explicit opt-in for a non-loopback bind.
    title:
        Page/service title.
    """

    roots: list[Path] = field(default_factory=lambda: [Path.cwd()])
    host: str = "127.0.0.1"
    port: int = 8765
    root_path: str = ""
    allow_remote: bool = False
    title: str = "FHOPS Web"


def is_loopback(host: str) -> bool:
    """Return whether a host string is a loopback address."""
    normalised = host.strip().lower()
    return normalised in {"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"}


def validate_bind(host: str, *, allow_remote: bool) -> None:
    """Refuse a non-loopback bind unless explicitly allowed.

    Raises
    ------
    ValueError
        When ``host`` is not loopback and ``allow_remote`` is false.
    """
    if not is_loopback(host) and not allow_remote:
        raise ValueError(
            f"Refusing non-loopback bind {host!r} without --allow-remote. "
            "The service has no authentication in this release."
        )


def create_app(config: ServiceConfig) -> FastAPI:
    """Create the FastAPI application.

    Parameters
    ----------
    config:
        Service configuration.

    Returns
    -------
    fastapi.FastAPI
        Application with health, run discovery, run detail, and the static shell.
    """
    validate_bind(config.host, allow_remote=config.allow_remote)
    app = FastAPI(title=config.title, version=fhops.__version__)
    roots = [root.expanduser().resolve() for root in config.roots]

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "version": fhops.__version__,
            "roots": [str(root) for root in roots],
            "domain_count": 3,
        }

    @app.get("/api/runs")
    def runs() -> list[dict[str, object]]:
        return [record.to_dict() for record in discover_runs(roots)]

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, object]:
        record = _find_run(roots, run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Unknown run_id={run_id}")
        return record.to_dict()

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        index_path = _STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=500, detail="Static shell is missing")
        return FileResponse(index_path)

    return app


def _find_run(roots: list[Path], run_id: str) -> RunRecord | None:
    for record in discover_runs(roots):
        if record.run_id == run_id:
            return record
    return None


def run_server(config: ServiceConfig) -> None:
    """Run the service with uvicorn.

    Parameters
    ----------
    config:
        Service configuration.

    Raises
    ------
    ValueError
        When the bind is refused or uvicorn is unavailable.
    """
    validate_bind(config.host, allow_remote=config.allow_remote)
    try:
        import uvicorn
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "The web service needs the optional dependencies. Install with: pip install 'fhops[web]'"
        ) from exc
    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port, root_path=config.root_path)
