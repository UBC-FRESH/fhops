"""Deterministic multi-machine ground-based harvesting simulation.

This module layers a grapple-skidder and loader queue onto the existing
single-machine tree-processing simulation. The feller-buncher still uses the
reference ADV6N10 processing time and spatial move model from
:mod:`fhops.spatial_machine`; the skidder and loader use configurable cycle
times. It is a reference execution model, not a field-calibrated system
simulation.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fhops.scenario.io import load_scenario
from fhops.spatial_machine import SpatialMachineError, simulate_block
from fhops.stem import StemInventory, build_stem_inventory

GROUND_SYSTEM_SCHEMA = "fhops.tree.ground_system.v1"
DEFAULT_BUNCH_VOLUME_M3 = 8.0
DEFAULT_FELLER_REACH_M = 12.0
DEFAULT_FELLER_TRAVEL_SPEED_MPS = 0.8
DEFAULT_SKIDDER_CAPACITY_M3 = 40.0

__all__ = [
    "DEFAULT_BUNCH_VOLUME_M3",
    "DEFAULT_FELLER_REACH_M",
    "DEFAULT_FELLER_TRAVEL_SPEED_MPS",
    "DEFAULT_SKIDDER_CAPACITY_M3",
    "GroundSystemError",
    "GroundSystemEvent",
    "GroundSystemResult",
    "GroundSystemTree",
    "MachineSpec",
    "default_loader_spec",
    "default_skidder_spec",
    "simulate_ground_system",
    "write_ground_system",
]


class GroundSystemError(RuntimeError):
    """Raised when a ground-based system simulation cannot be completed."""


@dataclass(frozen=True)
class MachineSpec:
    """Cycle-time parameters for one skidder or loader.

    Parameters
    ----------
    machine_id:
        Scenario machine identifier.
    machine_type:
        Human-readable machine type (``grapple_skidder`` or ``loader``).
    capacity_m3:
        Payload capacity in cubic metres. Only used by skidders.
    empty_speed_mps:
        Travel speed without a load, in metres per second.
    loaded_speed_mps:
        Travel speed with a load, in metres per second.
    load_fixed_s:
        Fixed loading time per bunch, seconds.
    load_per_log_s:
        Additional loading time per log, seconds.
    unload_fixed_s:
        Fixed unloading time per load, seconds.
    unload_per_log_s:
        Additional unloading time per log, seconds.
    process_fixed_s:
        Fixed loader processing time per load, seconds.
    process_per_log_s:
        Additional loader processing time per log, seconds.
    """

    machine_id: str
    machine_type: str
    capacity_m3: float = DEFAULT_SKIDDER_CAPACITY_M3
    empty_speed_mps: float = 1.4
    loaded_speed_mps: float = 1.1
    load_fixed_s: float = 45.0
    load_per_log_s: float = 5.0
    unload_fixed_s: float = 45.0
    unload_per_log_s: float = 3.0
    process_fixed_s: float = 45.0
    process_per_log_s: float = 4.0

    def __post_init__(self) -> None:
        for field, value in (
            ("capacity_m3", self.capacity_m3),
            ("empty_speed_mps", self.empty_speed_mps),
            ("loaded_speed_mps", self.loaded_speed_mps),
            ("load_fixed_s", self.load_fixed_s),
            ("load_per_log_s", self.load_per_log_s),
            ("unload_fixed_s", self.unload_fixed_s),
            ("unload_per_log_s", self.unload_per_log_s),
            ("process_fixed_s", self.process_fixed_s),
            ("process_per_log_s", self.process_per_log_s),
        ):
            if not math.isfinite(value) or value < 0:
                raise GroundSystemError(f"{field} must be finite and non-negative.")
        if self.capacity_m3 <= 0:
            raise GroundSystemError("capacity_m3 must be positive.")


def default_skidder_spec(machine_id: str) -> MachineSpec:
    """Return the default grapple-skidder specification for ``machine_id``."""
    return MachineSpec(machine_id=machine_id, machine_type="grapple_skidder")


def default_loader_spec(machine_id: str) -> MachineSpec:
    """Return the default loader specification for ``machine_id``."""
    return MachineSpec(machine_id=machine_id, machine_type="loader")


@dataclass(frozen=True)
class GroundSystemTree:
    """One tree processed by the feller-buncher."""

    tree_id: str
    x_m: float
    y_m: float
    dbh_cm: float
    merchantable_volume_m3: float
    log_count: int
    processed_s: float


@dataclass(frozen=True)
class GroundSystemEvent:
    """One machine-state segment in the system timeline."""

    machine: str
    type: str
    start_s: float
    end_s: float
    x0: float
    y0: float
    x1: float
    y1: float
    volume_m3: float = 0.0
    logs: int = 0
    tree_ids: tuple[str, ...] = ()
    status: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return the event as a JSON-serializable mapping."""
        return {
            "machine": self.machine,
            "type": self.type,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
            "volume_m3": self.volume_m3,
            "logs": self.logs,
            "tree_ids": list(self.tree_ids),
            "status": self.status,
        }


