from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Tuple

from rich.console import Console
from rich.live import Live
from rich.table import Table

from fhops.telemetry.watch import Snapshot, SnapshotBus, SnapshotSink, WatchConfig


@dataclass
class LiveWatch:
    config: WatchConfig
    console: Console = field(default_factory=Console)

    def __post_init__(self) -> None:
        self._bus = SnapshotBus()
        self._state: Dict[Tuple[str, str], Snapshot] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._live: Live | None = None

    @property
    def sink(self) -> SnapshotSink:
        return self._bus.sink()

    def __enter__(self) -> LiveWatch:
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def start(self) -> None:
        if self._live is not None:
            return
        refresh = max(1, int(1 / max(self.config.refresh_interval, 0.1)))
        self._live = Live(self._render(), refresh_per_second=refresh, console=self.console)
        self._live.__enter__()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None
        if self._live:
            self._live.__exit__(None, None, None)
            self._live = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            updated = False
            for snapshot in self._bus.drain():
                key = (snapshot.scenario, snapshot.solver)
                self._state[key] = snapshot
                updated = True
            if updated and self._live:
                self._live.update(self._render())
            time.sleep(self.config.refresh_interval)

    def _render(self) -> Table:
        table = Table(title="FHOPS Heuristic Watch", expand=True)
        table.add_column("Scenario", style="cyan")
        table.add_column("Solver", style="magenta")
        table.add_column("Iter", justify="right")
        table.add_column("Progress", justify="right")
        table.add_column("Objective", justify="right")
        table.add_column("Runtime (s)", justify="right")
        if self.config.include_acceptance_rate:
            table.add_column("Accept", justify="right")
        if self.config.include_restarts:
            table.add_column("Restarts", justify="right")
        if self.config.include_workers:
            table.add_column("Workers", justify="right")
        for (scenario, solver), snap in sorted(self._state.items()):
            progress = snap.progress_ratio
            progress_str = f"{progress*100:.1f}%" if progress is not None else "?"
            accept = (
                f"{snap.acceptance_rate*100:.1f}%"
                if snap.acceptance_rate is not None
                else "-"
            )
            restarts = str(snap.restarts) if snap.restarts is not None else "-"
            workers = "-"
            if self.config.include_workers:
                if snap.workers_busy is not None and snap.workers_total is not None:
                    workers = f"{snap.workers_busy}/{snap.workers_total}"
                elif snap.workers_busy is not None:
                    workers = str(snap.workers_busy)
            row = [
                scenario,
                solver,
                str(snap.iteration),
                progress_str,
                f"{snap.objective:.3f}",
                f"{snap.runtime_seconds:.1f}",
            ]
            if self.config.include_acceptance_rate:
                row.append(accept)
            if self.config.include_restarts:
                row.append(restarts)
            if self.config.include_workers:
                row.append(workers)
            table.add_row(*row)
        return table
