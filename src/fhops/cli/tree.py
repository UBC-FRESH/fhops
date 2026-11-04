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
    Landing,
    LandingFleet,
    MachineSpec,
    ProcessorSpec,
    TruckSpec,
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


def _load_processor_specs(path: Path) -> dict[str, ProcessorSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Processor specs JSON must be an object mapping machine ids.")
    specs: dict[str, ProcessorSpec] = {}
    for machine, values in payload.items():
        if not isinstance(values, dict):
            raise ValueError(f"Processor spec for {machine!r} must be an object.")
        specs[str(machine)] = ProcessorSpec(
            machine_id=str(machine),
            seconds_per_m3=float(values.get("seconds_per_m3", 3600.0 / 35.0)),
            fixed_s=float(values.get("fixed_s", 60.0)),
            per_log_s=float(values.get("per_log_s", 0.5)),
        )
    return specs


def _load_loader_specs(path: Path) -> dict[str, MachineSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Loader specs JSON must be an object mapping machine ids.")
    specs: dict[str, MachineSpec] = {}
    for machine, values in payload.items():
        if not isinstance(values, dict):
            raise ValueError(f"Loader spec for {machine!r} must be an object.")
        specs[str(machine)] = MachineSpec(
            machine_id=str(machine),
            machine_type="loader",
            capacity_m3=float(values.get("capacity_m3", 40.0)),
            empty_speed_mps=float(values.get("empty_speed_mps", 1.4)),
            loaded_speed_mps=float(values.get("loaded_speed_mps", 1.1)),
            load_fixed_s=float(values.get("load_fixed_s", 45.0)),
            load_per_log_s=float(values.get("load_per_log_s", 5.0)),
            unload_fixed_s=float(values.get("unload_fixed_s", 45.0)),
            unload_per_log_s=float(values.get("unload_per_log_s", 3.0)),
            process_fixed_s=float(values.get("process_fixed_s", 45.0)),
            process_per_log_s=float(values.get("process_per_log_s", 4.0)),
        )
    return specs


def _load_skidder_specs(path: Path) -> dict[str, MachineSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Skidder specs JSON must be an object mapping machine ids.")
    specs: dict[str, MachineSpec] = {}
    for machine, values in payload.items():
        if not isinstance(values, dict):
            raise ValueError(f"Skidder spec for {machine!r} must be an object.")
        specs[str(machine)] = MachineSpec(
            machine_id=str(machine),
            machine_type="grapple_skidder",
            capacity_m3=float(values.get("capacity_m3", DEFAULT_SKIDDER_CAPACITY_M3)),
            empty_speed_mps=float(values.get("empty_speed_mps", 1.4)),
            loaded_speed_mps=float(values.get("loaded_speed_mps", 1.1)),
            load_fixed_s=float(values.get("load_fixed_s", 45.0)),
            load_per_log_s=float(values.get("load_per_log_s", 5.0)),
            unload_fixed_s=float(values.get("unload_fixed_s", 45.0)),
            unload_per_log_s=float(values.get("unload_per_log_s", 3.0)),
            productivity_m3_per_smh=(
                float(values["productivity_m3_per_smh"])
                if values.get("productivity_m3_per_smh") is not None
                else None
            ),
            forwarder_model=(
                str(values["forwarder_model"]) if values.get("forwarder_model") else None
            ),
            forwarder_stem_size_m3=float(values.get("forwarder_stem_size_m3", 0.3)),
            forwarder_load_fixed_s=(
                float(values["forwarder_load_fixed_s"])
                if values.get("forwarder_load_fixed_s") is not None
                else None
            ),
            forwarder_load_per_log_s=(
                float(values["forwarder_load_per_log_s"])
                if values.get("forwarder_load_per_log_s") is not None
                else None
            ),
            forwarder_unload_fixed_s=(
                float(values["forwarder_unload_fixed_s"])
                if values.get("forwarder_unload_fixed_s") is not None
                else None
            ),
            forwarder_unload_per_log_s=(
                float(values["forwarder_unload_per_log_s"])
                if values.get("forwarder_unload_per_log_s") is not None
                else None
            ),
        )
    return specs


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


def _parse_landing(value: str, index: int) -> Landing:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) == 2:
        landing_id = f"landing-{index + 1}"
        x_text, y_text = parts
    elif len(parts) == 3:
        landing_id, x_text, y_text = parts
    else:
        raise ValueError(f"Landing {value!r} must be id,x,y or x,y.")
    try:
        x, y = float(x_text), float(y_text)
    except ValueError as exc:
        raise ValueError(f"Landing {value!r} must contain numeric coordinates.") from exc
    if not landing_id:
        raise ValueError("Landing id must not be empty.")
    return Landing(landing_id=landing_id, x_m=x, y_m=y)


def _parse_landing_truck_counts(values: list[str] | None) -> dict[str, int] | None:
    if not values:
        return None
    counts: dict[str, int] = {}
    for value in values:
        parts = value.split(":", 1)
        if len(parts) != 2 or not all(part.strip() for part in parts):
            raise ValueError(f"Landing truck {value!r} must be landing_id:count.")
        landing_id, count_text = (part.strip() for part in parts)
        try:
            count = int(count_text)
        except ValueError as exc:
            raise ValueError(f"Landing truck count {value!r} must be an integer.") from exc
        if count < 0:
            raise ValueError("Landing truck counts must be non-negative.")
        if landing_id in counts:
            raise ValueError(f"Landing {landing_id!r} has more than one truck count.")
        counts[landing_id] = count
    return counts


def _load_landing_truck_specs(path: Path) -> dict[str, TruckSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Landing truck specs JSON must be an object mapping landing ids.")
    specs: dict[str, TruckSpec] = {}
    for landing_id, values in payload.items():
        if not isinstance(values, dict):
            raise ValueError(f"Truck spec for {landing_id!r} must be an object.")
        specs[str(landing_id)] = TruckSpec(
            capacity_m3=float(values.get("capacity_m3", 30.0)),
            cycle_time_s=float(values.get("cycle_time_s", 3600.0)),
            count=int(values.get("count", 1)),
            load_time_s=float(values.get("load_time_s", 300.0)),
            arrival_interval_s=float(values.get("arrival_interval_s", 0.0)),
            one_way_distance_m=(
                float(values["one_way_distance_m"])
                if values.get("one_way_distance_m") is not None
                else None
            ),
            speed_mps=float(values.get("speed_mps", 12.0)),
            mill_service_s=float(values.get("mill_service_s", 600.0)),
            mill_bays=int(values.get("mill_bays", 1)),
        )
    return specs


def _parse_landing_fleets(
    loaders: list[str] | None, processors: list[str] | None
) -> tuple[LandingFleet, ...]:
    loader_map: dict[str, str] = {}
    processor_map: dict[str, list[str]] = {}
    for value in loaders or []:
        parts = value.split(":", 1)
        if len(parts) != 2 or not all(part.strip() for part in parts):
            raise ValueError(f"Landing loader {value!r} must be landing_id:machine_id.")
        landing_id, machine_id = (part.strip() for part in parts)
        if landing_id in loader_map:
            raise ValueError(f"Landing {landing_id!r} has more than one loader assignment.")
        loader_map[landing_id] = machine_id
    for value in processors or []:
        parts = value.split(":", 1)
        if len(parts) != 2 or not all(part.strip() for part in parts):
            raise ValueError(f"Landing processor {value!r} must be landing_id:machine_id.")
        landing_id, machine_id = (part.strip() for part in parts)
        processor_map.setdefault(landing_id, []).append(machine_id)
    missing = set(processor_map) - set(loader_map)
    if missing:
        raise ValueError(
            "Landing processors require a landing loader for: " + ", ".join(sorted(missing))
        )
    return tuple(
        LandingFleet(
            landing_id=landing_id,
            loader_machine_id=loader_machine_id,
            processor_machine_ids=tuple(processor_map.get(landing_id, [])),
        )
        for landing_id, loader_machine_id in loader_map.items()
    )


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
    processor_model: str | None = typer.Option(
        None,
        "--processor-model",
        help="tn103_area_a, tn103_combined, adv5n6_cold, or custom.",
    ),
    processor_rate: float | None = typer.Option(
        None, "--processor-rate", help="Custom processor productivity (m3/SMH)."
    ),
    processor_productivity_multiplier: float = typer.Option(
        1.0,
        "--processor-productivity-multiplier",
        help="Multiplier on processor productive output (>1 is faster).",
    ),
    processor_specs: Path | None = typer.Option(
        None,
        "--processor-specs",
        help='JSON mapping machine id to {"seconds_per_m3": ..., "fixed_s": ...}.',
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
    landing: list[str] | None = typer.Option(
        None,
        "--landing",
        help="Named landing as id,x,y or x,y. Repeat to route bunches to multiple landings.",
    ),
    landing_loader: list[str] | None = typer.Option(
        None,
        "--landing-loader",
        help="Per-landing loader as landing_id:machine_id. Repeat.",
    ),
    landing_processor: list[str] | None = typer.Option(
        None,
        "--landing-processor",
        help="Per-landing processor as landing_id:machine_id. Repeat.",
    ),
    dem: Path | None = typer.Option(
        None, "--dem", help="Optional GeoTIFF DEM in the scenario CRS."
    ),
    road: Path | None = typer.Option(
        None, "--road", help="Optional GeoJSON line for a single connected road corridor."
    ),
    obstacle: list[str] | None = typer.Option(
        None,
        "--obstacle",
        help="Circular obstacle as x,y,radius_m. Repeat for retained-tree exclusions.",
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
    landing_truck: list[str] | None = typer.Option(
        None,
        "--landing-truck",
        help="Per-landing truck count as landing_id:count. Repeat.",
    ),
    landing_truck_specs_path: Path | None = typer.Option(
        None,
        "--landing-truck-specs",
        help="JSON mapping landing id to truck equipment specs.",
    ),
    truck_load_time: float = typer.Option(
        300.0, "--truck-load-time", help="Truck loading time (s)."
    ),
    truck_arrival_interval: float = typer.Option(
        0.0, "--truck-arrival-interval", help="Initial truck arrival stagger (s)."
    ),
    truck_route_distance: float | None = typer.Option(
        None, "--truck-route-distance", help="One-way landing-to-mill distance (m)."
    ),
    truck_speed: float = typer.Option(12.0, "--truck-speed", help="Truck travel speed (m/s)."),
    mill_service: float = typer.Option(600.0, "--mill-service", help="Mill service time (s)."),
    mill_bays: int = typer.Option(1, "--mill-bays", help="Parallel mill service bays."),
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
    feller_productivity_multiplier: float = typer.Option(
        1.0,
        "--feller-productivity-multiplier",
        help="Multiplier on feller processing productivity (<1 slows selection-cut work).",
    ),
    damage_downgrade_fraction: float = typer.Option(
        0.0,
        "--damage-downgrade-fraction",
        help="Fraction of sawlog volume downgraded to pulp by operator damage risk.",
    ),
    path_mode: str = typer.Option(
        "nearest",
        "--path-mode",
        help="Feller path: nearest (legacy) or swath (contiguous boustrophedon rows).",
    ),
    stem_form_factor: float | None = typer.Option(
        None,
        "--stem-form-factor",
        help="Optional calibrated reference stem form factor for this run.",
    ),
    stem_log_length: float = typer.Option(
        DEFAULT_LOG_LENGTH_M, "--stem-log-length", help="Target bucked log length (m)."
    ),
    stem_stump_height: float = typer.Option(
        DEFAULT_STUMP_HEIGHT_M, "--stem-stump-height", help="Stump height (m)."
    ),
    stem_sawlog_min_dbh: float = typer.Option(
        DEFAULT_SAWLOG_MIN_DBH_CM,
        "--stem-sawlog-min-dbh",
        help="Minimum DBH for sawlog product classification (cm).",
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
    loader_specs_path: Path | None = typer.Option(
        None,
        "--loader-specs",
        help="JSON mapping machine id to loader cycle fields (capacity_m3, process_fixed_s, ...).",
    ),
    skidder_specs_path: Path | None = typer.Option(
        None,
        "--skidder-specs",
        help="JSON mapping machine id to skidder cycle fields (capacity_m3, speeds, load/unload times).",
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
        if skidder_specs_path is not None:
            skidder_specs.update(_load_skidder_specs(skidder_specs_path))
        loader_specs_map = (
            _load_loader_specs(loader_specs_path) if loader_specs_path is not None else None
        )
        loader_spec = MachineSpec(
            machine_id=loader,
            machine_type="loader",
            process_fixed_s=loader_process_fixed,
            process_per_log_s=loader_process_per_log,
        )
        stem_inventory = None
        if stem_form_factor is not None:
            stem_inventory = build_stem_inventory(
                scenario,
                model=ReferenceStemModel(
                    form_factor=stem_form_factor,
                    log_length_m=stem_log_length,
                    stump_height_m=stem_stump_height,
                    sawlog_min_dbh_cm=stem_sawlog_min_dbh,
                ),
            )
        if feller_productivity_multiplier <= 0:
            raise GroundSystemError("feller-productivity-multiplier must be positive.")
        if processor_productivity_multiplier <= 0:
            raise GroundSystemError("processor-productivity-multiplier must be positive.")
        if not 0 <= damage_downgrade_fraction <= 1:
            raise GroundSystemError("damage-downgrade-fraction must be between 0 and 1.")
        landing_choices = tuple(
            _parse_landing(value, index) for index, value in enumerate(landing or [])
        )
        landing_fleets = _parse_landing_fleets(landing_loader, landing_processor)
        landing_truck_counts = _parse_landing_truck_counts(landing_truck)
        landing_truck_specs = (
            _load_landing_truck_specs(landing_truck_specs_path)
            if landing_truck_specs_path is not None
            else None
        )
        result = simulate_ground_system(
            scenario,
            block_id=block,
            feller_machine_id=feller,
            skidder_machine_ids=tuple(skidder),
            processor_machine_ids=tuple(processor or ()),
            processor_model=processor_model,
            processor_rate_m3_per_smh=processor_rate,
            processor_specs=(
                _load_processor_specs(processor_specs) if processor_specs is not None else None
            ),
            loader_machine_id=loader,
            landing_x_m=landing_x,
            landing_y_m=landing_y,
            landings=landing_choices,
            landing_fleets=landing_fleets,
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
            landing_truck_counts=landing_truck_counts,
            landing_truck_specs=landing_truck_specs,
            truck_load_time_s=truck_load_time,
            truck_arrival_interval_s=truck_arrival_interval,
            truck_route_distance_m=truck_route_distance,
            truck_speed_mps=truck_speed,
            mill_service_s=mill_service,
            mill_bays=mill_bays,
            landing_capacity_m3=landing_capacity,
            feller_reach_radius_m=feller_reach,
            feller_travel_speed_m_per_s=feller_speed,
            feller_processing_time_multiplier=1.0 / feller_productivity_multiplier,
            damage_downgrade_fraction=damage_downgrade_fraction,
            processor_productivity_multiplier=processor_productivity_multiplier,
            path_mode=path_mode,  # type: ignore[arg-type]
            obstacles=tuple(_parse_obstacle(value) for value in (obstacle or [])),
            stem_inventory=stem_inventory,
            skidder_specs=skidder_specs,
            loader_spec=loader_spec,
            loader_specs=loader_specs_map,
        )
        paths = None if dry_run or out is None else write_ground_system(result, out)
    except (GroundSystemError, StemModelError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    payload = result.to_dict()
    if paths is not None:
        payload["paths"] = {key: str(value) for key, value in paths.items()}
    typer.echo(json.dumps(payload, indent=2))
