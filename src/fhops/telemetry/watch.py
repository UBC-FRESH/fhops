"""Live watcher API for streaming heuristic progress snapshots."""

from __future__ import annotations

import queue
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, Iterator, Protocol, Tuple


@dataclass(slots=True)
class Snapshot:
    """Immutable payload emitted by heuristic runners for live dashboards."""

    scenario: str
    solver: str
    iteration: int
    max_iterations: int | None
    objective: float
    best_gap: float | None
    runtime_seconds: float
    acceptance_rate: float | None = None
    restarts: int | None = None
    workers_busy: int | None = None
    workers_total: int | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def progress_ratio(self) -> float | None:
        if self.max_iterations and self.max_iterations > 0:
            return min(1.0, max(0.0, self.iteration / self.max_iterations))
        return None


class SnapshotSink(Protocol):
    """Invoked by heuristics whenever a new snapshot is available."""

    def __call__(self, snapshot: Snapshot, /) -> None:  # pragma: no cover - interface only
        ...


@dataclass(slots=True)
class WatchConfig:
    """Configuration for live watch rendering/state."""

    refresh_interval: float = 0.5  # seconds
    enable_watch: bool = True
    quiet_fallback: bool = False
    rich_theme: str | None = None
    include_workers: bool = True
    include_restarts: bool = True
    include_acceptance_rate: bool = True


# Default no-op sink used when watch mode is disabled.
def null_sink(snapshot: Snapshot) -> None:
    return None


class SnapshotBus:
    """Thread-safe queue-based transport for snapshot events."""

    def __init__(self) -> None:
        self._queue: queue.Queue[Snapshot] = queue.Queue()

    def sink(self) -> SnapshotSink:
        """Return a sink that enqueues snapshots for later consumption."""

        def _enqueue(snapshot: Snapshot) -> None:
            self._queue.put(snapshot)

        return _enqueue

    def get(self, timeout: float | None = None) -> Snapshot:
        """Blocking read of the next snapshot."""

        return self._queue.get(timeout=timeout)

    def drain(self) -> Iterator[Snapshot]:
        """Iterate over available snapshots without blocking."""

        while True:
            try:
                yield self._queue.get_nowait()
            except queue.Empty:
                break


def summarize_snapshots(
    snapshots: Iterable[Snapshot],
) -> Dict[Tuple[str, str], Dict[str, float]]:
    """Compute best objective and max runtime per (scenario, solver)."""

    summary: Dict[Tuple[str, str], Dict[str, float]] = {}
    for snap in snapshots:
        key = (snap.scenario, snap.solver)
        entry = summary.setdefault(
            key,
            {
                "best_objective": snap.objective,
                "runtime_seconds": snap.runtime_seconds,
            },
        )
        if snap.objective < entry["best_objective"]:
            entry["best_objective"] = snap.objective
        entry["runtime_seconds"] = max(entry["runtime_seconds"], snap.runtime_seconds)
    return summary
