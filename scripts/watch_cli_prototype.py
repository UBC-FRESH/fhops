#!/usr/bin/env python3
"""Prototype Rich.Live dashboard that replays FHOPS telemetry JSONL files."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Tuple

import typer
from rich.live import Live
from rich.table import Table

from fhops.telemetry.watch import Snapshot, SnapshotBus, WatchConfig

app = typer.Typer(help=__doc__)


def load_jsonl(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def telemetry_to_snapshot(record: dict) -> Snapshot:
    scenario = record.get("scenario", "unknown")
    solver = record.get("solver", "unknown")
    iteration = int(record.get("iterations") or record.get("iteration") or 0)
    config = record.get("config") or {}
    max_iterations = config.get("iters") or record.get("max_iterations")
    duration = float(record.get("duration_seconds") or 0.0)
    operators_stats = record.get("operators_stats") or {}
    acceptance_rate = None
    if operators_stats:
        move_stats = operators_stats.get("move") or next(iter(operators_stats.values()), None)
        if isinstance(move_stats, dict):
            acceptance_rate = move_stats.get("acceptance_rate")
    metadata = {
        "preset": record.get("preset_label") or "",
        "tier": record.get("tier") or "",
    }
    restarts = record.get("sa_restarts") or record.get("restarts")
    workers_busy = record.get("workers_busy")
    workers_total = record.get("workers_total")
    return Snapshot(
        scenario=scenario,
        solver=solver,
        iteration=iteration,
        max_iterations=int(max_iterations) if max_iterations else None,
        objective=float(record.get("objective") or 0.0),
        best_gap=None,
        runtime_seconds=duration,
        acceptance_rate=float(acceptance_rate) if acceptance_rate is not None else None,
        restarts=int(restarts) if restarts is not None else None,
        workers_busy=int(workers_busy) if workers_busy is not None else None,
        workers_total=int(workers_total) if workers_total is not None else None,
        metadata={k: v for k, v in metadata.items() if v},
    )


def render_dashboard(state: Dict[Tuple[str, str], Snapshot]) -> Table:
    table = Table(title="FHOPS Heuristic Watch", expand=True)
    table.add_column("Scenario", style="cyan")
    table.add_column("Solver", style="magenta")
    table.add_column("Iter", justify="right")
    table.add_column("Progress", justify="right")
    table.add_column("Objective", justify="right")
    table.add_column("Runtime (s)", justify="right")
    table.add_column("Accept", justify="right")
    table.add_column("Restarts", justify="right")
    for (scenario, solver), snap in sorted(state.items()):
        progress = snap.progress_ratio
        progress_str = f"{progress*100:.1f}%" if progress is not None else "?"
        accept = (
            f"{snap.acceptance_rate*100:.1f}%"
            if snap.acceptance_rate is not None
            else "-"
        )
        restarts = str(snap.restarts) if snap.restarts is not None else "-"
        table.add_row(
            scenario,
            solver,
            str(snap.iteration),
            progress_str,
            f"{snap.objective:.3f}",
            f"{snap.runtime_seconds:.1f}",
            accept,
            restarts,
        )
    return table


@app.command()
def replay(
    telemetry: Path = typer.Argument(..., exists=True, readable=True),
    refresh: float = typer.Option(0.5, help="UI refresh interval (seconds)."),
    playback_delay: float = typer.Option(
        0.25, help="Delay between snapshots to simulate runtime (seconds)."
    ),
):
    """Replay a telemetry JSONL file using Rich Live dashboard."""

    records = load_jsonl(telemetry)
    if not records:
        typer.echo("No telemetry records found.")
        raise typer.Exit(1)

    bus = SnapshotBus()
    sink = bus.sink()
    state: Dict[Tuple[str, str], Snapshot] = {}
    config = WatchConfig(refresh_interval=refresh)

    def update_state() -> None:
        for snapshot in bus.drain():
            key = (snapshot.scenario, snapshot.solver)
            state[key] = snapshot

    with Live(render_dashboard(state), refresh_per_second=max(1, int(1 / config.refresh_interval))):
        for record in records:
            sink(telemetry_to_snapshot(record))
            update_state()
            time.sleep(playback_delay)
        update_state()

    typer.echo("Replay complete.")


if __name__ == "__main__":
    app()
