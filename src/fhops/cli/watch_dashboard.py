from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field

from rich.console import Console, Group
from rich.live import Live
from rich.table import Table

from fhops.telemetry.watch import Snapshot, SnapshotBus, SnapshotSink, WatchConfig


@dataclass
class LiveWatch:
    config: WatchConfig
    console: Console = field(default_factory=Console)

    def __post_init__(self) -> None:
        self._bus = SnapshotBus()
        self._state: dict[tuple[str, str], Snapshot] = {}
        self._history: dict[tuple[str, str], deque[float]] = {}
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
        self._stop.clear()
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
        # Flush any remaining snapshots so short-lived runs still render a final state.
        self._drain_once()
        if self._live:
            self._live.__exit__(None, None, None)
            self._live = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._drain_once()
            # Wait for either the refresh interval to elapse or an explicit stop.
            self._stop.wait(self.config.refresh_interval)
        # One last drain after receiving the stop signal to capture final snapshots.
        self._drain_once()

    def _drain_once(self) -> None:
        updated = False
        for snapshot in self._bus.drain():
            key = (snapshot.scenario, snapshot.solver)
            self._state[key] = snapshot
            self._record_history(key, snapshot)
            updated = True
        if updated and self._live:
            self._live.update(self._render())

    def _record_history(self, key: tuple[str, str], snapshot: Snapshot) -> None:
        value = (
            snapshot.current_objective
            if snapshot.current_objective is not None
            else snapshot.objective
        )
        if value is None:
            return
        history = self._history.setdefault(key, deque(maxlen=max(5, self.config.sparkline_points)))
        history.append(float(value))

    def _sparkline(self, key: tuple[str, str]) -> str:
        history = self._history.get(key)
        if not history:
            return "-"
        values = list(history)
        minimum = min(values)
        maximum = max(values)
        if maximum - minimum < 1e-6:
            return "=" * min(len(values), 12)
        chars = " .:-=+*#%@"
        span = maximum - minimum
        window = values[-min(len(values), self.config.sparkline_points) :]
        spark_chars: list[str] = []
        for value in window:
            norm = (value - minimum) / span
            idx = int(round(norm * (len(chars) - 1)))
            spark_chars.append(chars[idx])
        return "".join(spark_chars)

    def _solver_details(self, snap: Snapshot) -> str:
        solver = (snap.solver or "").lower()
        parts: list[str] = []
        if solver.startswith("sa"):
            if snap.temperature is not None:
                parts.append(f"T={snap.temperature:.3f}")
            if snap.acceptance_rate is not None:
                parts.append(f"Acc={snap.acceptance_rate * 100:.1f}%")
            if snap.acceptance_rate_window is not None:
                parts.append(f"Win={snap.acceptance_rate_window * 100:.1f}%")
        elif solver.startswith("ils"):
            metadata = snap.metadata or {}
            stalls = metadata.get("stalls")
            if stalls is not None:
                parts.append(f"Stalls={stalls}")
            perturb = metadata.get("perturbations")
            if perturb is not None:
                parts.append(f"Perturb={perturb}")
            restarts = metadata.get("restarts")
            if restarts is not None:
                parts.append(f"Restarts={restarts}")
        elif solver.startswith("tabu"):
            metadata = snap.metadata or {}
            tenure = metadata.get("tabu_tenure")
            if tenure is not None:
                parts.append(f"Tenure={tenure}")
            stall_counter = metadata.get("iterations_since_improvement") or metadata.get("stalls")
            if stall_counter is not None:
                parts.append(f"SinceImprove={stall_counter}")
            restarts = metadata.get("restarts")
            if restarts is not None:
                parts.append(f"Restarts={restarts}")
            if snap.acceptance_rate is not None:
                parts.append(f"Acc={snap.acceptance_rate * 100:.1f}%")
            if snap.acceptance_rate_window is not None:
                parts.append(f"Win={snap.acceptance_rate_window * 100:.1f}%")
        return " | ".join(parts)

    def _render(self) -> Group:
        table = Table(title="FHOPS Heuristic Watch", expand=True)
        table.add_column("Scenario", style="cyan")
        table.add_column("Solver", style="magenta")
        table.add_column("Iter", justify="right")
        table.add_column("Progress", justify="right")
        table.add_column("Best Z", justify="right")
        table.add_column("Curr Z", justify="right")
        table.add_column("Roll Z", justify="right")
        table.add_column("Δbest", justify="right")
        table.add_column("Runtime (s)", justify="right")
        if self.config.include_restarts:
            table.add_column("Restarts", justify="right")
        if self.config.include_workers:
            table.add_column("Workers", justify="right")

        trend_rows: list[tuple[str, str, str, str]] = []
        for (scenario, solver), snap in sorted(self._state.items()):
            progress = snap.progress_ratio
            progress_str = f"{progress * 100:.1f}%" if progress is not None else "?"
            restarts = str(snap.restarts) if snap.restarts is not None else "-"
            workers = "-"
            if self.config.include_workers:
                if snap.workers_busy is not None and snap.workers_total is not None:
                    workers = f"{snap.workers_busy}/{snap.workers_total}"
                elif snap.workers_busy is not None:
                    workers = str(snap.workers_busy)
            delta = f"{snap.delta_objective:+.3f}" if snap.delta_objective is not None else "-"
            curr = f"{snap.current_objective:.3f}" if snap.current_objective is not None else "-"
            rolling = f"{snap.rolling_objective:.3f}" if snap.rolling_objective is not None else "-"
            sparkline = self._sparkline((scenario, solver))
            row = [
                scenario,
                solver,
                str(snap.iteration),
                progress_str,
                f"{snap.objective:.3f}",
                curr,
                rolling,
                delta,
                f"{snap.runtime_seconds:.1f}",
            ]
            if self.config.include_restarts:
                row.append(restarts)
            if self.config.include_workers:
                row.append(workers)
            table.add_row(*row)
            details = self._solver_details(snap)
            trend_rows.append((scenario, solver, sparkline, details))

        trend_table = Table(box=None, show_header=False, expand=True, padding=(0, 1))
        trend_table.add_column("Scenario", style="dim", width=16, no_wrap=True)
        trend_table.add_column("Solver", style="dim", width=8, no_wrap=True)
        trend_table.add_column("Trend", style="green")
        trend_table.add_column("Details", style="cyan")
        for scenario, solver, sparkline, details in trend_rows:
            trend_table.add_row(scenario, solver, sparkline or "-", details or "")

        return Group(table, trend_table)
