"""Replay an existing FHOPS schedule at tree scale.

The replay is a one-schedule execution check. It reads machine/block/day rows,
drives the single-machine spatial simulator, consumes trees deterministically,
and reports scheduled-versus-simulated differences. It never rewrites the
schedule or the scenario.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fhops.scenario.contract import Scenario
from fhops.scenario.io import load_scenario
from fhops.scheduling.systems.models import default_system_registry
from fhops.spatial_machine import (
    Obstacle,
    SpatialEvent,
    SpatialMachineError,
    simulate_block,
)
from fhops.stem import StemInventory, StemModelError, build_stem_inventory

TREE_REPLAY_SCHEMA = "fhops.tree.replay.v1"
DEFAULT_REPLAY_TOLERANCE = 0.1

__all__ = [
    "DEFAULT_REPLAY_TOLERANCE",
    "ReplayAssignment",
    "ReplayBlockSummary",
    "TreeReplay",
    "TreeReplayError",
    "replay_tree_schedule",
    "write_tree_replay",
]


class TreeReplayError(RuntimeError):
    """Raised when a schedule cannot be replayed at tree scale."""


@dataclass(frozen=True)
class _AssignmentRow:
    index: int
    day: int
    shift_id: str | None
    machine_id: str
    block_id: str
    production: float | None


@dataclass(frozen=True)
class ReplayAssignment:
    """One scheduled machine/block/day assignment and its tree-scale execution.

    Attributes
    ----------
    index : int
        One-based input row index.
    day : int
        Scenario day.
    shift_id : str | None
        Shift label, when supplied.
    machine_id : str
        Machine identifier.
    block_id : str
        Block identifier.
    scheduled_volume_m3 : float | None
        Scheduled production from the assignments CSV, when supplied.
    simulated_volume_m3 : float
        Processed merchantable volume.
    processed_count : int
        Processed tree count.
    unreachable_count : int
        Unreachable tree count.
    total_time_s : float
        Simulated elapsed time for this assignment.
    status : str
        ``ok``, ``under``, ``over``, ``no_remaining_trees``, ``unknown_block``,
        ``unknown_machine``, ``unsupported_system``, or ``no_work``.
    events : tuple[SpatialEvent, ...]
        Tree-scale events for this assignment.
    """

    index: int
    day: int
    shift_id: str | None
    machine_id: str
    block_id: str
    scheduled_volume_m3: float | None
    simulated_volume_m3: float
    processed_count: int
    unreachable_count: int
    total_time_s: float
    status: str
    events: tuple[SpatialEvent, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the assignment result as a JSON-serializable mapping."""
        return {
            "index": self.index,
            "day": self.day,
            "shift_id": self.shift_id,
            "machine_id": self.machine_id,
            "block_id": self.block_id,
            "scheduled_volume_m3": self.scheduled_volume_m3,
            "simulated_volume_m3": self.simulated_volume_m3,
            "processed_count": self.processed_count,
            "unreachable_count": self.unreachable_count,
            "total_time_s": self.total_time_s,
            "status": self.status,
            "events": [event.to_dict() for event in self.events],
        }


@dataclass(frozen=True)
class ReplayBlockSummary:
    """Tree consumption and schedule reconciliation for one block.

    Attributes
    ----------
    block_id : str
        Block identifier.
    scheduled_volume_m3 : float
        Sum of known scheduled production.
    processed_volume_m3 : float
        Sum of simulated merchantable volume.
    remaining_tree_count : int
        Trees not consumed by the replay.
    remaining_volume_m3 : float
        Merchantable volume still on the block.
    status : str
        ``complete``, ``leftover``, or ``no_trees``.
    """

    block_id: str
    scheduled_volume_m3: float
    processed_volume_m3: float
    remaining_tree_count: int
    remaining_volume_m3: float
    status: str

    def to_dict(self) -> dict[str, object]:
        """Return the block summary as a JSON-serializable mapping."""
        return {
            "block_id": self.block_id,
            "scheduled_volume_m3": self.scheduled_volume_m3,
            "processed_volume_m3": self.processed_volume_m3,
            "remaining_tree_count": self.remaining_tree_count,
            "remaining_volume_m3": self.remaining_volume_m3,
            "status": self.status,
        }


