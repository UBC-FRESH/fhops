"""Case execution and run-manifest writer for the Tree Lab sandbox.

The runner shells out to the installed FHOPS CLI so the exact command, exit
status, duration, and input hashes are recorded. It never imports FHOPS
internals for simulation, which keeps the sandbox a pure consumer of the
released tree-scale workflow.

Run directory layout::

    runs/<case_id>/<run_id>/
        system/system_events.json
        system/system_summary.json
        scene/scene.gltf
        scene/scene.glb
        scene/scene_manifest.json
        logs/system.log
        logs/scene.log
        run.json
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sandbox.tree_lab.cases import Case, ensure_pinned, validate_case
from sandbox.tree_lab.harvest import write_run_inputs

RUN_SCHEMA = "fhops.tree_lab.run.v1"
DEFAULT_TIMEOUT_S = 900.0
_STATE_LOCK = threading.Lock()
_RUNNING: dict[str, str] = {}

__all__ = [
    "RUN_SCHEMA",
    "RunError",
    "RunManager",
    "list_runs",
    "load_run",
    "run_case",
]


class RunError(RuntimeError):
    """Raised when a case run cannot start or finish."""


@dataclass(slots=True)
class RunManager:
    """Thread-safe, in-process run registry for one sandbox instance.

    Attributes
    ----------
    cases_root : Path
        Root containing case directories.
    runs_root : Path
        Root receiving run directories.
    timeout_s : float
        Per-command timeout in seconds.
    """

    cases_root: Path
    runs_root: Path
    timeout_s: float = DEFAULT_TIMEOUT_S
    _records: dict[str, dict[str, Any]] = field(default_factory=dict)

    def start(self, case: Case) -> dict[str, Any]:
        """Start a background run and return the initial run record."""
        with _STATE_LOCK:
            if case.case_id in _RUNNING:
                raise RunError(f"Case {case.case_id!r} already has a run in progress.")
            run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            _RUNNING[case.case_id] = run_id
        record: dict[str, Any] = {
            "schema_version": RUN_SCHEMA,
            "run_id": run_id,
            "case_id": case.case_id,
            "status": "running",
            "started_utc": datetime.now(UTC).isoformat(),
        }
        self._records[run_id] = record
        thread = threading.Thread(target=self._execute, args=(case, run_id), daemon=True)
        thread.start()
        return record

    def _execute(self, case: Case, run_id: str) -> None:
        try:
            record = run_case(
                case, self.runs_root / case.case_id, run_id=run_id, timeout_s=self.timeout_s
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            record = {
                "schema_version": RUN_SCHEMA,
                "run_id": run_id,
                "case_id": case.case_id,
                "status": "failed",
                "error": str(exc),
                "started_utc": self._records.get(run_id, {}).get("started_utc"),
                "finished_utc": datetime.now(UTC).isoformat(),
            }
            run_dir = self.runs_root / case.case_id / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        finally:
            self._records[run_id] = record
            with _STATE_LOCK:
                _RUNNING.pop(case.case_id, None)

    def get(self, run_id: str) -> dict[str, Any] | None:
        return self._records.get(run_id)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _fhops_version() -> str:
    from fhops import __version__

    return __version__


def _git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


def _system_command(case: Case, run_dir: Path, scenario: Path) -> list[str]:
    args = case.manifest["system_args"]
    command = [
        sys.executable,
        "-m",
        "fhops.cli.main",
        "tree",
        "system",
        str(scenario),
        "--block",
        str(case.manifest["block_id"]),
        "--feller",
        str(args["feller"]),
    ]
    for skidder in args["skidders"]:
        command.extend(["--skidder", str(skidder)])
    for processor in args.get("processors") or []:
        command.extend(["--processor", str(processor)])
    command.extend(["--loader", str(args["loader"])])
    command.extend(["--path-mode", str(args.get("path_mode", "swath"))])
    option_map = {
        "bunch_volume_m3": "--bunch-volume",
        "rate_model": "--rate-model",
        "shift_days": "--shift-days",
        "shifts_per_day": "--shifts-per-day",
        "hours_per_shift": "--hours-per-shift",
        "truck_capacity_m3": "--truck-capacity",
        "truck_count": "--truck-count",
        "truck_cycle_s": "--truck-cycle",
        "landing_capacity_m3": "--landing-capacity",
        "skidder_capacity_m3": "--skidder-capacity",
        "feller_reach_m": "--feller-reach",
        "feller_speed_mps": "--feller-speed",
        "max_skidder_grade": "--max-skidder-grade",
    }
    for key, flag in option_map.items():
        value = args.get(key)
        if value is None:
            continue
        command.extend([flag, str(value)])
    for downtime in args.get("downtime") or []:
        command.extend(["--downtime", str(downtime)])
    if args.get("processor_model"):
        command.extend(["--processor-model", str(args["processor_model"])])
    if args.get("processor_rate"):
        command.extend(["--processor-rate", str(args["processor_rate"])])
    if args.get("dem"):
        command.extend(["--dem", str(case.path("dem"))])
    if args.get("road"):
        command.extend(["--road", str(case.path("road"))])
    command.extend(["--out", str(run_dir / "system")])
    return command


def _scene_command(case: Case, run_dir: Path, scenario: Path, assignments: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "fhops.cli.main",
        "tree",
        "scene",
        str(scenario),
        str(assignments),
        "--out",
        str(run_dir / "scene"),
        "--max-log-nodes",
        "500",
    ]
    return command


def _run_command(command: list[str], log_path: Path, timeout_s: float) -> dict[str, Any]:
    started = time.monotonic()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(command) + "\n\n")
        log.flush()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            log.write(f"\n[timeout after {timeout_s:g}s]\n")
            return {
                "command": command,
                "returncode": None,
                "duration_s": round(time.monotonic() - started, 3),
                "timed_out": True,
            }
        log.write(completed.stdout)
        if completed.stderr:
            log.write("\n--- stderr ---\n")
            log.write(completed.stderr)
        return {
            "command": command,
            "returncode": completed.returncode,
            "duration_s": round(time.monotonic() - started, 3),
            "timed_out": False,
            "stdout_tail": completed.stdout.strip().splitlines()[-5:],
            "stderr_tail": completed.stderr.strip().splitlines()[-5:],
        }


def run_case(
    case: Case,
    runs_root: Path,
    *,
    run_id: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Validate, pin, simulate, and export one case.

    Parameters
    ----------
    case : Case
        Case to run.
    runs_root : Path
        Directory that receives ``<run_id>/``.
    run_id : str, optional
        Explicit run identifier. Defaults to a UTC timestamp.
    timeout_s : float, optional
        Per-command timeout in seconds.

    Returns
    -------
    dict[str, Any]
        Persisted ``run.json`` payload.

    Raises
    ------
    RunError
        If validation, pinning, simulation, or scene export fails.
    """
    run_id = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started = _utc_now()

    validation = validate_case(case)
    if not validation["valid"]:
        raise RunError("Case validation failed: " + "; ".join(validation["errors"]))
    pin = ensure_pinned(case)
    derived = write_run_inputs(case, run_dir)

    commands: list[dict[str, Any]] = []
    if case.manifest.get("system_kind") == "cable_standing":
        from sandbox.tree_lab.cable import write_cable_system

        system = write_cable_system(case, derived, run_dir)
    else:
        system = _run_command(
            _system_command(case, run_dir, derived.scenario),
            run_dir / "logs" / "system.log",
            timeout_s,
        )
    commands.append(system)
    if system.get("returncode") != 0:
        raise RunError(
            "system simulation failed: "
            + " / ".join(system.get("stderr_tail") or ["see logs/system.log"])
        )

    scene = _run_command(
        _scene_command(case, run_dir, derived.scenario, derived.assignments),
        run_dir / "logs" / "scene.log",
        timeout_s,
    )
    commands.append(scene)
    if scene.get("returncode") != 0:
        raise RunError(
            "fhops tree scene failed: "
            + " / ".join(scene.get("stderr_tail") or ["see logs/scene.log"])
        )

    summary_path = run_dir / "system" / "system_summary.json"
    events_path = run_dir / "system" / "system_events.json"
    if not summary_path.is_file() or not events_path.is_file():
        raise RunError("Simulation did not produce system_summary.json and system_events.json.")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    events = json.loads(events_path.read_text(encoding="utf-8"))

    record = {
        "schema_version": RUN_SCHEMA,
        "run_id": run_id,
        "case_id": case.case_id,
        "case_label": case.label,
        "status": "completed",
        "started_utc": started,
        "finished_utc": _utc_now(),
        "fhops_version": _fhops_version(),
        "fhops_commit": _git_commit(),
        "commands": commands,
        "pin": pin,
        "harvest": {
            "prescription": case.manifest.get("harvest")
            or {"type": "clear_cut", "marking_rule": "all"},
            "derived": derived.to_dict(),
        },
        "inputs": validation.get("hashes", {}),
        "artifacts": {
            "events_json": "system/system_events.json",
            "summary_json": "system/system_summary.json",
            "events_csv": "system/system_events.csv",
            "tree_processing_csv": "system/tree_processing.csv",
            "scene_gltf": "scene/scene.gltf",
            "scene_glb": "scene/scene.glb",
            "scene_manifest": "scene/scene_manifest.json",
        },
        "kpis": {
            "tree_count": summary.get("tree_count"),
            "processed_volume_m3": summary.get("processed_volume_m3"),
            "makespan_s": summary.get("makespan_s"),
            "landing_inventory_max_m3": summary.get("landing_inventory_max_m3"),
            "landing_inventory_final_m3": summary.get("landing_inventory_final_m3"),
            "unreachable_count": summary.get("unreachable_count"),
            "machine_summaries": summary.get("machine_summaries", {}),
            "truck_summary": summary.get("truck_summary"),
        },
        "warnings": summary.get("warnings", []),
        "caveats": summary.get("caveats", []),
        "event_count": len(events.get("events", [])),
        "duration_s": round(sum(cmd["duration_s"] for cmd in commands), 3),
    }
    (run_dir / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def list_runs(runs_root: Path, case_id: str) -> list[dict[str, Any]]:
    """Return run records for one case, newest first."""
    case_runs = runs_root / case_id
    if not case_runs.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for child in sorted(case_runs.iterdir(), reverse=True):
        record_path = child / "run.json"
        if record_path.is_file():
            try:
                records.append(json.loads(record_path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return records


def load_run(runs_root: Path, case_id: str, run_id: str) -> dict[str, Any]:
    """Load one run record or raise :class:`RunError`."""
    path = runs_root / case_id / run_id / "run.json"
    if not path.is_file():
        raise RunError(f"Run {run_id!r} for case {case_id!r} was not found.")
    return json.loads(path.read_text(encoding="utf-8"))


def copy_scene_assets(run_dir: Path, destination: Path) -> None:
    """Copy the exported scene assets into ``destination``."""
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("scene.gltf", "scene.glb", "scene_manifest.json"):
        source = run_dir / "scene" / name
        if source.is_file():
            shutil.copy2(source, destination / name)
