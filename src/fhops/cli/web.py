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
    workspace: Path = typer.Option(
        Path.cwd(),
        "--workspace",
        help="Working directory for CLI subprocesses and scenario paths.",
    ),
    allow_agent: bool = typer.Option(
        False,
        "--allow-agent",
        help="Enable the optional local assistant (installed opencode CLI).",
    ),
    agent_timeout: float = typer.Option(
        120.0,
        "--agent-timeout",
        help="Assistant subprocess timeout in seconds.",
    ),
    lidar_bundles: list[Path] | None = typer.Option(
        None,
        "--lidar-bundles",
        help="Bundle root containing FEMIC LiDAR directories (repeatable).",
    ),
    lidar_timeout: float = typer.Option(
        300.0,
        "--lidar-timeout",
        help="LiDAR mapping subprocess timeout in seconds.",
    ),
    game_level: list[Path] | None = typer.Option(
        None,
        "--game-level",
        help="Stand game level manifest (repeatable, in play order).",
    ),
    game_precompute: list[Path] | None = typer.Option(
        None,
        "--game-precompute",
        help="Matching stand precompute artifact (repeatable).",
    ),
    game_agent_model: str = typer.Option(
        "opencode-go/deepseek-v4.1-flash",
        "--game-agent-model",
        help="Model for optional game debrief/chat agent.",
    ),
    game_explanation_cache: Path | None = typer.Option(
        None,
        "--game-explanation-cache",
        help="JSON cache for game explanations.",
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
        workspace=workspace,
        allow_agent=allow_agent,
        agent_timeout=agent_timeout,
        lidar_bundles=lidar_bundles or [],
        lidar_timeout=lidar_timeout,
        game_levels=game_level or [],
        game_precomputes=game_precompute or [],
        game_agent_model=game_agent_model,
        game_explanation_cache=game_explanation_cache,
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
