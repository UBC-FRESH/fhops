"""Single-machine spatial tree-processing simulation for tree-scale FHOPS.

The simulator is a deterministic reference execution layer. It moves one
machine through a block, selects trees using an explicit reach radius, rejects
trees blocked by terrain or optional circular obstacles, and uses the reference
stem model plus the existing ADV6N10 harvester regression for processing time.
It is not a field-calibrated machine-routing or physics model.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fhops.productivity.harvester_ctl import (
    ADV6N10HarvesterInputs,
    estimate_harvester_productivity_adv6n10,
)
from fhops.scenario.io import load_scenario
from fhops.stem import StemInventory, StemModelError, StemResult, build_stem_inventory

SPATIAL_SIM_SCHEMA = "fhops.tree.machine_sim.v1"
DEFAULT_REACH_RADIUS_M = 10.0
DEFAULT_TRAVEL_SPEED_M_PER_S = 0.5
DEFAULT_MAX_SLOPE_PERCENT = 35.0

__all__ = [
    "DEFAULT_MAX_SLOPE_PERCENT",
    "DEFAULT_REACH_RADIUS_M",
    "DEFAULT_TRAVEL_SPEED_M_PER_S",
    "Obstacle",
    "SpatialEvent",
    "SpatialMachineError",
    "SpatialSimulation",
    "simulate_block",
    "write_spatial_simulation",
]


class SpatialMachineError(RuntimeError):
    """Raised when a single-machine simulation cannot be completed."""


@dataclass(frozen=True)
class Obstacle:
    """Circular obstacle in the block CRS.

    Attributes
    ----------
    x_m : float
        Easting in metres.
    y_m : float
        Northing in metres.
    radius_m : float
        Exclusion radius in metres.
    """

    x_m: float
    y_m: float
    radius_m: float

    def contains(self, x_m: float, y_m: float) -> bool:
        """Return whether a point lies inside the exclusion circle."""
        return math.hypot(x_m - self.x_m, y_m - self.y_m) <= self.radius_m


@dataclass(frozen=True)
class SpatialEvent:
    """One tree visit in a single-machine simulation.

    Attributes
    ----------
    sequence : int
        One-based visit order.
    tree_id : str
        Tree identifier.
    block_id : str
        Block identifier.
    status : str
        ``processed`` or ``unreachable``.
    reason : str | None
        Refusal reason for unreachable trees.
    x_m : float
        Tree easting.
    y_m : float
        Tree northing.
    machine_x_m : float
        Machine position after any move.
    machine_y_m : float
        Machine position after any move.
    distance_m : float
        Travel distance to the processing position.
    slope_percent : float
        Absolute terrain slope between the previous and target positions.
    move_time_s : float
        Travel time.
    processing_time_s : float
        Processing time.
    start_s : float
        Event start in seconds.
    end_s : float
        Event end in seconds.
    cumulative_s : float
        Elapsed time after the event.
    merchantable_volume_m3 : float
        Processed merchantable volume.
    log_count : int
        Number of logs.
    """

    sequence: int
    tree_id: str
    block_id: str
    status: str
    reason: str | None
    x_m: float
    y_m: float
    machine_x_m: float
    machine_y_m: float
    distance_m: float
    slope_percent: float
    move_time_s: float
    processing_time_s: float
    start_s: float
    end_s: float
    cumulative_s: float
    merchantable_volume_m3: float
    log_count: int

    def to_dict(self) -> dict[str, object]:
        """Return the event as a JSON-serializable mapping."""
        return {
            "sequence": self.sequence,
            "tree_id": self.tree_id,
            "block_id": self.block_id,
            "status": self.status,
            "reason": self.reason,
            "x_m": self.x_m,
            "y_m": self.y_m,
            "machine_x_m": self.machine_x_m,
            "machine_y_m": self.machine_y_m,
            "distance_m": self.distance_m,
            "slope_percent": self.slope_percent,
            "move_time_s": self.move_time_s,
            "processing_time_s": self.processing_time_s,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "cumulative_s": self.cumulative_s,
            "merchantable_volume_m3": self.merchantable_volume_m3,
            "log_count": self.log_count,
        }


@dataclass(frozen=True)
class SpatialSimulation:
    """Result of one machine on one block.

    Attributes
    ----------
    simulation_id : str
        Deterministic simulation identifier.
    generated_utc : str
        Generation timestamp.
    scenario_path : Path
        Scenario YAML.
    block_id : str
        Block identifier.
    machine_id : str
        Machine identifier.
    start_x_m : float
        Machine starting easting.
    start_y_m : float
        Machine starting northing.
    start_z_m : float
        Machine starting elevation.
    reach_radius_m : float
        Processing reach.
    travel_speed_m_per_s : float
        Travel speed.
    max_slope_percent : float
        Terrain slope limit.
    events : tuple[SpatialEvent, ...]
        Visit and unreachable events.
    processed_count : int
        Processed tree count.
    unreachable_count : int
        Unreachable tree count.
    total_distance_m : float
        Total travel distance.
    travel_time_s : float
        Total travel time.
    processing_time_s : float
        Total processing time.
    total_time_s : float
        Total elapsed time.
    merchantable_volume_m3 : float
        Processed merchantable volume.
    gross_volume_m3 : float
        Processed gross volume.
    work_required_m3 : float | None
        Scenario terminal volume.
    volume_status : str
        ``ok``, ``warning``, or ``unknown``.
    volume_difference_fraction : float | None
        Relative difference from ``work_required``.
    warnings : tuple[str, ...]
        Non-fatal observations.
    caveats : tuple[str, ...]
        Simulation-only caveats.
    """

    simulation_id: str
    generated_utc: str
    scenario_path: Path
    block_id: str
    machine_id: str
    start_x_m: float
    start_y_m: float
    start_z_m: float
    reach_radius_m: float
    travel_speed_m_per_s: float
    max_slope_percent: float
    events: tuple[SpatialEvent, ...]
    processed_count: int
    unreachable_count: int
    total_distance_m: float
    travel_time_s: float
    processing_time_s: float
    total_time_s: float
    merchantable_volume_m3: float
    gross_volume_m3: float
    work_required_m3: float | None
    volume_status: str
    volume_difference_fraction: float | None
    warnings: tuple[str, ...]
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the simulation manifest as a JSON-serializable mapping."""
        return {
            "schema_version": SPATIAL_SIM_SCHEMA,
            "simulation_id": self.simulation_id,
            "generated_utc": self.generated_utc,
            "scenario_path": str(self.scenario_path),
            "block_id": self.block_id,
            "machine_id": self.machine_id,
            "start": {"x_m": self.start_x_m, "y_m": self.start_y_m, "z_m": self.start_z_m},
            "reach_radius_m": self.reach_radius_m,
            "travel_speed_m_per_s": self.travel_speed_m_per_s,
            "max_slope_percent": self.max_slope_percent,
            "processed_count": self.processed_count,
            "unreachable_count": self.unreachable_count,
            "total_distance_m": self.total_distance_m,
            "travel_time_s": self.travel_time_s,
            "processing_time_s": self.processing_time_s,
            "total_time_s": self.total_time_s,
            "merchantable_volume_m3": self.merchantable_volume_m3,
            "gross_volume_m3": self.gross_volume_m3,
            "work_required_m3": self.work_required_m3,
            "volume_status": self.volume_status,
            "volume_difference_fraction": self.volume_difference_fraction,
            "events": [event.to_dict() for event in self.events],
            "warnings": list(self.warnings),
            "caveats": list(self.caveats),
        }