@dataclass(frozen=True)
class TreeReplay:
    """Tree-scale replay of one assignments CSV.

    Attributes
    ----------
    replay_id : str
        Deterministic replay identifier.
    generated_utc : str
        Generation timestamp.
    scenario_path : Path
        Scenario YAML.
    assignments_path : Path
        Assignments CSV.
    schedule_sha256 : str
        Assignments CSV digest.
    stem_id : str
        Stem run identifier.
    model_name : str
        Stem model name.
    model_version : str
        Stem model version.
    tolerance : float
        Scheduled-volume tolerance.
    assignments : tuple[ReplayAssignment, ...]
        Assignment results.
    blocks : tuple[ReplayBlockSummary, ...]
        Block consumption summaries.
    discrepancies : tuple[dict[str, object], ...]
        Explicit schedule/execution mismatches.
    warnings : tuple[str, ...]
        Non-fatal observations.
    caveats : tuple[str, ...]
        Replay-only caveats.
    """

    replay_id: str
    generated_utc: str
    scenario_path: Path
    assignments_path: Path
    schedule_sha256: str
    stem_id: str
    model_name: str
    model_version: str
    tolerance: float
    assignments: tuple[ReplayAssignment, ...]
    blocks: tuple[ReplayBlockSummary, ...]
    discrepancies: tuple[dict[str, object], ...]
    warnings: tuple[str, ...]
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the replay manifest as a JSON-serializable mapping."""
        return {
            "schema_version": TREE_REPLAY_SCHEMA,
            "replay_id": self.replay_id,
            "generated_utc": self.generated_utc,
            "scenario_path": str(self.scenario_path),
            "assignments_path": str(self.assignments_path),
            "schedule_sha256": self.schedule_sha256,
            "stem_id": self.stem_id,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "tolerance": self.tolerance,
            "assignment_count": len(self.assignments),
            "processed_count": sum(item.processed_count for item in self.assignments),
            "unreachable_count": sum(item.unreachable_count for item in self.assignments),
            "scheduled_volume_m3": sum(
                item.scheduled_volume_m3 or 0.0 for item in self.assignments
            ),
            "simulated_volume_m3": sum(item.simulated_volume_m3 for item in self.assignments),
            "assignments": [item.to_dict() for item in self.assignments],
            "blocks": [block.to_dict() for block in self.blocks],
            "discrepancies": list(self.discrepancies),
            "warnings": list(self.warnings),
            "caveats": list(self.caveats),
        }


def replay_tree_schedule(
    scenario_path: str | Path,
    assignments_path: str | Path,
    *,
    tolerance: float = DEFAULT_REPLAY_TOLERANCE,
    stem_inventory: StemInventory | None = None,
    obstacles: tuple[Obstacle, ...] = (),
    require_complete: bool = False,
    generated_utc: str | None = None,
) -> TreeReplay:
    """Replay an assignments CSV against a pinned tree inventory.

    Parameters
    ----------
    scenario_path : str | Path
        Scenario YAML with a tree-inventory pin.
    assignments_path : str | Path
        Assignments CSV with ``machine_id``, ``block_id``, and ``day`` columns.
        Optional columns are ``shift_id``, ``production``, and ``assigned``.
    tolerance : float, optional
        Relative tolerance for scheduled-versus-simulated volume.
    stem_inventory : StemInventory | None, optional
        Precomputed stem inventory.
    obstacles : tuple[Obstacle, ...], optional
        Circular obstacles passed to the spatial simulator.
    require_complete : bool, optional
        Refuse when any discrepancy is recorded.
    generated_utc : str | None, optional
        Generation timestamp.

    Returns
    -------
    TreeReplay
        Assignment results, block consumption, and discrepancies.

    Raises
    ------
    TreeReplayError
        If the schedule cannot be read, the inventory cannot be evaluated, or
        strict completion is requested with discrepancies.
    """
    if not math.isfinite(tolerance) or tolerance < 0:
        raise TreeReplayError("Replay tolerance must be finite and non-negative.")
    scenario_file = Path(scenario_path).expanduser().resolve()
    assignments_file = Path(assignments_path).expanduser().resolve()
    try:
        scenario = load_scenario(scenario_file)
        stems = stem_inventory or build_stem_inventory(scenario_file)
    except (StemModelError, ValueError, FileNotFoundError) as exc:
        raise TreeReplayError(str(exc)) from exc
    schedule_bytes = _read_bytes(assignments_file)
    schedule_sha = hashlib.sha256(schedule_bytes).hexdigest()
    rows = _read_assignments(schedule_bytes, assignments_file)
    machines = {machine.id: machine for machine in scenario.machines}
    tree_by_id = {tree.tree_id: tree for tree in stems.trees}
    remaining: dict[str, set[str]] = {}
    for tree in stems.trees:
        remaining.setdefault(tree.block_id, set()).add(tree.tree_id)
    last_position: dict[tuple[str, str], tuple[float, float, float]] = {}
    assignments: list[ReplayAssignment] = []
    discrepancies: list[dict[str, object]] = []
    warnings: list[str] = []
    for row in rows:
        index = row.index
        day = row.day
        machine_id = row.machine_id
        block_id = row.block_id
        shift_id = row.shift_id
        scheduled = row.production
        base = {
            "index": index,
            "day": day,
            "shift_id": shift_id,
            "machine_id": machine_id,
            "block_id": block_id,
            "scheduled_volume_m3": scheduled,
        }
        if block_id not in set(scenario.block_ids()):
            assignments.append(_empty_assignment(row, status="unknown_block"))
            discrepancies.append({**base, "kind": "unknown_block", "reason": "Unknown block."})
            continue
        if machine_id not in machines:
            assignments.append(_empty_assignment(row, status="unknown_machine"))
            discrepancies.append({**base, "kind": "unknown_machine", "reason": "Unknown machine."})
            continue
        if scheduled is not None and scheduled <= 0:
            assignments.append(_empty_assignment(row, status="no_work"))
            continue
        machine = machines[machine_id]
        roles = _system_roles(scenario, block_id)
        if roles and machine.role and machine.role not in roles:
            assignments.append(_empty_assignment(row, status="unsupported_system"))
            discrepancies.append(
                {
                    **base,
                    "kind": "unsupported_system",
                    "reason": f"Machine role {machine.role!r} is not in block system roles.",
                }
            )
            continue
        block_remaining = remaining.get(block_id, set())
        if not block_remaining:
            assignments.append(_empty_assignment(row, status="no_remaining_trees"))
            discrepancies.append(
                {**base, "kind": "no_remaining_trees", "reason": "No trees remain on the block."}
            )
            continue
        position = last_position.get((machine_id, block_id))
        start_x = position[0] if position else None
        start_y = position[1] if position else None
        start_z = position[2] if position else None
        try:
            simulation = simulate_block(
                scenario_file,
                block_id=block_id,
                machine_id=machine_id,
                stem_inventory=stems,
                tree_ids=set(block_remaining),
                start_x_m=start_x,
                start_y_m=start_y,
                start_z_m=start_z,
                max_total_time_s=machine.daily_hours * 3600.0,
                target_merchantable_volume_m3=scheduled,
                obstacles=obstacles,
            )
        except SpatialMachineError as exc:
            assignments.append(_empty_assignment(row, status="no_work"))
            discrepancies.append({**base, "kind": "simulation_error", "reason": str(exc)})
            continue
        processed = [event for event in simulation.events if event.status == "processed"]
        unreachable = [event for event in simulation.events if event.status == "unreachable"]
        for event in simulation.events:
            remaining[block_id].discard(event.tree_id)
        if processed:
            last_event = processed[-1]
            last_tree = tree_by_id.get(last_event.tree_id)
            last_position[(machine_id, block_id)] = (
                last_event.machine_x_m,
                last_event.machine_y_m,
                last_tree.elevation_m
                if last_tree is not None and last_tree.elevation_m is not None
                else 0.0,
            )
        simulated = sum(event.merchantable_volume_m3 for event in processed)
        status = _assignment_status(scheduled, simulated, tolerance)
        assignments.append(
            ReplayAssignment(
                index=index,
                day=day,
                shift_id=shift_id,
                machine_id=machine_id,
                block_id=block_id,
                scheduled_volume_m3=scheduled,
                simulated_volume_m3=simulated,
                processed_count=len(processed),
                unreachable_count=len(unreachable),
                total_time_s=simulation.total_time_s,
                status=status,
                events=tuple(simulation.events),
            )
        )
        if status in {"under", "over"}:
            discrepancies.append(
                {
                    **base,
                    "kind": status,
                    "reason": f"Simulated {simulated:.3f} m³ against scheduled {scheduled:.3f} m³.",
                }
            )
        if unreachable:
            discrepancies.append(
                {
                    **base,
                    "kind": "unreachable_trees",
                    "reason": f"{len(unreachable)} tree(s) could not be processed.",
                }
            )
    blocks: list[ReplayBlockSummary] = []
    for block in scenario.blocks:
        block_rows = [item for item in assignments if item.block_id == block.id]
        block_remaining = remaining.get(block.id, set())
        scheduled = sum(item.scheduled_volume_m3 or 0.0 for item in block_rows)
        processed_volume = sum(item.simulated_volume_m3 for item in block_rows)
        remaining_volume = sum(
            tree_by_id[tree_id].merchantable_volume_m3
            for tree_id in block_remaining
            if tree_id in tree_by_id
        )
        if not block_rows and not block_remaining:
            status = "no_trees"
        elif block_remaining:
            status = "leftover"
            discrepancies.append(
                {
                    "block_id": block.id,
                    "kind": "leftover_trees",
                    "reason": f"{len(block_remaining)} tree(s) remain after the schedule.",
                }
            )
        else:
            status = "complete"
        blocks.append(
            ReplayBlockSummary(
                block_id=block.id,
                scheduled_volume_m3=scheduled,
                processed_volume_m3=processed_volume,
                remaining_tree_count=len(block_remaining),
                remaining_volume_m3=remaining_volume,
                status=status,
            )
        )
    if not rows:
        warnings.append("Assignments CSV contained no replayable rows.")
    if discrepancies:
        warnings.append(f"{len(discrepancies)} replay discrepancy/discrepancies recorded.")
    if require_complete and discrepancies:
        kinds = sorted({str(item["kind"]) for item in discrepancies})
        raise TreeReplayError("Tree replay is incomplete: " + ", ".join(kinds) + ".")
    timestamp = generated_utc or datetime.now(UTC).isoformat()
    material = {
        "schedule_sha256": schedule_sha,
        "stem_id": stems.stem_id,
        "assignments": [item.to_dict() for item in assignments],
        "blocks": [block.to_dict() for block in blocks],
    }
    replay_id = (
        "fhops-tree-replay-"
        + hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
    )
    return TreeReplay(
        replay_id=replay_id,
        generated_utc=timestamp,
        scenario_path=scenario_file,
        assignments_path=assignments_file,
        schedule_sha256=schedule_sha,
        stem_id=stems.stem_id,
        model_name=stems.model_name,
        model_version=stems.model_version,
        tolerance=tolerance,
        assignments=tuple(assignments),
        blocks=tuple(blocks),
        discrepancies=tuple(discrepancies),
        warnings=tuple(warnings),
        caveats=(
            "Replay is an execution test, not a rescheduling algorithm.",
            "Cross-block machine travel is not modeled; each block starts from the first remaining tree.",
            "Machine-level assignments are replayed; full multi-machine system interaction is deferred.",
            *stems.caveats,
        ),
    )


def write_tree_replay(replay: TreeReplay, out_dir: Path) -> dict[str, Path]:
    """Write replay events, block summaries, and the replay manifest.

    Parameters
    ----------
    replay : TreeReplay
        Replay result.
    out_dir : Path
        Output directory.

    Returns
    -------
    dict[str, Path]
        Paths keyed by ``events``, ``blocks``, and ``manifest``.
    """
    output = out_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    events_path = output / "tree_replay_events.csv"
    event_columns = (
        "assignment_index",
        "day",
        "shift_id",
        "machine_id",
        "block_id",
        "assignment_status",
        "sequence",
        "tree_id",
        "event_status",
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
        writer = csv.DictWriter(handle, fieldnames=event_columns, extrasaction="ignore")
        writer.writeheader()
        for assignment in replay.assignments:
            for event in assignment.events:
                event_payload = event.to_dict()
                event_payload["event_status"] = event_payload.pop("status")
                writer.writerow(
                    {
                        "assignment_index": assignment.index,
                        "day": assignment.day,
                        "shift_id": assignment.shift_id,
                        "machine_id": assignment.machine_id,
                        "block_id": assignment.block_id,
                        "assignment_status": assignment.status,
                        **event_payload,
                    }
                )
    blocks_path = output / "tree_replay_blocks.csv"
    with blocks_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "block_id",
                "scheduled_volume_m3",
                "processed_volume_m3",
                "remaining_tree_count",
                "remaining_volume_m3",
                "status",
            ),
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(block.to_dict() for block in replay.blocks)
    manifest_path = output / "tree_replay.json"
    manifest_path.write_text(
        json.dumps(replay.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"events": events_path, "blocks": blocks_path, "manifest": manifest_path}


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise TreeReplayError(f"Unable to read assignments: {exc}") from exc


def _read_assignments(data: bytes, path: Path) -> list[_AssignmentRow]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TreeReplayError(f"Assignments CSV is not UTF-8: {path}") from exc
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise TreeReplayError("Assignments CSV has no header.")
    missing = {"machine_id", "block_id", "day"} - set(reader.fieldnames)
    if missing:
        raise TreeReplayError(
            "Assignments CSV is missing required columns: " + ", ".join(sorted(missing)) + "."
        )
    rows: list[_AssignmentRow] = []
    for index, payload in enumerate(reader, start=2):
        assigned = (payload.get("assigned") or "").strip().lower()
        if assigned in {"0", "false", "no", "n"}:
            continue
        day_raw = (payload.get("day") or "").strip()
        try:
            day = int(day_raw)
        except ValueError as exc:
            raise TreeReplayError(f"Assignments row {index} has an invalid day.") from exc
        if day < 1:
            raise TreeReplayError(f"Assignments row {index} day must be >= 1.")
        machine_id = (payload.get("machine_id") or "").strip()
        block_id = (payload.get("block_id") or "").strip()
        if not machine_id or not block_id:
            raise TreeReplayError(f"Assignments row {index} requires machine_id and block_id.")
        production: float | None = None
        production_raw = (payload.get("production") or "").strip()
        if production_raw:
            try:
                production = float(production_raw)
            except ValueError as exc:
                raise TreeReplayError(f"Assignments row {index} has invalid production.") from exc
            if not math.isfinite(production) or production < 0:
                raise TreeReplayError(
                    f"Assignments row {index} production must be finite and non-negative."
                )
        shift_id = (payload.get("shift_id") or "").strip() or None
        rows.append(
            _AssignmentRow(
                index=index,
                day=day,
                shift_id=shift_id,
                machine_id=machine_id,
                block_id=block_id,
                production=production,
            )
        )
    rows.sort(key=lambda row: (row.day, row.shift_id or "", row.index))
    return rows


def _empty_assignment(row: _AssignmentRow, *, status: str) -> ReplayAssignment:
    return ReplayAssignment(
        index=row.index,
        day=row.day,
        shift_id=row.shift_id,
        machine_id=row.machine_id,
        block_id=row.block_id,
        scheduled_volume_m3=row.production,
        simulated_volume_m3=0.0,
        processed_count=0,
        unreachable_count=0,
        total_time_s=0.0,
        status=status,
        events=(),
    )


def _assignment_status(scheduled: float | None, simulated: float, tolerance: float) -> str:
    if scheduled is None:
        return "ok" if simulated > 0 else "no_work"
    if simulated < scheduled * (1.0 - tolerance):
        return "under"
    if simulated > scheduled * (1.0 + tolerance):
        return "over"
    return "ok"


def _system_roles(scenario: Scenario, block_id: str) -> set[str]:
    block = next((item for item in scenario.blocks if item.id == block_id), None)
    if block is None or not block.harvest_system_id:
        return set()
    systems = dict(default_system_registry())
    systems.update(getattr(scenario, "harvest_systems", None) or {})
    system = systems.get(block.harvest_system_id)
    if system is None:
        return set()
    return {job.machine_role for job in system.jobs if job.machine_role}
