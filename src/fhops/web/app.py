"""FastAPI application factory for the optional FHOPS web service.

This module imports FastAPI and is only imported when the ``fhops[web]`` extra is installed. The
core CLI imports :mod:`fhops.cli.web` lazily, so a core install never needs FastAPI.
"""

from __future__ import annotations

import json
import sys
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import fhops
from fhops.web.agent import AgentError, AgentRequest, run_agent
from fhops.web.discovery import RunRecord, discover_runs
from fhops.web.editing import (
    ScenarioEditError,
    read_editable,
    save_tactical_overlay,
    update_hauling,
    update_locks,
    update_objective,
)
from fhops.web.game import GameService, create_game_router
from fhops.web.lidarview import lidar_payload
from fhops.web.lidarworkflow import (
    LidarBundleRequest,
    LidarMapRequest,
    LidarRegisterRequest,
    LidarWorkflowError,
    list_bundles,
    map_bundle_products,
    register_bundle,
    resolve_bundle,
    scenario_for_run,
    validate_bundle,
)
from fhops.web.mapdata import layer_registry, load_block_geometry, map_payload, time_payload
from fhops.web.runs import RunControlRequest, RunManager, RunRequest
from fhops.web.skins import load_skins

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
    geometry:
        Optional block GeoJSON path. When omitted, the service tries the scenario's
        ``geo_block_path`` and a ``blocks.geojson`` file inside the run directory.
    geometry_crs:
        Optional source CRS for the geometry. When omitted, the scenario ``geo_crs`` or the
        GeoJSON ``crs`` member is used; coordinates are transformed to WGS84 for MapLibre.
    workspace:
        Working directory for CLI subprocesses and for resolving scenario paths.
    cli_command:
        Command prefix used to invoke FHOPS. Defaults to the current Python interpreter running
        ``-m fhops.cli.main``.
    allow_agent:
        Enable the optional local assistant. Off by default; the assistant runs the installed
        ``opencode`` CLI with the service user's shell permissions.
    agent_command:
        Command prefix for the assistant.
    agent_timeout:
        Assistant subprocess timeout in seconds.
    lidar_bundles:
        Allowlisted roots containing FEMIC LiDAR bundle directories.
    lidar_timeout:
        Timeout for LiDAR mapping subprocesses.
    game_level:
        Optional stand-level game manifest. Must be paired with ``game_precompute``.
    game_precompute:
        Optional complete stand precompute artifact.
    """

    roots: list[Path] = field(default_factory=lambda: [Path.cwd()])
    host: str = "127.0.0.1"
    port: int = 8765
    root_path: str = ""
    allow_remote: bool = False
    title: str = "FHOPS Web"
    geometry: Path | None = None
    geometry_crs: str | None = None
    workspace: Path = field(default_factory=Path.cwd)
    cli_command: tuple[str, ...] = field(
        default_factory=lambda: (sys.executable, "-m", "fhops.cli.main")
    )
    allow_agent: bool = False
    agent_command: tuple[str, ...] = ("opencode", "run", "--format", "json")
    agent_timeout: float = 120.0
    lidar_bundles: list[Path] = field(default_factory=list)
    lidar_timeout: float = 300.0
    game_level: Path | None = None
    game_precompute: Path | None = None


class ObjectiveUpdate(BaseModel):
    """Objective-weight edit payload."""

    weights: dict[str, float] = Field(default_factory=dict)


class LocksUpdate(BaseModel):
    """Schedule-lock replacement payload."""

    locks: list[dict[str, object]] = Field(default_factory=list)


class HaulingUpdate(BaseModel):
    """Hauling driver/contractor edit payload."""

    driver_policy: dict[str, object] | None = None
    contractors: list[dict[str, object]] | None = None


class TacticalOverlayUpdate(BaseModel):
    """Sparse tactical overlay payload."""

    overlay: dict[str, object] = Field(default_factory=dict)


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
    roots = [root.expanduser().resolve() for root in config.roots]
    run_manager = RunManager()
    lidar_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            run_manager.shutdown()

    app = FastAPI(title=config.title, version=fhops.__version__, lifespan=lifespan)
    if (config.game_level is None) != (config.game_precompute is None):
        raise ValueError("game_level and game_precompute must be configured together.")
    if config.game_level is not None and config.game_precompute is not None:
        game_service = GameService(
            level_path=config.game_level,
            precompute_path=config.game_precompute,
        )
        app.include_router(create_game_router(game_service))

    def _scenario_target(scenario_id: str) -> tuple[Path, str | None, RunRecord]:
        record = _find_run(roots, scenario_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Unknown scenario/run id={scenario_id}")
        manifest = record.manifest or {}
        value = manifest.get("scenario")
        if not value:
            raise HTTPException(
                status_code=404, detail=f"Run {scenario_id} has no scenario path in run.json"
            )
        raw = Path(str(value)).expanduser()
        candidates = [raw] if raw.is_absolute() else [config.workspace / raw, record.path / raw]
        path = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
        path = path.resolve()
        allowed = [config.workspace.resolve(), *roots]
        if not any(path.is_relative_to(root) for root in allowed):
            raise HTTPException(status_code=403, detail="Scenario path escapes the allowed roots")
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"Scenario not found: {value}")
        return path, record.domain or manifest.get("domain"), record

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "version": fhops.__version__,
            "roots": [str(root) for root in roots],
            "domain_count": 3,
            "skins": [skin.id for skin in load_skins()],
            "agent_enabled": config.allow_agent,
        }

    @app.get("/api/runs")
    def runs() -> list[dict[str, object]]:
        return [record.to_dict() for record in discover_runs(roots)]

    @app.post("/api/runs")
    def start_run(request: RunRequest) -> dict[str, Any]:
        run_root = roots[0]
        run_root.mkdir(parents=True, exist_ok=True)
        try:
            record = run_manager.start(
                request,
                workspace=config.workspace,
                run_root=run_root,
                cli_command=config.cli_command,
            )
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return run_manager.status(record)

    @app.get("/api/runs/{run_id}/status")
    def run_status(run_id: str) -> dict[str, Any]:
        active = run_manager.get(run_id)
        if active is not None:
            return run_manager.status(active)
        record = _find_run(roots, run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Unknown run_id={run_id}")
        return {
            "run_id": record.run_id,
            "domain": record.domain,
            "run_type": record.run_type,
            "status": record.status,
            "finished": True,
            "paused": False,
            "returncode": None,
            "output_dir": str(record.path),
            "started_at": None,
            "elapsed_seconds": None,
        }

    @app.post("/api/runs/{run_id}/control")
    def control_run(run_id: str, control: RunControlRequest) -> dict[str, Any]:
        try:
            return run_manager.control(run_id, control.action)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown live run_id={run_id}") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}/events")
    def run_events(run_id: str) -> Response:
        live = run_manager.get(run_id)
        if live is None:
            if _find_run(roots, run_id) is None:
                raise HTTPException(status_code=404, detail=f"Unknown run_id={run_id}")
            return Response(status_code=204)
        if live.finished:
            return Response(status_code=204)
        return StreamingResponse(
            run_manager.stream(run_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/scenarios/{scenario_id}")
    def scenario_detail(scenario_id: str) -> dict[str, object]:
        path, domain, record = _scenario_target(scenario_id)
        payload = read_editable(path, domain=domain, overlay_root=roots[0])
        payload["scenario_id"] = scenario_id
        payload["run_id"] = record.run_id
        return payload

    @app.put("/api/scenarios/{scenario_id}/objective")
    def scenario_objective(scenario_id: str, update: ObjectiveUpdate) -> dict[str, object]:
        path, _, record = _scenario_target(scenario_id)
        try:
            payload = update_objective(path, update.weights)
        except ScenarioEditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload["scenario_id"] = scenario_id
        payload["run_id"] = record.run_id
        return payload

    @app.put("/api/scenarios/{scenario_id}/locks")
    def scenario_locks(scenario_id: str, update: LocksUpdate) -> dict[str, object]:
        path, _, record = _scenario_target(scenario_id)
        try:
            payload = update_locks(path, update.locks)
        except ScenarioEditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload["scenario_id"] = scenario_id
        payload["run_id"] = record.run_id
        return payload

    @app.put("/api/scenarios/{scenario_id}/hauling")
    def scenario_hauling(scenario_id: str, update: HaulingUpdate) -> dict[str, object]:
        path, _, record = _scenario_target(scenario_id)
        try:
            payload = update_hauling(
                path,
                driver_policy=update.driver_policy,
                contractors=update.contractors,
            )
        except ScenarioEditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload["scenario_id"] = scenario_id
        payload["run_id"] = record.run_id
        return payload

    @app.put("/api/scenarios/{scenario_id}/tactical")
    def scenario_tactical(scenario_id: str, update: TacticalOverlayUpdate) -> dict[str, object]:
        path, _, record = _scenario_target(scenario_id)
        try:
            payload = save_tactical_overlay(path, update.overlay, overlay_root=roots[0])
        except ScenarioEditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload["scenario_id"] = scenario_id
        payload["run_id"] = record.run_id
        return payload

    @app.post("/api/agent")
    def assistant(request: AgentRequest) -> dict[str, object]:
        if not config.allow_agent:
            raise HTTPException(
                status_code=403,
                detail="Assistant is disabled; start fhops web with --allow-agent to enable it.",
            )
        try:
            return run_agent(
                request,
                workspace=config.workspace,
                command=config.agent_command,
                timeout=config.agent_timeout,
            )
        except AgentError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, object]:
        record = _find_run(roots, run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Unknown run_id={run_id}")
        return record.to_dict()

    def run_or_404(run_id: str) -> RunRecord:
        record = _find_run(roots, run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Unknown run_id={run_id}")
        return record

    @app.get("/api/runs/{run_id}/summary")
    def run_summary(run_id: str) -> dict[str, Any]:
        record = run_or_404(run_id)
        return _summary_payload(record)

    @app.get("/api/runs/{run_id}/kpis")
    def run_kpis(run_id: str) -> dict[str, Any]:
        record = run_or_404(run_id)
        return _kpi_payload(record)

    @app.get("/api/runs/{run_id}/assignments")
    def run_assignments(
        run_id: str,
        day: int | None = Query(None),
        shift: str | None = Query(None),
        machine: str | None = Query(None),
        block: str | None = Query(None),
        limit: int = Query(5000, ge=1, le=50000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        record = run_or_404(run_id)
        return _table_payload(
            record,
            "assignments",
            {"day": day, "shift_id": shift, "machine_id": machine, "block_id": block},
            limit=limit,
            offset=offset,
        )

    @app.get("/api/runs/{run_id}/playback")
    def run_playback(
        run_id: str,
        scope: str = Query("day", pattern="^(day|shift)$"),
    ) -> dict[str, Any]:
        record = run_or_404(run_id)
        logical = "day_summary" if scope == "day" else "shift_summary"
        return _table_payload(record, logical, {}, limit=50000, offset=0)

    @app.get("/api/runs/{run_id}/hauling/flows")
    def hauling_flows(
        run_id: str,
        day: int | None = Query(None),
        block: str | None = Query(None),
        yard: str | None = Query(None),
        sort: str | None = Query(None),
        contractor: str | None = Query(None),
        truck_type: str | None = Query(None),
        limit: int = Query(5000, ge=1, le=50000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        record = run_or_404(run_id)
        return _table_payload(
            record,
            "haul_flows",
            {
                "day": day,
                "block_id": block,
                "yard_id": yard,
                "log_sort_id": sort,
                "contractor_id": contractor,
                "truck_type_id": truck_type,
            },
            limit=limit,
            offset=offset,
        )

    @app.get("/api/runs/{run_id}/hauling/truckloads")
    def hauling_truckloads(
        run_id: str,
        day: int | None = Query(None),
        block: str | None = Query(None),
        yard: str | None = Query(None),
        contractor: str | None = Query(None),
        truck_type: str | None = Query(None),
        limit: int = Query(5000, ge=1, le=50000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        record = run_or_404(run_id)
        return _table_payload(
            record,
            "haul_truckloads",
            {
                "day": day,
                "block_id": block,
                "yard_id": yard,
                "contractor_id": contractor,
                "truck_type_id": truck_type,
            },
            limit=limit,
            offset=offset,
        )

    @app.get("/api/runs/{run_id}/hauling/schedule")
    def hauling_schedule(
        run_id: str,
        day: int | None = Query(None),
        truck: str | None = Query(None),
        contractor: str | None = Query(None),
        limit: int = Query(5000, ge=1, le=50000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        record = run_or_404(run_id)
        return _table_payload(
            record,
            "haul_schedule",
            {"day": day, "truck_id": truck, "contractor_id": contractor},
            limit=limit,
            offset=offset,
        )

    @app.get("/api/runs/{run_id}/hauling/yard-inventory")
    def hauling_yard_inventory(
        run_id: str,
        day: int | None = Query(None),
        yard: str | None = Query(None),
        sort: str | None = Query(None),
        limit: int = Query(5000, ge=1, le=50000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        record = run_or_404(run_id)
        return _table_payload(
            record,
            "haul_yard_inventory",
            {"day": day, "yard_id": yard, "log_sort_id": sort},
            limit=limit,
            offset=offset,
        )

    @app.get("/api/runs/{run_id}/hauling/contractor-workload")
    def hauling_contractor_workload(
        run_id: str,
        day: int | None = Query(None),
        contractor: str | None = Query(None),
        limit: int = Query(5000, ge=1, le=50000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        record = run_or_404(run_id)
        return _table_payload(
            record,
            "haul_contractor_workload",
            {"day": day, "contractor_id": contractor},
            limit=limit,
            offset=offset,
        )

    @app.get("/api/runs/{run_id}/hauling/trucks")
    def hauling_trucks(run_id: str) -> dict[str, Any]:
        return _table_payload(run_or_404(run_id), "haul_truck_summary", {}, limit=50000, offset=0)

    @app.get("/api/runs/{run_id}/hauling/loaders")
    def hauling_loaders(run_id: str) -> dict[str, Any]:
        return _table_payload(run_or_404(run_id), "haul_loader_summary", {}, limit=50000, offset=0)

    def tactical_table(
        run_id: str,
        logical: str,
        period: str | None,
        product: str | None,
        facility: str | None,
        block: str | None,
        limit: int,
        offset: int,
        facility_column: str = "facility_id",
    ) -> dict[str, Any]:
        record = run_or_404(run_id)
        return _table_payload(
            record,
            logical,
            {
                "period_id": period,
                "product_id": product,
                facility_column: facility,
                "block_id": block,
            },
            limit=limit,
            offset=offset,
        )

    @app.get("/api/runs/{run_id}/tactical/harvest")
    def tactical_harvest(
        run_id: str,
        period: str | None = Query(None),
        block: str | None = Query(None),
        limit: int = Query(5000, ge=1, le=50000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        return tactical_table(run_id, "harvest_decisions", period, None, None, block, limit, offset)

    @app.get("/api/runs/{run_id}/tactical/production")
    def tactical_production(
        run_id: str,
        period: str | None = Query(None),
        product: str | None = Query(None),
        block: str | None = Query(None),
        limit: int = Query(5000, ge=1, le=50000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        return tactical_table(run_id, "production", period, product, None, block, limit, offset)

    @app.get("/api/runs/{run_id}/tactical/flows")
    def tactical_flows(
        run_id: str,
        period: str | None = Query(None),
        product: str | None = Query(None),
        facility: str | None = Query(None),
        limit: int = Query(5000, ge=1, le=50000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        return tactical_table(
            run_id, "flows", period, product, facility, None, limit, offset, "destination_id"
        )

    @app.get("/api/runs/{run_id}/tactical/inventory")
    def tactical_inventory(
        run_id: str,
        period: str | None = Query(None),
        product: str | None = Query(None),
        facility: str | None = Query(None),
        limit: int = Query(5000, ge=1, le=50000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        return tactical_table(run_id, "inventory", period, product, facility, None, limit, offset)

    @app.get("/api/runs/{run_id}/tactical/purchases")
    def tactical_purchases(
        run_id: str,
        period: str | None = Query(None),
        product: str | None = Query(None),
        facility: str | None = Query(None),
        limit: int = Query(5000, ge=1, le=50000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        return tactical_table(run_id, "purchases", period, product, facility, None, limit, offset)

    @app.get("/api/runs/{run_id}/tactical/roads")
    def tactical_roads(
        run_id: str,
        period: str | None = Query(None),
        limit: int = Query(5000, ge=1, le=50000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        return tactical_table(run_id, "roads", period, None, None, None, limit, offset)

    @app.get("/api/runs/{run_id}/tactical/silviculture")
    def tactical_silviculture(
        run_id: str,
        period: str | None = Query(None),
        block: str | None = Query(None),
        limit: int = Query(5000, ge=1, le=50000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        return tactical_table(run_id, "silviculture", period, None, None, block, limit, offset)

    @app.get("/api/runs/{run_id}/tactical/fleet")
    def tactical_fleet(
        run_id: str,
        period: str | None = Query(None),
        limit: int = Query(5000, ge=1, le=50000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        return tactical_table(run_id, "fleet", period, None, None, None, limit, offset)

    @app.get("/api/runs/{run_id}/time")
    def run_time(run_id: str) -> dict[str, Any]:
        return time_payload(run_or_404(run_id))

    @app.get("/api/runs/{run_id}/lidar")
    def run_lidar(run_id: str) -> dict[str, Any]:
        record = run_or_404(run_id)
        return lidar_payload(record, config.workspace)

    @app.get("/api/lidar/bundles")
    def lidar_bundle_list() -> dict[str, Any]:
        return list_bundles(config.lidar_bundles)

    @app.post("/api/runs/{run_id}/lidar/validate")
    def lidar_validate(run_id: str, request: LidarBundleRequest) -> dict[str, Any]:
        run_or_404(run_id)
        try:
            bundle = resolve_bundle(request.bundle, config.lidar_bundles)
            return validate_bundle(
                bundle,
                expected_bundle_id=request.expected_bundle_id,
                expected_bundle_version=request.expected_bundle_version,
            )
        except LidarWorkflowError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/runs/{run_id}/lidar/register")
    def lidar_register(run_id: str, request: LidarRegisterRequest) -> dict[str, Any]:
        record = run_or_404(run_id)
        try:
            bundle = resolve_bundle(request.bundle, config.lidar_bundles)
            scenario = scenario_for_run(record, config.workspace, roots)
            with lidar_lock:
                return register_bundle(
                    scenario,
                    bundle,
                    expected_bundle_id=request.expected_bundle_id,
                    expected_bundle_version=request.expected_bundle_version,
                    dry_run=request.dry_run,
                )
        except LidarWorkflowError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/runs/{run_id}/lidar/map")
    def lidar_map(run_id: str, request: LidarMapRequest) -> dict[str, Any]:
        record = run_or_404(run_id)
        try:
            bundle = resolve_bundle(request.bundle, config.lidar_bundles)
            scenario = scenario_for_run(record, config.workspace, roots)
            resolved_request = request
            if request.roads_geojson:
                roads = Path(request.roads_geojson).expanduser()
                if not roads.is_absolute():
                    roads = scenario.parent / roads
                roads = roads.resolve()
                allowed = [scenario.parent.resolve(), config.workspace.resolve(), *roots]
                if not any(roads.is_relative_to(root) for root in allowed):
                    raise LidarWorkflowError("Roads GeoJSON escapes the allowed roots.")
                resolved_request = request.model_copy(update={"roads_geojson": str(roads)})
            with lidar_lock:
                return map_bundle_products(
                    scenario,
                    bundle,
                    workspace=config.workspace,
                    cli_command=config.cli_command,
                    request=resolved_request,
                    timeout=config.lidar_timeout,
                )
        except LidarWorkflowError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}/layers")
    def run_layers(run_id: str) -> dict[str, Any]:
        record = run_or_404(run_id)
        try:
            geometry = load_block_geometry(record, config.geometry, config.geometry_crs)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "run_id": record.run_id,
            "domain": record.domain,
            "geometry_available": bool(geometry),
            "layers": layer_registry(record, geometry, workspace=config.workspace),
        }

    @app.get("/api/runs/{run_id}/map")
    def run_map(
        run_id: str,
        day: int | None = Query(None),
        period: str | None = Query(None),
        shift: str | None = Query(None),
        layers: str | None = Query(None, description="Comma-separated layer names."),
    ) -> dict[str, Any]:
        record = run_or_404(run_id)
        try:
            geometry = load_block_geometry(record, config.geometry, config.geometry_crs)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not geometry:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No block geometry found. Pass --geometry to the service or add a block "
                    "GeoJSON path to the scenario."
                ),
            )
        requested = [name.strip() for name in layers.split(",") if name.strip()] if layers else None
        try:
            return map_payload(
                record,
                geometry,
                day=day,
                period=period,
                shift=shift,
                layers=requested,
                workspace=config.workspace,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}/reports")
    def reports(run_id: str) -> dict[str, Any]:
        record = run_or_404(run_id)
        return _report_listing(record)

    @app.get("/api/runs/{run_id}/reports/{report_path:path}")
    def report_file(run_id: str, report_path: str) -> FileResponse:
        record = run_or_404(run_id)
        path = _safe_child(record.path, report_path)
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"Missing report file: {report_path}")
        return FileResponse(path)

    @app.get("/api/skins")
    def skins() -> list[dict[str, Any]]:
        return [skin.to_dict() for skin in load_skins()]

    @app.get("/api/skins/{skin_id}")
    def skin(skin_id: str) -> dict[str, Any]:
        for manifest in load_skins():
            if manifest.id == skin_id:
                return manifest.to_dict()
        raise HTTPException(status_code=404, detail=f"Unknown skin_id={skin_id}")

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/game")
    def game_page() -> FileResponse:
        path = _STATIC_DIR / "game.html"
        if not path.exists():
            raise HTTPException(status_code=500, detail="Game shell is missing")
        return FileResponse(path)

    @app.get("/")
    def index() -> FileResponse:
        index_path = _STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=500, detail="Static shell is missing")
        return FileResponse(index_path)

    return app


def _summary_payload(record: RunRecord) -> dict[str, Any]:
    for logical in ("haul_summary", "tactical_summary", "summary"):
        if logical in record.files:
            return _read_json(record, logical)
    raise HTTPException(
        status_code=404,
        detail=f"Run {record.run_id} has no summary artefact",
    )


def _kpi_payload(record: RunRecord) -> dict[str, Any]:
    for logical in ("haul_kpis", "kpis"):
        if logical in record.files:
            return _read_json(record, logical)
    for logical in ("tactical_summary", "haul_summary", "summary"):
        if logical in record.files:
            payload = _read_json(record, logical)
            return {key: value for key, value in payload.items() if key != "files"}
    raise HTTPException(status_code=404, detail=f"Run {record.run_id} has no KPI artefact")


def _read_json(record: RunRecord, logical: str) -> dict[str, Any]:
    path = _artifact_path(record, logical)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Could not read {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail=f"{path.name} is not a JSON object")
    return payload


def _table_payload(
    record: RunRecord,
    logical: str,
    filters: dict[str, Any],
    *,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    path = _artifact_path(record, logical)
    frame = _read_frame(path)
    for column, value in filters.items():
        if value is None or value == "":
            continue
        if column not in frame.columns:
            raise HTTPException(status_code=400, detail=f"Unknown filter column: {column}")
        frame = frame[frame[column].astype(str) == str(value)]
    total = len(frame)
    if offset:
        frame = frame.iloc[offset:]
    if limit:
        frame = frame.head(limit)
    records = frame.to_dict("records")
    for row in records:
        for key, value in row.items():
            if pd.isna(value):
                row[key] = None
    return {
        "run_id": record.run_id,
        "artefact": logical,
        "file": record.files[logical],
        "columns": [str(column) for column in frame.columns],
        "rows": records,
        "total": total,
        "returned": len(records),
    }


def _read_frame(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return pd.DataFrame(payload)
        if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
            return pd.DataFrame(payload["rows"])
        return pd.DataFrame([payload])
    raise HTTPException(status_code=400, detail=f"Unsupported table format: {path.suffix}")


def _artifact_path(record: RunRecord, logical: str) -> Path:
    filename = record.files.get(logical)
    if not filename:
        raise HTTPException(
            status_code=404,
            detail=f"Run {record.run_id} has no {logical} artefact",
        )
    path = _safe_child(record.path, filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Missing artefact file: {filename}")
    return path


def _safe_child(run_dir: Path, relative: str) -> Path:
    root = run_dir.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status_code=404, detail=f"Path escapes the run directory: {relative}")
    return path


def _report_listing(record: RunRecord) -> dict[str, Any]:
    root = record.path.resolve()
    reports = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "run.json":
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        reports.append(
            {
                "name": path.name,
                "path": str(relative),
                "size": path.stat().st_size,
                "suffix": path.suffix.lower(),
            }
        )
        if len(reports) >= 500:
            break
    return {"run_id": record.run_id, "reports": reports, "count": len(reports)}


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