def simulate_block(
    scenario_path: str | Path,
    *,
    block_id: str,
    machine_id: str,
    stem_inventory: StemInventory | None = None,
    tree_ids: set[str] | None = None,
    start_x_m: float | None = None,
    start_y_m: float | None = None,
    start_z_m: float | None = None,
    reach_radius_m: float = DEFAULT_REACH_RADIUS_M,
    travel_speed_m_per_s: float = DEFAULT_TRAVEL_SPEED_M_PER_S,
    max_slope_percent: float = DEFAULT_MAX_SLOPE_PERCENT,
    processing_time_multiplier: float = 1.0,
    path_mode: Literal["nearest", "swath"] = "nearest",
    swath_band_height_m: float | None = None,
    max_total_time_s: float | None = None,
    target_merchantable_volume_m3: float | None = None,
    obstacles: tuple[Obstacle, ...] = (),
    generated_utc: str | None = None,
) -> SpatialSimulation:
    """Simulate one machine processing trees in one block.

    The machine starts at ``start_x_m``/``start_y_m`` when supplied; otherwise it
    starts at the first tree in the block. When no tree is within reach, it moves
    to a point within reach of the nearest feasible tree. Trees blocked by a
    circular obstacle or a slope above ``max_slope_percent`` are recorded as
    unreachable.

    Parameters
    ----------
    scenario_path : str | Path
        Scenario YAML with a tree-inventory pin.
    block_id : str
        Block to simulate.
    machine_id : str
        Scenario machine identifier.
    stem_inventory : StemInventory | None, optional
        Precomputed stem inventory. Defaults to building one.
    tree_ids : set[str] | None, optional
        Restrict the simulation to these tree identifiers.
    start_x_m, start_y_m, start_z_m : float | None, optional
        Starting position. Defaults to the first tree.
    reach_radius_m : float, optional
        Processing reach.
    travel_speed_m_per_s : float, optional
        Travel speed.
    max_slope_percent : float, optional
        Maximum absolute terrain slope.
    processing_time_multiplier : float, optional
        Multiplier on each tree processing time. Values above one model slower
        harvester work (for example selection-cut care); values below one model
        faster work. Travel time is unaffected.
    path_mode : {"nearest", "swath"}, optional
        ``swath`` uses boustrophedon bands for a contiguous harvest pattern;
        ``nearest`` preserves the original nearest-tree behavior.
    swath_band_height_m : float | None, optional
        Height of the boustrophedon harvest bands. Defaults to twice the reach
        radius when ``path_mode="swath"``.
    max_total_time_s : float | None, optional
        Stop after this elapsed time unless no tree has been processed yet.
    target_merchantable_volume_m3 : float | None, optional
        Stop after this merchantable volume has been processed.
    obstacles : tuple[Obstacle, ...], optional
        Circular exclusion zones.
    generated_utc : str | None, optional
        Generation timestamp.

    Returns
    -------
    SpatialSimulation
        Deterministic events and totals.

    Raises
    ------
    SpatialMachineError
        If the block/machine is unknown, the block has no trees, or input
        parameters are invalid.
    """
    for field, value in (
        ("reach_radius_m", reach_radius_m),
        ("travel_speed_m_per_s", travel_speed_m_per_s),
        ("max_slope_percent", max_slope_percent),
        ("processing_time_multiplier", processing_time_multiplier),
    ):
        if not math.isfinite(value) or value <= 0:
            raise SpatialMachineError(f"{field} must be positive and finite.")
    for field, optional_value in (
        ("max_total_time_s", max_total_time_s),
        ("target_merchantable_volume_m3", target_merchantable_volume_m3),
    ):
        if optional_value is not None and (
            not math.isfinite(optional_value) or optional_value <= 0
        ):
            raise SpatialMachineError(f"{field} must be positive and finite when supplied.")
    scenario_file = Path(scenario_path).expanduser().resolve()
    try:
        scenario = load_scenario(scenario_file)
        stems = stem_inventory or build_stem_inventory(scenario_file)
    except (StemModelError, ValueError, FileNotFoundError) as exc:
        raise SpatialMachineError(str(exc)) from exc
    if block_id not in set(scenario.block_ids()):
        raise SpatialMachineError(f"Unknown block {block_id!r}.")
    if machine_id not in set(scenario.machine_ids()):
        raise SpatialMachineError(f"Unknown machine {machine_id!r}.")
    block = next(item for item in scenario.blocks if item.id == block_id)
    trees = [tree for tree in stems.trees if tree.block_id == block_id]
    if tree_ids is not None:
        trees = [tree for tree in trees if tree.tree_id in tree_ids]
    if not trees:
        raise SpatialMachineError(f"Block {block_id!r} has no tree records.")
    if path_mode not in {"nearest", "swath"}:
        raise SpatialMachineError("path_mode must be 'nearest' or 'swath'.")
    ordered_trees = (
        _swath_order(
            trees,
            band_height_m=(
                swath_band_height_m
                if swath_band_height_m is not None
                else max(2.0 * reach_radius_m, 5.0)
            ),
        )
        if path_mode == "swath"
        else trees
    )
    first = ordered_trees[0]
    sx = first.x_m if start_x_m is None else start_x_m
    sy = first.y_m if start_y_m is None else start_y_m
    sz = first.elevation_m if start_z_m is None else start_z_m
    if sz is None:
        sz = 0.0
    if not all(math.isfinite(value) for value in (sx, sy, sz)):
        raise SpatialMachineError("Starting position must be finite.")
    events = _simulate_events(
        ordered_trees,
        start=(sx, sy, sz),
        path_mode=path_mode,
        reach_radius_m=reach_radius_m,
        travel_speed_m_per_s=travel_speed_m_per_s,
        max_slope_percent=max_slope_percent,
        processing_time_multiplier=processing_time_multiplier,
        max_total_time_s=max_total_time_s,
        target_merchantable_volume_m3=target_merchantable_volume_m3,
        obstacles=obstacles,
    )
    processed = [event for event in events if event.status == "processed"]
    unreachable = [event for event in events if event.status == "unreachable"]
    merchantable = sum(event.merchantable_volume_m3 for event in processed)
    gross = sum(
        tree.gross_volume_m3
        for tree in trees
        if tree.tree_id in {event.tree_id for event in processed}
    )
    work_required = block.work_required if block.work_required > 0 else None
    volume_status, difference = _volume_status(merchantable, work_required)
    warnings: list[str] = []
    if volume_status == "warning":
        warnings.append("Processed merchantable volume differs from work_required.")
    if volume_status == "unknown":
        warnings.append("work_required is unavailable; volume reconciliation skipped.")
    if unreachable:
        warnings.append(f"{len(unreachable)} tree(s) could not be processed.")
    timestamp = generated_utc or datetime.now(UTC).isoformat()
    material = {
        "block_id": block_id,
        "machine_id": machine_id,
        "start": [sx, sy, sz],
        "reach_radius_m": reach_radius_m,
        "events": [event.to_dict() for event in events],
    }
    simulation_id = (
        "fhops-tree-machine-"
        + hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
    )
    return SpatialSimulation(
        simulation_id=simulation_id,
        generated_utc=timestamp,
        scenario_path=scenario_file,
        block_id=block_id,
        machine_id=machine_id,
        start_x_m=sx,
        start_y_m=sy,
        start_z_m=sz,
        reach_radius_m=reach_radius_m,
        travel_speed_m_per_s=travel_speed_m_per_s,
        max_slope_percent=max_slope_percent,
        events=tuple(events),
        processed_count=len(processed),
        unreachable_count=len(unreachable),
        total_distance_m=sum(event.distance_m for event in events),
        travel_time_s=sum(event.move_time_s for event in events),
        processing_time_s=sum(event.processing_time_s for event in events),
        total_time_s=events[-1].cumulative_s if events else 0.0,
        merchantable_volume_m3=merchantable,
        gross_volume_m3=gross,
        work_required_m3=work_required,
        volume_status=volume_status,
        volume_difference_fraction=difference,
        warnings=tuple(warnings),
        caveats=(
            "Reference single-machine simulation, not a field-calibrated routing or physics model.",
            "Processing time uses the ADV6N10 harvester regression; travel is a constant-speed approximation.",
            *stems.caveats,
        ),
    )


