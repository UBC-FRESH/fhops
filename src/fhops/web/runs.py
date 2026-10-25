"""Process management for live runs started by the web service.

The service starts a run by invoking the FHOPS CLI in a subprocess. It never imports the optimizer
into the request process. The manager keeps only process state and a bounded output directory; all
run values still come from the files the CLI writes.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from fhops.web.discovery import build_run_manifest

__all__ = [
    "RunControlRequest",
    "RunManager",
    "RunRequest",
    "build_command",
]

Domain = Literal["operational", "hauling", "tactical_operational"]
_RUN_TYPES = {
    "operational": {
        "solve_heur",
        "solve_ils",
        "solve_tabu",
        "solve_mip_operational",
        "eval_playback",
        "plan_rolling",
    },
    "hauling": {"haul_plan", "haul_schedule", "haul_solve"},
    "tactical_operational": {"tactical_operational", "tactical_report"},
}


class RunRequest(BaseModel):
    """Request to start a run.

    Attributes
    ----------
    domain:
        One of ``operational``, ``hauling``, or ``tactical_operational``.
    run_type:
        Domain-specific run kind: ``solve_heur``, ``solve_mip_operational``, ``haul_solve``, or
        ``tactical_operational``.
    scenario:
        Scenario path, relative to the workspace or absolute under it.
    options:
        Optional ``iterations``, ``seed``, ``time_limit``, ``day``, and ``solver`` values.
    """

    domain: Domain
    run_type: str
    scenario: str
    options: dict[str, Any] = Field(default_factory=dict)


class RunControlRequest(BaseModel):
    """Run control action."""

    action: Literal["pause", "resume", "stop"]


@dataclass(slots=True)
class RunProcess:
    """In-memory state for one live CLI process."""

    run_id: str
    out_dir: Path
    domain: str
    run_type: str
    command: list[str]
    scenario: Path
    process: subprocess.Popen[bytes]
    stdout_path: Path
    stderr_path: Path
    started_at: float = field(default_factory=time.time)
    timeout: float = 3600.0
    finished: bool = False
    paused: bool = False
    stop_requested: bool = False
    status: str = "running"
    returncode: int | None = None


class RunManager:
    """Start, monitor, and control CLI runs."""

    def __init__(self) -> None:
        self._runs: dict[str, RunProcess] = {}
        self._lock = threading.Lock()

    def start(
        self, request: RunRequest, *, workspace: Path, run_root: Path, cli_command: tuple[str, ...]
    ) -> RunProcess:
        """Start a run and return its process state."""
        if request.run_type not in _RUN_TYPES[request.domain]:
            raise ValueError(
                f"Unsupported run_type={request.run_type!r} for domain={request.domain!r}"
            )
        scenario = _resolve_scenario(request.scenario, workspace, run_root)
        run_id = _make_run_id(request.run_type, scenario)
        out_dir = (run_root / run_id).resolve()
        command = build_command(
            request,
            scenario=scenario,
            out_dir=out_dir,
            cli_command=cli_command,
            workspace=workspace,
            run_root=run_root,
        )
        out_dir.mkdir(parents=True, exist_ok=False)
        build_run_manifest(
            out_dir,
            domain=request.domain,
            run_type=request.run_type,
            command=shlex.join(command),
            scenario=str(scenario),
            solver=_solver(request.options),
            seed=_int_option(request.options, "seed"),
            status="running",
            run_id=run_id,
        )
        stdout_path = out_dir / "stdout.log"
        stderr_path = out_dir / "stderr.log"
        timeout = _float_option(request.options, "time_limit") or 3600.0
        env = os.environ.copy()
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(
                command,
                cwd=workspace,
                stdout=stdout,
                stderr=stderr,
                env=env,
            )
        record = RunProcess(
            run_id=run_id,
            out_dir=out_dir,
            domain=request.domain,
            run_type=request.run_type,
            command=command,
            scenario=scenario,
            process=process,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout=timeout,
        )
        with self._lock:
            self._runs[run_id] = record
        threading.Thread(target=self._monitor, args=(record,), daemon=True).start()
        return record

    def _monitor(self, record: RunProcess) -> None:
        status = "ok"
        try:
            record.process.wait(timeout=record.timeout)
        except subprocess.TimeoutExpired:
            status = "timeout"
            record.process.terminate()
            try:
                record.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                record.process.kill()
                record.process.wait()
        record.returncode = record.process.returncode
        if record.stop_requested:
            status = "stopped"
        elif record.process.returncode not in (0, None):
            status = "failed"
        record.status = status
        record.finished = True
        try:
            build_run_manifest(
                record.out_dir,
                domain=record.domain,
                run_type=record.run_type,
                command=shlex.join(record.command),
                scenario=str(record.scenario),
                solver=_solver_from_command(record.command),
                status=status,
                run_id=record.run_id,
            )
        except Exception:
            # The process result is still available; a manifest refresh failure should not crash
            # the monitor thread.
            pass

    def get(self, run_id: str) -> RunProcess | None:
        """Return a live run by id."""
        with self._lock:
            return self._runs.get(run_id)

    def control(self, run_id: str, action: str) -> dict[str, Any]:
        """Apply pause/resume/stop to a live run."""
        record = self.get(run_id)
        if record is None:
            raise KeyError(run_id)
        if record.finished:
            raise RuntimeError(f"Run {run_id} is already finished")
        if action == "pause":
            if os.name != "posix":
                raise RuntimeError("pause is only supported on POSIX")
            record.process.send_signal(signal.SIGSTOP)
            record.paused = True
        elif action == "resume":
            if os.name != "posix":
                raise RuntimeError("resume is only supported on POSIX")
            record.process.send_signal(signal.SIGCONT)
            record.paused = False
        elif action == "stop":
            record.stop_requested = True
            record.process.terminate()
        else:  # pragma: no cover - Pydantic validates the literal
            raise ValueError(f"Unknown control action: {action}")
        return self.status(record)

    def shutdown(self) -> None:
        """Terminate live subprocesses when the service shuts down."""
        with self._lock:
            records = list(self._runs.values())
        for record in records:
            if record.finished:
                continue
            record.stop_requested = True
            try:
                record.process.terminate()
            except ProcessLookupError:
                pass

    def status(self, record: RunProcess) -> dict[str, Any]:
        """Return a JSON-ready status payload."""
        elapsed = time.time() - record.started_at
        return {
            "run_id": record.run_id,
            "domain": record.domain,
            "run_type": record.run_type,
            "status": record.status,
            "finished": record.finished,
            "paused": record.paused,
            "returncode": record.returncode,
            "output_dir": str(record.out_dir),
            "started_at": datetime.fromtimestamp(record.started_at, UTC).isoformat(),
            "elapsed_seconds": elapsed,
        }

    async def stream(self, run_id: str):
        """Yield SSE-formatted events for a live run."""
        record = self.get(run_id)
        if record is None or record.finished:
            return
        positions: dict[Path, int] = {}
        deadline = time.monotonic() + 600
        last_emit = 0.0
        pending: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            for step_path in _step_paths(record.out_dir):
                if not step_path.exists():
                    continue
                try:
                    with step_path.open("r", encoding="utf-8") as handle:
                        handle.seek(positions.get(step_path, 0))
                        for line in handle:
                            positions[step_path] = handle.tell()
                            try:
                                record_payload = json.loads(line)
                            except ValueError:
                                continue
                            event = _step_event(record_payload)
                            if event is None:
                                continue
                            event["domain"] = record.domain
                            pending = event
                except OSError:
                    pass
            now = time.monotonic()
            if pending is not None and (record.finished or now - last_emit >= 0.5):
                last_emit = now
                yield _sse("progress", pending)
                pending = None
            if record.finished:
                break
            if now - last_emit >= 0.5:
                last_emit = now
                yield _sse(
                    "progress",
                    {
                        "domain": record.domain,
                        "status": record.status,
                        "elapsed_seconds": time.time() - record.started_at,
                    },
                )
            await asyncio.sleep(0.25)
        if record.finished:
            final_step = _last_step_event(record.out_dir)
            if final_step is not None:
                yield _sse("progress", {**final_step, "domain": record.domain})
            run_record = _last_run_record(record.out_dir)
            if run_record is not None and isinstance(run_record.get("metrics"), dict):
                yield _sse("kpis", {**run_record["metrics"], "domain": record.domain})
            assignment = _last_assignment(record.out_dir)
            if assignment is not None:
                yield _sse("assignment", {**assignment, "domain": record.domain})
            if record.status == "ok":
                done_payload: dict[str, Any] = {"status": record.status, "domain": record.domain}
                for summary_name in ("summary.json", "haul_summary.json"):
                    summary_path = record.out_dir / summary_name
                    if not summary_path.is_file():
                        continue
                    done_payload["summary"] = summary_name
                    summary = _read_json(summary_path)
                    if summary is not None:
                        done_payload["detail"] = summary
                    break
                yield _sse("done", done_payload)
            else:
                error = _read_text(record.stderr_path)[-1200:]
                yield _sse(
                    "error", {"status": record.status, "domain": record.domain, "error": error}
                )


def build_command(
    request: RunRequest,
    *,
    scenario: Path,
    out_dir: Path,
    cli_command: tuple[str, ...],
    workspace: Path | None = None,
    run_root: Path | None = None,
) -> list[str]:
    """Build the allowlisted CLI command for a run request.

    Raises
    ------
    ValueError
        For an unsupported run type or a missing/invalid option.
    """
    options = request.options
    workspace = workspace or scenario.parent
    run_root = run_root or out_dir.parent
    command = list(cli_command)
    if request.domain == "operational":
        if request.run_type in {"solve_heur", "solve_ils", "solve_tabu"}:
            cli_name = {
                "solve_heur": "solve-heur",
                "solve_ils": "solve-ils",
                "solve_tabu": "solve-tabu",
            }[request.run_type]
            command.extend(
                [
                    cli_name,
                    str(scenario),
                    "--out",
                    str(out_dir / "assignments.csv"),
                    "--telemetry-log",
                    str(out_dir / "telemetry.jsonl"),
                    "--iters",
                    str(_int_option(options, "iterations", default=500, minimum=1)),
                    "--seed",
                    str(_int_option(options, "seed", default=42)),
                ]
            )
        elif request.run_type == "solve_mip_operational":
            command.extend(
                [
                    "solve-mip-operational",
                    str(scenario),
                    "--out",
                    str(out_dir / "assignments.csv"),
                    "--telemetry-log",
                    str(out_dir / "telemetry.jsonl"),
                ]
            )
            _append_time_limit(command, options)
        elif request.run_type == "eval_playback":
            assignments = _resolve_input(
                _required_text(options, "assignments"), workspace=workspace, run_root=run_root
            )
            command.extend(
                [
                    "eval-playback",
                    str(scenario),
                    "--assignments",
                    str(assignments),
                    "--shift-out",
                    str(out_dir / "playback_shift.csv"),
                    "--day-out",
                    str(out_dir / "playback_day.csv"),
                    "--telemetry-log",
                    str(out_dir / "telemetry.jsonl"),
                ]
            )
            samples = _int_option(options, "samples", minimum=1)
            if samples is not None:
                command.extend(["--samples", str(samples)])
        elif request.run_type == "plan_rolling":
            solver = str(options.get("solver", "sa"))
            if solver not in {"stub", "sa", "mip"}:
                raise ValueError("Rolling solver must be 'stub', 'sa', or 'mip'")
            command.extend(
                [
                    "plan",
                    "rolling",
                    str(scenario),
                    "--solver",
                    solver,
                    "--sa-iters",
                    str(_int_option(options, "iterations", default=500, minimum=1)),
                    "--sa-seed",
                    str(_int_option(options, "seed", default=42)),
                    "--master-days",
                    str(_int_option(options, "master_days", default=84, minimum=1)),
                    "--sub-days",
                    str(_int_option(options, "sub_days", default=28, minimum=1)),
                    "--lock-days",
                    str(_int_option(options, "lock_days", default=14, minimum=1)),
                    "--out-json",
                    str(out_dir / "summary.json"),
                    "--out-assignments",
                    str(out_dir / "assignments.csv"),
                    "--out-iterations-jsonl",
                    str(out_dir / "iterations.jsonl"),
                    "--out-iterations-csv",
                    str(out_dir / "iterations.csv"),
                ]
            )
            limit = _float_option(options, "time_limit", minimum=0.001)
            if limit is not None:
                command.extend(["--mip-time-limit", str(int(limit))])
        else:  # pragma: no cover - validated by caller
            raise ValueError(f"Unsupported operational run_type={request.run_type}")
    elif request.domain == "hauling":
        if request.run_type == "haul_plan":
            command.extend(["haul", "plan", str(scenario), "--out-dir", str(out_dir)])
            command.extend(["--objective", str(options.get("objective", "cost"))])
            command.extend(["--solver", str(options.get("solver", "highs"))])
            _append_gap(command, options)
            _append_time_limit(command, options, integer=False)
        elif request.run_type == "haul_schedule":
            solver = str(options.get("solver", "sa"))
            if solver not in {"sa", "mip"}:
                raise ValueError("Hauling solver must be 'sa' or 'mip'")
            command.extend(
                [
                    "haul",
                    "schedule",
                    str(scenario),
                    "--out-dir",
                    str(out_dir),
                    "--day",
                    str(_int_option(options, "day", default=1, minimum=1)),
                    "--solver",
                    solver,
                    "--sa-iters",
                    str(_int_option(options, "iterations", default=500, minimum=1)),
                    "--sa-seed",
                    str(_int_option(options, "seed", default=42)),
                ]
            )
            flow_dir = options.get("flow_dir")
            if flow_dir:
                resolved_flow_dir = _resolve_directory(
                    str(flow_dir), workspace=workspace, run_root=run_root
                )
                command.extend(["--flow-dir", str(resolved_flow_dir)])
            _append_gap(command, options)
            _append_time_limit(command, options, integer=False)
        elif request.run_type == "haul_solve":
            solver = str(options.get("solver", "sa"))
            if solver not in {"sa", "mip"}:
                raise ValueError("Hauling solver must be 'sa' or 'mip'")
            command.extend(
                [
                    "haul",
                    "solve",
                    str(scenario),
                    "--out-dir",
                    str(out_dir),
                    "--day",
                    str(_int_option(options, "day", default=1, minimum=1)),
                    "--solver",
                    solver,
                    "--sa-iters",
                    str(_int_option(options, "iterations", default=500, minimum=1)),
                    "--sa-seed",
                    str(_int_option(options, "seed", default=42)),
                ]
            )
            _append_time_limit(command, options, integer=False)
        else:  # pragma: no cover - validated by caller
            raise ValueError(f"Unsupported hauling run_type={request.run_type}")
    elif request.domain == "tactical_operational":
        if request.run_type == "tactical_report":
            result_json = _resolve_input(
                _required_text(options, "result_json"), workspace=workspace, run_root=run_root
            )
            command.extend(
                [
                    "report",
                    "tactical",
                    str(result_json),
                    "--out-dir",
                    str(out_dir),
                    "--formats",
                    str(options.get("formats", "csv,markdown")),
                ]
            )
        elif request.run_type == "tactical_operational":
            command.extend(
                [
                    "plan",
                    "tactical-operational",
                    str(scenario),
                    "--out-json",
                    str(out_dir / "summary.json"),
                    "--out-harvest-csv",
                    str(out_dir / "harvest_decisions.csv"),
                    "--out-production-csv",
                    str(out_dir / "production.csv"),
                    "--out-flows-csv",
                    str(out_dir / "flows.csv"),
                    "--out-purchases-csv",
                    str(out_dir / "purchases.csv"),
                    "--out-inventory-csv",
                    str(out_dir / "inventory.csv"),
                    "--out-roads-csv",
                    str(out_dir / "roads.csv"),
                    "--out-silviculture-csv",
                    str(out_dir / "silviculture.csv"),
                    "--out-fleet-csv",
                    str(out_dir / "fleet.csv"),
                ]
            )
            _append_time_limit(command, options)
        else:  # pragma: no cover - validated by caller
            raise ValueError(f"Unsupported tactical run_type={request.run_type}")
    else:  # pragma: no cover - Pydantic validates the domain
        raise ValueError(f"Unsupported domain={request.domain}")
    return command


def _append_time_limit(
    command: list[str], options: dict[str, Any], *, integer: bool = True
) -> None:
    limit = _float_option(options, "time_limit", minimum=0.001)
    if limit is not None:
        command.extend(["--time-limit", str(int(limit) if integer else limit)])


def _append_gap(command: list[str], options: dict[str, Any]) -> None:
    gap = _float_option(options, "gap", minimum=0.0)
    if gap is not None:
        command.extend(["--gap", str(gap)])


def _resolve_input(value: str, *, workspace: Path, run_root: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = workspace / path
    path = path.resolve()
    roots = [workspace.resolve(), run_root.resolve()]
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError(f"Input escapes the workspace and run roots: {value}")
    if not path.is_file():
        raise ValueError(f"Input not found: {value}")
    return path


def _resolve_directory(value: str, *, workspace: Path, run_root: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = workspace / path
    path = path.resolve()
    roots = [workspace.resolve(), run_root.resolve()]
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError(f"Directory escapes the workspace and run roots: {value}")
    if not path.is_dir():
        raise ValueError(f"Directory not found: {value}")
    return path


def _required_text(options: dict[str, Any], key: str) -> str:
    value = options.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Option {key} is required")
    return value


def _resolve_scenario(value: str, workspace: Path, run_root: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = workspace / path
    path = path.resolve()
    roots = [workspace.resolve()]
    if run_root is not None:
        roots.append(run_root.resolve())
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError(f"Scenario escapes the configured workspace and run roots: {value}")
    if not path.is_file():
        raise ValueError(f"Scenario not found: {value}")
    return path


def _make_run_id(run_type: str, scenario: Path) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    stem = "".join(char if char.isalnum() or char in "-_" else "-" for char in scenario.stem)
    return f"{stamp}-{run_type}-{stem}"


def _int_option(
    options: dict[str, Any], key: str, default: int | None = None, *, minimum: int | None = None
) -> int | None:
    value = options.get(key, default)
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Option {key} must be an integer") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"Option {key} must be at least {minimum}")
    return parsed


def _float_option(
    options: dict[str, Any], key: str, *, minimum: float | None = None
) -> float | None:
    value = options.get(key)
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Option {key} must be a number") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"Option {key} must be at least {minimum}")
    return parsed


def _solver(options: dict[str, Any]) -> str | None:
    value = options.get("solver")
    return str(value) if value is not None else None


def _solver_from_command(command: list[str]) -> str | None:
    if "--solver" in command:
        index = command.index("--solver")
        if index + 1 < len(command):
            return command[index + 1]
    if "solve-heur" in command:
        return "sa"
    return None


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _step_paths(out_dir: Path) -> list[Path]:
    """Return step-log files for an operational run.

    The heuristics write the run record to ``telemetry.jsonl`` and step records below
    ``steps/<run_id>.jsonl``. Fake-run tests and small producers may write steps directly to
    ``telemetry.jsonl``; both are read without assuming a schema beyond ``record_type=step``.
    """
    paths = [out_dir / "telemetry.jsonl"]
    paths.extend(sorted((out_dir / "steps").glob("*.jsonl")))
    paths.append(out_dir / "iterations.jsonl")
    return paths


def _last_run_record(out_dir: Path) -> dict[str, Any] | None:
    """Return the run-level telemetry record, which carries the final KPI metrics."""
    path = out_dir / "telemetry.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if payload.get("record_type") == "run":
            return payload
    return None


def _last_assignment(out_dir: Path) -> dict[str, Any] | None:
    """Return the final assignment row for a completed operational run."""
    path = out_dir / "assignments.csv"
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return None
    return rows[-1] if rows else None


def _step_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Translate a heuristic step or rolling iteration record into a progress payload."""
    if "iteration_index" in payload:
        start = payload.get("start_day")
        horizon = payload.get("horizon_days")
        end = start + horizon - 1 if isinstance(start, int) and isinstance(horizon, int) else None
        return {
            "iteration": payload.get("iteration_index"),
            "objective": payload.get("objective"),
            "best": payload.get("objective"),
            "window": {"start_day": start, "end_day": end, "days": horizon},
            "status": payload.get("status"),
        }
    if payload.get("record_type") != "step":
        return None
    return {
        "step": payload.get("step"),
        "iteration": payload.get("step"),
        "objective": payload.get("objective"),
        "best": payload.get("best_objective"),
        "temperature": payload.get("temperature"),
        "acceptance_rate": payload.get("acceptance_rate"),
    }


def _last_step_event(out_dir: Path) -> dict[str, Any] | None:
    """Return the final telemetry step as an SSE payload, even if the stream started late."""
    for path in reversed(_step_paths(out_dir)):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            event = _step_event(payload)
            if event is not None:
                return event
    return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
