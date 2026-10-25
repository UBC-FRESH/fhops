"""`fhops web` command group: serve the optional UI and manage run manifests."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from fhops.web.discovery import build_run_manifest, discover_runs

web_app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    invoke_without_command=True,
    help="Serve the optional FHOPS web UI or manage run manifests.",
)


@web_app.callback()
def web(
    ctx: typer.Context,
    runs: list[Path] | None = typer.Option(
        None,
        "--runs",
        help="Run root to scan (repeatable). Defaults to the current directory.",
    ),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address."),
    port: int = typer.Option(8765, "--port", help="Bind port."),
    root_path: str = typer.Option(
        "", "--root-path", help="Proxy prefix, e.g. /user/me/proxy/8765."
    ),
    allow_remote: bool = typer.Option(
        False,
        "--allow-remote",
        help="Allow a non-loopback bind. The service has no authentication.",
    ),
    geometry: Path | None = typer.Option(
        None,
        "--geometry",
        help="Optional block GeoJSON for map layers.",
    ),
    geometry_crs: str | None = typer.Option(
        None,
        "--geometry-crs",
        help="Source CRS for --geometry/run-local GeoJSON (e.g. EPSG:3005).",
    ),
) -> None:
    """Start the web service when no subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        from fhops.web.app import ServiceConfig, run_server
    except ModuleNotFoundError as exc:
        typer.echo(
            "The web service needs optional dependencies. Install with: pip install 'fhops[web]'",
            err=True,
        )
        raise typer.Exit(1) from exc
    config = ServiceConfig(
        roots=runs or [Path.cwd()],
        host=host,
        port=port,
        root_path=root_path,
        allow_remote=allow_remote,
        geometry=geometry,
        geometry_crs=geometry_crs,
    )
    try:
        run_server(config)
    except (RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@web_app.command("manifest")
def manifest(
    run_dir: Path = typer.Argument(..., help="Run directory to inspect/write."),
    domain: str | None = typer.Option(
        None, "--domain", help="operational|hauling|tactical_operational"
    ),
    run_type: str | None = typer.Option(None, "--run-type", help="Run type label."),
    command: str | None = typer.Option(None, "--command", help="Command that produced the run."),
    scenario: str | None = typer.Option(None, "--scenario", help="Scenario path."),
    solver: str | None = typer.Option(None, "--solver", help="Solver label."),
    seed: int | None = typer.Option(None, "--seed", help="Random seed."),
    status: str | None = typer.Option(None, "--status", help="Run status."),
) -> None:
    """Write `run.json` for a run directory from its artefacts."""
    payload = build_run_manifest(
        run_dir,
        domain=domain,
        run_type=run_type,
        command=command,
        scenario=scenario,
        solver=solver,
        seed=seed,
        status=status,
    )
    typer.echo(json.dumps(payload, indent=2))


@web_app.command("discover")
def discover(
    roots: list[Path] = typer.Argument(..., help="Run roots to scan."),
) -> None:
    """Print discovered runs as JSON."""
    records = discover_runs(roots)
    typer.echo(json.dumps([record.to_dict() for record in records], indent=2))