@dataclass(frozen=True)
class GroundSystemResult:
    """Result of one ground-based system on one block.

    Attributes
    ----------
    system_id:
        Deterministic identifier for the configuration and event stream.
    generated_utc:
        Generation timestamp.
    scenario_path:
        Scenario YAML.
    block_id:
        Block identifier.
    feller_machine_id:
        Feller-buncher machine identifier.
    skidder_machine_ids:
        Grapple-skidder identifiers.
    loader_machine_id:
        Loader identifier.
    landing_x_m, landing_y_m:
        Landing position in the block CRS.
    bunch_volume_m3:
        Target bunch volume.
    trees:
        Processed trees.
    events:
        Machine timeline.
    machine_summaries:
        Busy time and utilisation per machine.
    processed_volume_m3:
        Merchantable volume processed by the feller-buncher.
    tree_count:
        Processed tree count.
    unreachable_count:
        Trees refused by the feller-buncher.
    makespan_s:
        System makespan.
    warnings:
        Non-fatal observations.
    caveats:
        Model limits.
    """

    system_id: str
    generated_utc: str
    scenario_path: Path
    block_id: str
    feller_machine_id: str
    skidder_machine_ids: tuple[str, ...]
    loader_machine_id: str
    landing_x_m: float
    landing_y_m: float
    bunch_volume_m3: float
    trees: tuple[GroundSystemTree, ...]
    events: tuple[GroundSystemEvent, ...]
    machine_summaries: dict[str, dict[str, float | int]]
    processed_volume_m3: float
    tree_count: int
    unreachable_count: int
    makespan_s: float
    warnings: tuple[str, ...]
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the system manifest as a JSON-serializable mapping."""
        return {
            "schema_version": GROUND_SYSTEM_SCHEMA,
            "system_id": self.system_id,
            "generated_utc": self.generated_utc,
            "scenario_path": str(self.scenario_path),
            "block_id": self.block_id,
            "feller_machine_id": self.feller_machine_id,
            "skidder_machine_ids": list(self.skidder_machine_ids),
            "loader_machine_id": self.loader_machine_id,
            "landing": {"x": self.landing_x_m, "y": self.landing_y_m},
            "bunch_volume_m3": self.bunch_volume_m3,
            "tree_count": self.tree_count,
            "processed_volume_m3": self.processed_volume_m3,
            "unreachable_count": self.unreachable_count,
            "makespan_s": self.makespan_s,
            "machine_summaries": self.machine_summaries,
            "trees": [
                {
                    "tree_id": tree.tree_id,
                    "x": tree.x_m,
                    "y": tree.y_m,
                    "dbh_cm": tree.dbh_cm,
                    "volume_m3": tree.merchantable_volume_m3,
                    "logs": tree.log_count,
                    "processed_s": tree.processed_s,
                }
                for tree in self.trees
            ],
            "timeline": [event.to_dict() for event in self.events],
            "events": [event.to_dict() for event in self.events],
            "duration_s": self.makespan_s,
            "machines": {
                **{self.feller_machine_id: {"type": "feller_buncher"}},
                **{machine: {"type": "grapple_skidder"} for machine in self.skidder_machine_ids},
                self.loader_machine_id: {"type": "loader"},
            },
            "warnings": list(self.warnings),
            "caveats": list(self.caveats),
        }


def simulate_ground_system(
    scenario_path: str | Path,
    *,
    block_id: str,
    feller_machine_id: str,
    skidder_machine_ids: Sequence[str],
    loader_machine_id: str,
    stem_inventory: StemInventory | None = None,
    landing_x_m: float | None = None,
    landing_y_m: float | None = None,
    bunch_volume_m3: float = DEFAULT_BUNCH_VOLUME_M3,
    feller_reach_radius_m: float = DEFAULT_FELLER_REACH_M,
    feller_travel_speed_m_per_s: float = DEFAULT_FELLER_TRAVEL_SPEED_MPS,
    skidder_specs: Mapping[str, MachineSpec] | None = None,
    loader_spec: MachineSpec | None = None,
    start_x_m: float | None = None,
    start_y_m: float | None = None,
    generated_utc: str | None = None,
) -> GroundSystemResult:
    """Simulate one feller-buncher/skidder/loader system on one block.

    The feller-buncher is simulated with :func:`fhops.spatial_machine.simulate_block`.
    Its processed-tree events are grouped into bunches. Skidders are dispatched
    greedily to the earliest available bunch, and the loader processes loads in
    arrival order. The model is deterministic for the same inputs.

    Parameters
    ----------
    scenario_path:
        Scenario YAML with a tree-inventory pin.
    block_id:
        Block to simulate.
    feller_machine_id:
        Scenario machine ID for the feller-buncher.
    skidder_machine_ids:
        One or more scenario machine IDs for grapple skidders.
    loader_machine_id:
        Scenario machine ID for the loader.
    stem_inventory:
        Optional precomputed stem inventory.
    landing_x_m, landing_y_m:
        Landing position. Defaults to the mean tree position.
    bunch_volume_m3:
        Target bunch volume in cubic metres.
    feller_reach_radius_m:
        Feller-buncher reach in metres.
    feller_travel_speed_m_per_s:
        Feller-buncher travel speed.
    skidder_specs:
        Optional per-skidder cycle-time overrides.
    loader_spec:
        Optional loader cycle-time override.
    start_x_m, start_y_m:
        Feller-buncher start position.
    generated_utc:
        Generation timestamp.

    Returns
    -------
    GroundSystemResult
        Event stream, tree list, machine summaries, and totals.

    Raises
    ------
    GroundSystemError
        If inputs are invalid or the feller-buncher simulation fails.
    """
    skidders = tuple(str(machine) for machine in skidder_machine_ids)
    if not skidders:
        raise GroundSystemError("At least one skidder machine is required.")
    if len(set(skidders)) != len(skidders):
        raise GroundSystemError("Skidder machine IDs must be unique.")
    if not math.isfinite(bunch_volume_m3) or bunch_volume_m3 <= 0:
        raise GroundSystemError("bunch_volume_m3 must be positive and finite.")
    if feller_machine_id in skidders or loader_machine_id in skidders:
        raise GroundSystemError("Feller and loader machines must not also be skidders.")
    if feller_machine_id == loader_machine_id:
        raise GroundSystemError("Feller and loader machines must differ.")
    scenario_file = Path(scenario_path).expanduser().resolve()
    try:
        scenario = load_scenario(scenario_file)
    except Exception as exc:  # noqa: BLE001 - preserve dependency error text
        raise GroundSystemError(str(exc)) from exc
    machines = {machine.id: machine for machine in scenario.machines}
    requested = (feller_machine_id, *skidders, loader_machine_id)
    missing = [machine for machine in requested if machine not in machines]
    if missing:
        raise GroundSystemError("Unknown scenario machine(s): " + ", ".join(missing))
    if machines[feller_machine_id].role not in {"feller_buncher", "harvester", "hand_faller"}:
        raise GroundSystemError(
            f"Feller machine {feller_machine_id!r} has role {machines[feller_machine_id].role!r}, "
            "expected feller_buncher/harvester/hand_faller."
        )
    for machine in skidders:
        if machines[machine].role not in {"grapple_skidder", "skidder"}:
            raise GroundSystemError(
                f"Skidder {machine!r} has role {machines[machine].role!r}, expected grapple_skidder/skidder."
            )
    if machines[loader_machine_id].role != "loader":
        raise GroundSystemError(
            f"Loader {loader_machine_id!r} has role {machines[loader_machine_id].role!r}, expected loader."
        )
    stems = stem_inventory
    if stems is None:
        try:
            stems = build_stem_inventory(scenario_file)
        except Exception as exc:  # noqa: BLE001 - preserve dependency error text
            raise GroundSystemError(str(exc)) from exc
    try:
        fb_sim = simulate_block(
            scenario_file,
            block_id=block_id,
            machine_id=feller_machine_id,
            stem_inventory=stems,
            start_x_m=start_x_m,
            start_y_m=start_y_m,
            reach_radius_m=feller_reach_radius_m,
            travel_speed_m_per_s=feller_travel_speed_m_per_s,
        )
    except SpatialMachineError as exc:
        raise GroundSystemError(str(exc)) from exc
    trees_by_id = {tree.tree_id: tree for tree in stems.trees if tree.block_id == block_id}
    processed_events = [event for event in fb_sim.events if event.status == "processed"]
    if not processed_events:
        raise GroundSystemError(f"Block {block_id!r} produced no processed trees.")
    if landing_x_m is None or landing_y_m is None:
        landing_x = sum(tree.x_m for tree in processed_events) / len(processed_events)
        landing_y = sum(tree.y_m for tree in processed_events) / len(processed_events)
    else:
        landing_x, landing_y = landing_x_m, landing_y_m
    if not all(math.isfinite(value) for value in (landing_x, landing_y)):
        raise GroundSystemError("Landing position must be finite.")
    skidder_specs = dict(skidder_specs or {})
    for machine in skidders:
        skidder_specs.setdefault(machine, default_skidder_spec(machine))
        if skidder_specs[machine].machine_id != machine:
            raise GroundSystemError(
                f"Skidder spec ID {skidder_specs[machine].machine_id!r} does not match {machine!r}."
            )
    loader = loader_spec or default_loader_spec(loader_machine_id)
    if loader.machine_id != loader_machine_id:
        raise GroundSystemError("Loader spec ID does not match loader_machine_id.")
    events: list[GroundSystemEvent] = []
    trees: list[GroundSystemTree] = []
    previous_x = fb_sim.start_x_m
    previous_y = fb_sim.start_y_m
    for event in processed_events:
        travel_start = event.start_s
        travel_end = event.start_s + event.move_time_s
        if event.move_time_s > 0:
            events.append(
                GroundSystemEvent(
                    machine=feller_machine_id,
                    type="travel",
                    start_s=travel_start,
                    end_s=travel_end,
                    x0=previous_x,
                    y0=previous_y,
                    x1=event.machine_x_m,
                    y1=event.machine_y_m,
                    status="empty",
                )
            )
        events.append(
            GroundSystemEvent(
                machine=feller_machine_id,
                type="process",
                start_s=travel_end,
                end_s=event.end_s,
                x0=event.machine_x_m,
                y0=event.machine_y_m,
                x1=event.machine_x_m,
                y1=event.machine_y_m,
                volume_m3=event.merchantable_volume_m3,
                logs=event.log_count,
                tree_ids=(event.tree_id,),
                status="processing",
            )
        )
        previous_x, previous_y = event.machine_x_m, event.machine_y_m
        trees.append(
            GroundSystemTree(
                tree_id=event.tree_id,
                x_m=event.x_m,
                y_m=event.y_m,
                dbh_cm=trees_by_id[event.tree_id].dbh_cm,
                merchantable_volume_m3=event.merchantable_volume_m3,
                log_count=event.log_count,
                processed_s=event.end_s,
            )
        )
    max_bunch_volume_m3 = min(spec.capacity_m3 for spec in skidder_specs.values())
    if bunch_volume_m3 > max_bunch_volume_m3 + 1e-9:
        raise GroundSystemError(
            f"bunch_volume_m3 ({bunch_volume_m3:.2f}) exceeds the smallest skidder capacity "
            f"({max_bunch_volume_m3:.2f} m3)."
        )
    bunches = _build_bunches(trees, bunch_volume_m3, max_bunch_volume_m3)
    loads = _simulate_skidders(events, bunches, skidders, skidder_specs, landing_x, landing_y)
    loader_total = _simulate_loader(events, loads, loader, landing_x, landing_y)
    fb_total = fb_sim.total_time_s
    skidder_total = max((load.ready_s for load in loads), default=0.0)
    makespan = max(fb_total, skidder_total, loader_total)
    summaries: dict[str, dict[str, float | int]] = {}
    for machine in (feller_machine_id, *skidders, loader_machine_id):
        machine_events = [event for event in events if event.machine == machine]
        busy = sum(event.end_s - event.start_s for event in machine_events)
        summaries[machine] = {
            "busy_s": busy,
            "events": len(machine_events),
            "utilisation": busy / makespan if makespan > 0 else 0.0,
        }
    material = {
        "block_id": block_id,
        "feller": feller_machine_id,
        "skidders": skidders,
        "loader": loader_machine_id,
        "bunch_volume_m3": bunch_volume_m3,
        "events": [event.to_dict() for event in events],
    }
    system_id = (
        "fhops-tree-system-"
        + hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
    )
    timestamp = generated_utc or datetime.now(UTC).isoformat()
    events.sort(key=lambda event: (event.start_s, event.end_s, event.machine, event.type))
    warnings: list[str] = []
    if fb_sim.unreachable_count:
        warnings.append(
            f"{fb_sim.unreachable_count} tree(s) were unreachable by the feller-buncher."
        )
    warnings.extend(fb_sim.warnings)
    return GroundSystemResult(
        system_id=system_id,
        generated_utc=timestamp,
        scenario_path=scenario_file,
        block_id=block_id,
        feller_machine_id=feller_machine_id,
        skidder_machine_ids=skidders,
        loader_machine_id=loader_machine_id,
        landing_x_m=landing_x,
        landing_y_m=landing_y,
        bunch_volume_m3=bunch_volume_m3,
        trees=tuple(trees),
        events=tuple(events),
        machine_summaries=summaries,
        processed_volume_m3=sum(tree.merchantable_volume_m3 for tree in trees),
        tree_count=len(trees),
        unreachable_count=fb_sim.unreachable_count,
        makespan_s=makespan,
        warnings=tuple(warnings),
        caveats=(
            "Reference multi-machine event model, not a field-calibrated system simulation.",
            "Feller-buncher processing uses the existing reference spatial/ADV6N10 model.",
            "Skidder and loader cycle times are configurable defaults; queue dispatch is greedy and deterministic.",
            "Flat terrain and a single landing are assumed; road and DEM routing are not modelled.",
            "Tree lists must be reviewed separately; this module does not validate stem-model calibration.",
        ),
    )


@dataclass(frozen=True)
class _Bunch:
    bunch_id: str
    tree_ids: tuple[str, ...]
    volume_m3: float
    logs: int
    ready_s: float
    x: float
    y: float


@dataclass(frozen=True)
class _Load:
    load_id: str
    bunch_id: str
    skidder_id: str
    volume_m3: float
    logs: int
    ready_s: float
    tree_ids: tuple[str, ...]


def _build_bunches(
    trees: list[GroundSystemTree],
    target_volume_m3: float,
    max_volume_m3: float,
) -> list[_Bunch]:
    bunches: list[_Bunch] = []
    current: list[GroundSystemTree] = []
    volume = 0.0

    def flush() -> None:
        nonlocal current, volume
        if not current:
            return
        last = current[-1]
        bunches.append(
            _Bunch(
                bunch_id=f"B{len(bunches) + 1:05d}",
                tree_ids=tuple(item.tree_id for item in current),
                volume_m3=volume,
                logs=sum(item.log_count for item in current),
                ready_s=last.processed_s,
                x=last.x_m,
                y=last.y_m,
            )
        )
        current = []
        volume = 0.0

    for tree in trees:
        if tree.merchantable_volume_m3 > max_volume_m3 + 1e-9:
            raise GroundSystemError(
                f"Tree {tree.tree_id!r} ({tree.merchantable_volume_m3:.2f} m3) exceeds "
                f"skidder capacity ({max_volume_m3:.2f} m3)."
            )
        if current and volume + tree.merchantable_volume_m3 > max_volume_m3:
            flush()
        current.append(tree)
        volume += tree.merchantable_volume_m3
        if volume >= target_volume_m3:
            flush()
    flush()
    return bunches


def _simulate_skidders(
    events: list[GroundSystemEvent],
    bunches: list[_Bunch],
    skidder_ids: tuple[str, ...],
    specs: Mapping[str, MachineSpec],
    landing_x: float,
    landing_y: float,
) -> list[_Load]:
    loads: list[_Load] = []
    available = {machine: 0.0 for machine in skidder_ids}
    for bunch in bunches:
        machine = min(skidder_ids, key=lambda item: available[item])
        spec = specs[machine]
        if bunch.volume_m3 > spec.capacity_m3 + 1e-9:
            raise GroundSystemError(
                f"Bunch {bunch.bunch_id} ({bunch.volume_m3:.2f} m3) exceeds "
                f"{machine} capacity ({spec.capacity_m3:.2f} m3)."
            )
        start = available[machine]
        bx, by = bunch.x, bunch.y
        distance = math.hypot(bx - landing_x, by - landing_y)
        empty_start = start
        empty_end = empty_start + distance / spec.empty_speed_mps
        events.append(
            GroundSystemEvent(
                machine=machine,
                type="travel_empty",
                start_s=empty_start,
                end_s=empty_end,
                x0=landing_x,
                y0=landing_y,
                x1=bx,
                y1=by,
                status="empty",
            )
        )
        load_start = max(empty_end, bunch.ready_s)
        load_end = load_start + spec.load_fixed_s + spec.load_per_log_s * bunch.logs
        events.append(
            GroundSystemEvent(
                machine=machine,
                type="load",
                start_s=load_start,
                end_s=load_end,
                x0=bx,
                y0=by,
                x1=bx,
                y1=by,
                volume_m3=bunch.volume_m3,
                logs=bunch.logs,
                tree_ids=bunch.tree_ids,
                status="loading",
            )
        )
        loaded_end = load_end + distance / spec.loaded_speed_mps
        events.append(
            GroundSystemEvent(
                machine=machine,
                type="travel_loaded",
                start_s=load_end,
                end_s=loaded_end,
                x0=bx,
                y0=by,
                x1=landing_x,
                y1=landing_y,
                volume_m3=bunch.volume_m3,
                logs=bunch.logs,
                status="loaded",
            )
        )
        unload_end = loaded_end + spec.unload_fixed_s + spec.unload_per_log_s * bunch.logs
        events.append(
            GroundSystemEvent(
                machine=machine,
                type="unload",
                start_s=loaded_end,
                end_s=unload_end,
                x0=landing_x,
                y0=landing_y,
                x1=landing_x,
                y1=landing_y,
                volume_m3=bunch.volume_m3,
                logs=bunch.logs,
                status="unloading",
            )
        )
        available[machine] = unload_end
        loads.append(
            _Load(
                load_id=f"L{len(loads) + 1:05d}",
                bunch_id=bunch.bunch_id,
                skidder_id=machine,
                volume_m3=bunch.volume_m3,
                logs=bunch.logs,
                ready_s=unload_end,
                tree_ids=bunch.tree_ids,
            )
        )
    return loads


def _simulate_loader(
    events: list[GroundSystemEvent],
    loads: list[_Load],
    spec: MachineSpec,
    landing_x: float,
    landing_y: float,
) -> float:
    available = 0.0
    for load in sorted(loads, key=lambda item: (item.ready_s, item.load_id)):
        start = max(available, load.ready_s)
        end = start + spec.process_fixed_s + spec.process_per_log_s * load.logs
        events.append(
            GroundSystemEvent(
                machine=spec.machine_id,
                type="process",
                start_s=start,
                end_s=end,
                x0=landing_x,
                y0=landing_y,
                x1=landing_x,
                y1=landing_y,
                volume_m3=load.volume_m3,
                logs=load.logs,
                tree_ids=load.tree_ids,
                status="processing",
            )
        )
        available = end
    return available


def write_ground_system(result: GroundSystemResult, out_dir: Path) -> dict[str, Path]:
    """Write ground-system events, trees, and the summary manifest.

    Parameters
    ----------
    result:
        Ground-system result.
    out_dir:
        Output directory.

    Returns
    -------
    dict[str, Path]
        Paths keyed by ``events_csv``, ``events_json``, ``trees_csv``, and
        ``manifest``.
    """
    output = out_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    events_csv = output / "system_events.csv"
    with events_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "machine",
                "type",
                "start_s",
                "end_s",
                "x0",
                "y0",
                "x1",
                "y1",
                "volume_m3",
                "logs",
                "tree_ids",
                "status",
            )
        )
        for event in result.events:
            writer.writerow(
                (
                    event.machine,
                    event.type,
                    event.start_s,
                    event.end_s,
                    event.x0,
                    event.y0,
                    event.x1,
                    event.y1,
                    event.volume_m3,
                    event.logs,
                    ";".join(event.tree_ids),
                    event.status,
                )
            )
    trees_csv = output / "tree_processing.csv"
    with trees_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "tree_id",
                "x_m",
                "y_m",
                "dbh_cm",
                "merchantable_volume_m3",
                "log_count",
                "processed_s",
            )
        )
        for tree in result.trees:
            writer.writerow(
                (
                    tree.tree_id,
                    tree.x_m,
                    tree.y_m,
                    tree.dbh_cm,
                    tree.merchantable_volume_m3,
                    tree.log_count,
                    tree.processed_s,
                )
            )
    events_json = output / "system_events.json"
    events_json.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = output / "system_summary.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": GROUND_SYSTEM_SCHEMA,
                "system_id": result.system_id,
                "block_id": result.block_id,
                "tree_count": result.tree_count,
                "processed_volume_m3": result.processed_volume_m3,
                "unreachable_count": result.unreachable_count,
                "makespan_s": result.makespan_s,
                "machine_summaries": result.machine_summaries,
                "warnings": list(result.warnings),
                "caveats": list(result.caveats),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "events_csv": events_csv,
        "events_json": events_json,
        "trees_csv": trees_csv,
        "manifest": manifest,
    }
