"""Tree-inventory CLI commands for tree-scale FHOPS workflows."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from fhops.ground_system import (
    DEFAULT_BUNCH_VOLUME_M3,
    DEFAULT_FELLER_REACH_M,
    DEFAULT_FELLER_TRAVEL_SPEED_MPS,
    DEFAULT_RATE_MODEL,
    DEFAULT_SKIDDER_CAPACITY_M3,
    BreakdownConfig,
    DowntimeWindow,
    GroundSystemError,
    MachineSpec,
    simulate_ground_system,
    write_ground_system,
)
from fhops.spatial_machine import (
    DEFAULT_MAX_SLOPE_PERCENT,
    DEFAULT_REACH_RADIUS_M,
    DEFAULT_TRAVEL_SPEED_M_PER_S,
    Obstacle,
    SpatialMachineError,
    simulate_block,
    write_spatial_simulation,
)
from fhops.stem import (
    DEFAULT_FORM_FACTOR,
    DEFAULT_LOG_LENGTH_M,
    DEFAULT_SAWLOG_MIN_DBH_CM,
    DEFAULT_STUMP_HEIGHT_M,
    ReferenceStemModel,
    StemModelError,
    build_stem_inventory,
    write_stem_inventory,
)
from fhops.tree_inventory import validate_tree_inventory
from fhops.tree_mapping import (
    DEFAULT_RECONCILIATION_TOLERANCE,
    TreeInventoryMappingError,
    TreeInventoryRegistrationError,
    map_tree_inventory,
    register_tree_inventory,
    write_tree_mapping,
)
from fhops.tree_replay import (
    DEFAULT_REPLAY_TOLERANCE,
    TreeReplayError,
    replay_tree_schedule,
    write_tree_replay,
)
from fhops.tree_scene import (
    DEFAULT_LOD_THRESHOLD,
    DEFAULT_MAX_LOG_NODES,
    TreeSceneError,
    write_tree_scene,
)

tree_app = typer.Typer(add_completion=False, no_args_is_help=True)
inventory_app = typer.Typer(add_completion=False, no_args_is_help=True)
tree_app.add_typer(
    inventory_app,
    name="inventory",
    help="Validate individual-tree inventories for tree-scale simulation.",
)


@inventory_app.command("validate")
def tree_inventory_validate(
    inventory: Path = typer.Argument(..., help="Tree inventory CSV."),
    metadata: Path | None = typer.Option(None, "--metadata", help="Tree inventory metadata JSON."),
    block: list[str] | None = typer.Option(
        None, "--block", help="Known block id. Repeat for multiple blocks."
    ),
) -> None:
    """Validate a tree inventory without modifying it."""
    report = validate_tree_inventory(
        inventory,
        metadata_path=metadata,
        block_ids=set(block) if block else None,
    )
    typer.echo(json.dumps(report.to_dict(), indent=2))
    if not report.is_valid:
        raise typer.Exit(1)


@tree_app.command("register")
def tree_register(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML."),
    inventory: Path = typer.Argument(..., help="Tree inventory CSV."),
    metadata: Path | None = typer.Option(None, "--metadata", help="Tree inventory metadata JSON."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print the pin without writing the scenario."
    ),
) -> None:
    """Validate and pin a tree inventory in a scenario."""
    try:
        result = register_tree_inventory(
            scenario,
            inventory,
            metadata_path=metadata,
            dry_run=dry_run,
        )
    except TreeInventoryRegistrationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result.to_dict(), indent=2))


@tree_app.command("map")
def tree_map(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML with a tree-inventory pin."),
    out: Path | None = typer.Option(
        None, "--out", help="Mapping output directory. Print only when omitted."
    ),
    tolerance: float = typer.Option(
        DEFAULT_RECONCILIATION_TOLERANCE,
        "--tolerance",
        help="Relative tolerance for stem-density and volume reconciliation.",
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Refuse when any block reconciliation warns."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print the map without writing outputs."
    ),
) -> None:
    """Map a pinned tree inventory to blocks and reconcile block evidence."""
    try:
        mapping = map_tree_inventory(
            scenario,
            tolerance=tolerance,
            require_reconciled=strict,
        )
        paths = None if dry_run or out is None else write_tree_mapping(mapping, out)
    except TreeInventoryMappingError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    payload = mapping.to_dict()
    if paths is not None:
        payload["paths"] = {key: str(value) for key, value in paths.items()}
    typer.echo(json.dumps(payload, indent=2))


@tree_app.command("stems")
def tree_stems(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML with a tree-inventory pin."),
    out: Path | None = typer.Option(
        None, "--out", help="Stem output directory. Print only when omitted."
    ),
    tolerance: float = typer.Option(
        DEFAULT_RECONCILIATION_TOLERANCE,
        "--tolerance",
        help="Relative tolerance for merchantable-volume reconciliation.",
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Refuse when a block volume reconciliation warns."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print the manifest without writing outputs."
    ),
    form_factor: float = typer.Option(
        DEFAULT_FORM_FACTOR, "--form-factor", help="Reference model form factor."
    ),
    log_length: float = typer.Option(
        DEFAULT_LOG_LENGTH_M, "--log-length", help="Target log length in metres."
    ),
    stump_height: float = typer.Option(
        DEFAULT_STUMP_HEIGHT_M, "--stump-height", help="Stump height in metres."
    ),
    sawlog_min_dbh: float = typer.Option(
        DEFAULT_SAWLOG_MIN_DBH_CM,
        "--sawlog-min-dbh",
        help="Minimum DBH in centimetres for the sawlog product class.",
    ),
) -> None:
    """Derive stem volumes and bucked logs for a pinned tree inventory."""
    try:
        model = ReferenceStemModel(
            form_factor=form_factor,
            log_length_m=log_length,
            stump_height_m=stump_height,
            sawlog_min_dbh_cm=sawlog_min_dbh,
        )
        result = build_stem_inventory(
            scenario,
            model=model,
            tolerance=tolerance,
            require_reconciled=strict,
        )
        paths = None if dry_run or out is None else write_stem_inventory(result, out)
    except StemModelError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    payload = result.to_dict()
    if paths is not None:
        payload["paths"] = {key: str(value) for key, value in paths.items()}
    typer.echo(json.dumps(payload, indent=2))


@tree_app.command("simulate")
def tree_simulate(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML with a tree-inventory pin."),
    block: str = typer.Option(..., "--block", help="Block id to simulate."),
    machine: str = typer.Option(..., "--machine", help="Scenario machine id."),
    out: Path | None = typer.Option(
        None, "--out", help="Simulation output directory. Print only when omitted."
    ),
    start_x: float | None = typer.Option(None, "--start-x", help="Machine start easting (m)."),
    start_y: float | None = typer.Option(None, "--start-y", help="Machine start northing (m)."),
    start_z: float | None = typer.Option(None, "--start-z", help="Machine start elevation (m)."),
    reach_radius: float = typer.Option(
        DEFAULT_REACH_RADIUS_M, "--reach-radius", help="Processing reach in metres."
    ),
    travel_speed: float = typer.Option(
        DEFAULT_TRAVEL_SPEED_M_PER_S,
        "--travel-speed",
        help="Travel speed in metres per second.",
    ),
    max_slope: float = typer.Option(
        DEFAULT_MAX_SLOPE_PERCENT,
        "--max-slope",
        help="Maximum absolute terrain slope percent.",
    ),
    obstacle: list[str] | None = typer.Option(
        None,
        "--obstacle",
        help="Circular obstacle as x,y,radius_m. Repeat for multiple obstacles.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print the simulation without writing outputs."
    ),
) -> None:
    """Simulate one machine processing trees in one block."""
    try:
        obstacles = tuple(_parse_obstacle(value) for value in (obstacle or []))
        result = simulate_block(
            scenario,
            block_id=block,
            machine_id=machine,
            start_x_m=start_x,
            start_y_m=start_y,
            start_z_m=start_z,
            reach_radius_m=reach_radius,
            travel_speed_m_per_s=travel_speed,
            max_slope_percent=max_slope,
            obstacles=obstacles,
        )
        paths = None if dry_run or out is None else write_spatial_simulation(result, out)
    except (SpatialMachineError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    payload = result.to_dict()
    if paths is not None:
        payload["paths"] = {key: str(value) for key, value in paths.items()}
    typer.echo(json.dumps(payload, indent=2))


def _parse_downtime(value: str) -> DowntimeWindow:
    parts = [part.strip() for part in value.split(":")]
    if len(parts) not in {3, 4}:
        raise ValueError(f"Downtime {value!r} must be MACHINE:START_HOURS:DURATION_HOURS[:REASON].")
    machine = parts[0]
    try:
        start_hours = float(parts[1])
        duration_hours = float(parts[2])
    except ValueError as exc:
        raise ValueError(f"Downtime {value!r} must contain numeric hours.") from exc
    if start_hours < 0 or duration_hours <= 0:
        raise ValueError("Downtime start must be >= 0 and duration must be > 0.")
    return DowntimeWindow(
        machine_id=machine,
        start_s=start_hours * 3600.0,
        duration_s=duration_hours * 3600.0,
        reason=parts[3] if len(parts) == 4 and parts[3] else "downtime",
    )


def _parse_obstacle(value: str) -> Obstacle:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        raise ValueError(f"Obstacle {value!r} must be x,y,radius_m.")
    try:
        x, y, radius = (float(part) for part in parts)
    except ValueError as exc:
        raise ValueError(f"Obstacle {value!r} must contain three numbers.") from exc
    if radius <= 0:
        raise ValueError("Obstacle radius must be positive.")
    return Obstacle(x_m=x, y_m=y, radius_m=radius)


@tree_app.command("replay")
def tree_replay(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML with a tree-inventory pin."),
    assignments: Path = typer.Argument(..., help="Assignments CSV."),
    out: Path | None = typer.Option(
        None, "--out", help="Replay output directory. Print only when omitted."
    ),
    tolerance: float = typer.Option(
        DEFAULT_REPLAY_TOLERANCE,
        "--tolerance",
        help="Relative tolerance for scheduled-versus-simulated volume.",
    ),
    obstacle: list[str] | None = typer.Option(
        None,
        "--obstacle",
        help="Circular obstacle as x,y,radius_m. Repeat for multiple obstacles.",
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Refuse when any replay discrepancy is recorded."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print the replay without writing outputs."
    ),
) -> None:
    """Replay an existing assignments schedule at tree scale."""
    try:
        obstacles = tuple(_parse_obstacle(value) for value in (obstacle or []))
        result = replay_tree_schedule(
            scenario,
            assignments,
            tolerance=tolerance,
            obstacles=obstacles,
            require_complete=strict,
        )
        paths = None if dry_run or out is None else write_tree_replay(result, out)
    except (TreeReplayError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    payload = result.to_dict()
    if paths is not None:
        payload["paths"] = {key: str(value) for key, value in paths.items()}
    typer.echo(json.dumps(payload, indent=2))


@tree_app.command("scene")
def tree_scene(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML with a tree-inventory pin."),
    assignments: Path = typer.Argument(..., help="Assignments CSV."),
    out: Path = typer.Option(..., "--out", help="Scene output directory."),
    lod_threshold: int = typer.Option(
        DEFAULT_LOD_THRESHOLD,
        "--lod-threshold",
        help="Use simple tree geometry above this tree count.",
    ),
    max_log_nodes: int = typer.Option(
        DEFAULT_MAX_LOG_NODES,
        "--max-log-nodes",
        help="Maximum individual log nodes.",
    ),
    obstacle: list[str] | None = typer.Option(
        None,
        "--obstacle",
        help="Circular obstacle as x,y,radius_m. Repeat for multiple obstacles.",
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Refuse when the replay has any discrepancy."
    ),
) -> None:
    """Export a deterministic glTF/GLB tree scene."""
    try:
        obstacles = tuple(_parse_obstacle(value) for value in (obstacle or []))
        result = write_tree_scene(
            scenario,
            assignments,
            out,
            lod_threshold=lod_threshold,
            max_log_nodes=max_log_nodes,
            obstacles=obstacles,
            require_complete=strict,
        )
    except (TreeSceneError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        json.dumps(
            {
                "scene_id": result.scene_id,
                "gltf": str(result.gltf_path),
                "glb": str(result.glb_path),
                "manifest": str(result.manifest_path),
                "camera_path": str(result.camera_path),
                "viewer": str(result.viewer_path),
                "tree_count": result.tree_count,
                "processed_count": result.processed_count,
                "log_count": result.log_count,
                "lod": result.lod,
            },
            indent=2,
        )
    )


@tree_app.command("system")
def tree_system(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML with a tree-inventory pin."),
    block: str = typer.Option(..., "--block", help="Block id to simulate."),
    feller: str = typer.Option(..., "--feller", help="Feller-buncher machine id."),
    skidder: list[str] = typer.Option(..., "--skidder", help="Grapple-skidder machine id. Repeat."),
    processor: list[str] | None = typer.Option(
        None, "--processor", help="Optional roadside processor machine id. Repeat for multiple."
    ),
    loader: str = typer.Option(..., "--loader", help="Loader machine id."),
    out: Path | None = typer.Option(
        None, "--out", help="System output directory. Print only when omitted."
    ),
    bunch_volume: float = typer.Option(
        DEFAULT_BUNCH_VOLUME_M3, "--bunch-volume", help="Target bunch volume in cubic metres."
    ),
    rate_model: str = typer.Option(
        DEFAULT_RATE_MODEL,
        "--rate-model",
        help="calibrated (Han/Barko) or reference (fixed MachineSpec cycle times).",
    ),
    landing_x: float | None = typer.Option(None, "--landing-x", help="Landing easting (m)."),
    landing_y: float | None = typer.Option(None, "--landing-y", help="Landing northing (m)."),
    dem: Path | None = typer.Option(
        None, "--dem", help="Optional GeoTIFF DEM in the scenario CRS."
    ),
    road: Path | None = typer.Option(
        None, "--road", help="Optional GeoJSON line for a single connected road corridor."
    ),
    terrain_step: float = typer.Option(
        10.0, "--terrain-step", help="DEM sampling interval along a route (m)."
    ),
    max_skidder_grade: float = typer.Option(
        35.0, "--max-skidder-grade", help="Maximum allowed skidder route grade (%)."
    ),
    terrain_speed_factor: float = typer.Option(
        0.02, "--terrain-speed-factor", help="Speed loss per percent of mean route grade."
    ),
    shift_days: int | None = typer.Option(
        None, "--shift-days", help="Operating days. Omit for continuous time."
    ),
    shifts_per_day: int = typer.Option(1, "--shifts-per-day", help="Shifts per operating day."),
    hours_per_shift: float = typer.Option(
        10.0, "--hours-per-shift", help="Productive hours per shift."
    ),
    shift_start_hour: float = typer.Option(
        0.0, "--shift-start-hour", help="First shift start hour."
    ),
    downtime: list[str] | None = typer.Option(
        None,
        "--downtime",
        help="Machine downtime as MACHINE:START_HOURS:DURATION_HOURS[:REASON]. Repeat.",
    ),
    failure_rate: float | None = typer.Option(
        None, "--failure-rate", help="Stochastic failures per machine operating hour."
    ),
    repair_hours: float = typer.Option(
        2.0, "--repair-hours", help="Mean repair duration for stochastic breakdowns."
    ),
    repair_cv: float = typer.Option(
        0.5, "--repair-cv", help="Coefficient of variation for repair duration."
    ),
    breakdown_seed: int = typer.Option(20261029, "--breakdown-seed", help="Breakdown RNG seed."),
    truck_capacity: float | None = typer.Option(
        None, "--truck-capacity", help="Truck payload capacity (m3). Omit to disable trucking."
    ),
    truck_cycle: float = typer.Option(
        3600.0, "--truck-cycle", help="Truck round trip excluding load (s)."
    ),
    truck_count: int = typer.Option(1, "--truck-count", help="Number of trucks."),
    truck_load_time: float = typer.Option(
        300.0, "--truck-load-time", help="Truck loading time (s)."
    ),
    landing_capacity: float | None = typer.Option(
        None, "--landing-capacity", help="Landing inventory capacity (m3)."
    ),
    feller_reach: float = typer.Option(
        DEFAULT_FELLER_REACH_M, "--feller-reach", help="Feller-buncher reach in metres."
    ),
    feller_speed: float = typer.Option(
        DEFAULT_FELLER_TRAVEL_SPEED_MPS,
        "--feller-speed",
        help="Feller-buncher travel speed in metres per second.",
    ),
    skidder_capacity: float = typer.Option(
        DEFAULT_SKIDDER_CAPACITY_M3,
        "--skidder-capacity",
        help="Skidder payload capacity in cubic metres.",
    ),
    skidder_empty_speed: float = typer.Option(
        1.4, "--skidder-empty-speed", help="Skidder empty travel speed (m/s)."
    ),
    skidder_loaded_speed: float = typer.Option(
        1.1, "--skidder-loaded-speed", help="Skidder loaded travel speed (m/s)."
    ),
    skidder_load_fixed: float = typer.Option(
        45.0, "--skidder-load-fixed", help="Fixed skidder loading time (s)."
    ),
    skidder_load_per_log: float = typer.Option(
        5.0, "--skidder-load-per-log", help="Skidder loading time per log (s)."
    ),
    skidder_unload_fixed: float = typer.Option(
        45.0, "--skidder-unload-fixed", help="Fixed skidder unloading time (s)."
    ),
    skidder_unload_per_log: float = typer.Option(
        3.0, "--skidder-unload-per-log", help="Skidder unloading time per log (s)."
    ),
    loader_process_fixed: float = typer.Option(
        45.0, "--loader-process-fixed", help="Fixed loader processing time (s)."
    ),
    loader_process_per_log: float = typer.Option(
        4.0, "--loader-process-per-log", help="Loader processing time per log (s)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the system result without writing outputs."
    ),
) -> None:
    """Simulate a feller-buncher/skidder/loader system on one block."""
    try:
        skidder_specs = {
            machine: MachineSpec(
                machine_id=machine,
                machine_type="grapple_skidder",
                capacity_m3=skidder_capacity,
                empty_speed_mps=skidder_empty_speed,
                loaded_speed_mps=skidder_loaded_speed,
                load_fixed_s=skidder_load_fixed,
                load_per_log_s=skidder_load_per_log,
                unload_fixed_s=skidder_unload_fixed,
                unload_per_log_s=skidder_unload_per_log,
            )
            for machine in skidder
        }
        loader_spec = MachineSpec(
            machine_id=loader,
            machine_type="loader",
            process_fixed_s=loader_process_fixed,
            process_per_log_s=loader_process_per_log,
        )
        result = simulate_ground_system(
            scenario,
            block_id=block,
            feller_machine_id=feller,
            skidder_machine_ids=tuple(skidder),
            processor_machine_ids=tuple(processor or ()),
            loader_machine_id=loader,
            landing_x_m=landing_x,
            landing_y_m=landing_y,
            bunch_volume_m3=bunch_volume,
            rate_model=rate_model,  # type: ignore[arg-type]
            dem_path=dem,
            road_path=road,
            terrain_sample_step_m=terrain_step,
            max_skidder_grade_percent=max_skidder_grade,
            terrain_speed_factor=terrain_speed_factor,
            shift_days=shift_days,
            shifts_per_day=shifts_per_day,
            hours_per_shift=hours_per_shift,
            shift_start_hour=shift_start_hour,
            downtime=tuple(_parse_downtime(value) for value in (downtime or [])),
            breakdown_config=(
                BreakdownConfig(
                    failure_rate_per_machine_hour=failure_rate,
                    repair_mean_hours=repair_hours,
                    repair_cv=repair_cv,
                    seed=breakdown_seed,
                )
                if failure_rate is not None
                else None
            ),
            truck_capacity_m3=truck_capacity,
            truck_cycle_time_s=truck_cycle,
            truck_count=truck_count,
            truck_load_time_s=truck_load_time,
            landing_capacity_m3=landing_capacity,
            feller_reach_radius_m=feller_reach,
            feller_travel_speed_m_per_s=feller_speed,
            skidder_specs=skidder_specs,
            loader_spec=loader_spec,
        )
        paths = None if dry_run or out is None else write_ground_system(result, out)
    except (GroundSystemError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    payload = result.to_dict()
    if paths is not None:
        payload["paths"] = {key: str(value) for key, value in paths.items()}
    typer.echo(json.dumps(payload, indent=2))