def write_spatial_simulation(simulation: SpatialSimulation, out_dir: Path) -> dict[str, Path]:
    """Write machine events and the simulation manifest.

    Parameters
    ----------
    simulation : SpatialSimulation
        Simulation result.
    out_dir : Path
        Output directory.

    Returns
    -------
    dict[str, Path]
        Paths keyed by ``events`` and ``manifest``.
    """
    output = out_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    events_path = output / "tree_machine_events.csv"
    columns = (
        "sequence",
        "tree_id",
        "block_id",
        "status",
        "reason",
        "x_m",
        "y_m",
        "machine_x_m",
        "machine_y_m",
        "distance_m",
        "slope_percent",
        "move_time_s",
        "processing_time_s",
        "start_s",
        "end_s",
        "cumulative_s",
        "merchantable_volume_m3",
        "log_count",
    )
    with events_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(event.to_dict() for event in simulation.events)
    manifest_path = output / "tree_machine_simulation.json"
    manifest_path.write_text(
        json.dumps(simulation.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"events": events_path, "manifest": manifest_path}


def _swath_order(
    trees: list[StemResult],
    *,
    band_height_m: float,
) -> list[StemResult]:
    """Order trees into alternating rows for a visible, contiguous harvest sweep."""
    if not trees:
        return []
    min_y = min(tree.y_m for tree in trees)
    rows: dict[int, list[StemResult]] = {}
    for tree in trees:
        band = int(math.floor((tree.y_m - min_y) / band_height_m))
        rows.setdefault(band, []).append(tree)
    ordered: list[StemResult] = []
    for index, (_, band_trees) in enumerate(sorted(rows.items())):
        band_trees.sort(key=lambda tree: (tree.x_m, tree.y_m))
        if index % 2:
            band_trees.reverse()
        ordered.extend(band_trees)
    return ordered


def _simulate_events(
    trees: list[StemResult],
    *,
    start: tuple[float, float, float],
    path_mode: Literal["nearest", "swath"] = "nearest",
    reach_radius_m: float,
    travel_speed_m_per_s: float,
    max_slope_percent: float,
    processing_time_multiplier: float,
    max_total_time_s: float | None,
    target_merchantable_volume_m3: float | None,
    obstacles: tuple[Obstacle, ...],
) -> list[SpatialEvent]:
    remaining = {tree.tree_id: tree for tree in trees}
    current_x, current_y, current_z = start
    elapsed = 0.0
    events: list[SpatialEvent] = []
    processed_volume = 0.0
    sequence = 1
    while remaining:
        if max_total_time_s is not None and events and elapsed >= max_total_time_s:
            break
        if (
            target_merchantable_volume_m3 is not None
            and processed_volume >= target_merchantable_volume_m3
        ):
            break

        def feasible(tree: StemResult) -> tuple[bool, str | None]:
            x = tree.x_m
            y = tree.y_m
            if any(obstacle.contains(x, y) for obstacle in obstacles):
                return False, "tree lies inside an obstacle"
            terrain_z = tree.elevation_m if tree.elevation_m is not None else current_z
            horizontal = math.hypot(x - current_x, y - current_y)
            slope = abs(terrain_z - current_z) / horizontal * 100.0 if horizontal > 0 else 0.0
            if slope > max_slope_percent:
                return False, f"terrain slope {slope:.2f}% exceeds the limit"
            return True, None

        def distance(tree: StemResult) -> float:
            return math.hypot(tree.x_m - current_x, tree.y_m - current_y)

        target: StemResult | None = None
        if path_mode == "swath":
            for tree in trees:
                if tree.tree_id not in remaining:
                    continue
                ok, _reason = feasible(tree)
                if ok:
                    target = tree
                    break
        else:
            within = [tree for tree in remaining.values() if distance(tree) <= reach_radius_m]
            for tree in sorted(within, key=lambda item: (distance(item), item.tree_id)):
                ok, _reason = feasible(tree)
                if ok:
                    target = tree
                    break
            if target is None:
                for tree in sorted(
                    remaining.values(), key=lambda item: (distance(item), item.tree_id)
                ):
                    ok, _reason = feasible(tree)
                    if ok:
                        target = tree
                        break
        if target is None:
            for tree in sorted(remaining.values(), key=lambda item: (distance(item), item.tree_id)):
                _ok, reason = feasible(tree)
                events.append(
                    SpatialEvent(
                        sequence=sequence,
                        tree_id=tree.tree_id,
                        block_id=tree.block_id,
                        status="unreachable",
                        reason=reason or "no feasible approach found",
                        x_m=tree.x_m,
                        y_m=tree.y_m,
                        machine_x_m=current_x,
                        machine_y_m=current_y,
                        distance_m=0.0,
                        slope_percent=0.0,
                        move_time_s=0.0,
                        processing_time_s=0.0,
                        start_s=elapsed,
                        end_s=elapsed,
                        cumulative_s=elapsed,
                        merchantable_volume_m3=0.0,
                        log_count=0,
                    )
                )
                sequence += 1
                remaining.pop(tree.tree_id)
            break
        target_distance = distance(target)
        approach_x = current_x
        approach_y = current_y
        move_distance = 0.0
        if target_distance > reach_radius_m:
            scale = max(0.0, (target_distance - reach_radius_m * 0.9) / target_distance)
            approach_x = current_x + (target.x_m - current_x) * scale
            approach_y = current_y + (target.y_m - current_y) * scale
            move_distance = math.hypot(approach_x - current_x, approach_y - current_y)
        terrain_z = target.elevation_m if target.elevation_m is not None else current_z
        horizontal = math.hypot(target.x_m - current_x, target.y_m - current_y)
        slope = abs(terrain_z - current_z) / horizontal * 100.0 if horizontal > 0 else 0.0
        move_time = move_distance / travel_speed_m_per_s
        processing_time = _processing_time(target) * processing_time_multiplier
        start_s = elapsed
        elapsed += move_time + processing_time
        events.append(
            SpatialEvent(
                sequence=sequence,
                tree_id=target.tree_id,
                block_id=target.block_id,
                status="processed",
                reason=None,
                x_m=target.x_m,
                y_m=target.y_m,
                machine_x_m=approach_x,
                machine_y_m=approach_y,
                distance_m=move_distance,
                slope_percent=slope,
                move_time_s=move_time,
                processing_time_s=processing_time,
                start_s=start_s,
                end_s=elapsed,
                cumulative_s=elapsed,
                merchantable_volume_m3=target.merchantable_volume_m3,
                log_count=len(target.logs),
            )
        )
        current_x, current_y, current_z = approach_x, approach_y, terrain_z
        processed_volume += target.merchantable_volume_m3
        remaining.pop(target.tree_id)
        sequence += 1
    return events


def _processing_time(tree: StemResult) -> float:
    if tree.merchantable_volume_m3 <= 0:
        return 0.0
    # Felling handles the whole tree. Bucking length belongs to the processor,
    # not to feller-buncher productivity.
    inputs = ADV6N10HarvesterInputs(
        stem_volume_m3=tree.merchantable_volume_m3,
        products_count=1.0,
        stems_per_cycle=1.0,
        mean_log_length_m=max(tree.height_m, 1e-9),
    )
    productivity = estimate_harvester_productivity_adv6n10(inputs)
    return tree.merchantable_volume_m3 / productivity * 3600.0


def _volume_status(observed: float, expected: float | None) -> tuple[str, float | None]:
    if expected is None or expected <= 0:
        return "unknown", None
    difference = (observed - expected) / expected
    return ("ok" if abs(difference) <= 0.25 else "warning"), difference
