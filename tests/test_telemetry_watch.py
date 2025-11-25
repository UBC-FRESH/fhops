from __future__ import annotations

import json
from pathlib import Path

import pytest

from fhops.telemetry.watch import Snapshot, SnapshotBus, summarize_snapshots

FIXTURES = Path(__file__).parent / "fixtures"


def test_snapshot_progress_ratio():
    snap = Snapshot(
        scenario="foo",
        solver="bar",
        iteration=5,
        max_iterations=10,
        objective=1.0,
        best_gap=None,
        runtime_seconds=1.0,
    )
    assert snap.progress_ratio == 0.5


def test_snapshot_progress_ratio_none_when_max_missing():
    snap = Snapshot(
        scenario="foo",
        solver="bar",
        iteration=5,
        max_iterations=None,
        objective=1.0,
        best_gap=None,
        runtime_seconds=1.0,
    )
    assert snap.progress_ratio is None


def test_snapshotbus_sink_and_get():
    bus = SnapshotBus()
    sink = bus.sink()
    snap = Snapshot(
        scenario="foo",
        solver="bar",
        iteration=1,
        max_iterations=2,
        objective=0.0,
        best_gap=0.1,
        runtime_seconds=0.5,
    )
    sink(snap)
    assert bus.get(timeout=0.1) == snap


def test_snapshotbus_drain_empty():
    bus = SnapshotBus()
    assert list(bus.drain()) == []


def test_snapshotbus_drain_flushes_multiple():
    bus = SnapshotBus()
    sink = bus.sink()
    snaps = [
        Snapshot(
            scenario="foo",
            solver=f"solver-{i}",
            iteration=i,
            max_iterations=10,
            objective=float(i),
            best_gap=None,
            runtime_seconds=0.1 * i,
        )
        for i in range(3)
    ]
    for snap in snaps:
        sink(snap)
    assert list(bus.drain()) == snaps


def _load_fixture_snapshots(name: str) -> list[Snapshot]:
    data = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    snapshots: list[Snapshot] = []
    for line in data:
        if not line:
            continue
        record = json.loads(line)
        snapshots.append(
            Snapshot(
                scenario=record["scenario"],
                solver=record["solver"],
                iteration=int(record["iteration"]),
                max_iterations=int(record.get("max_iterations"))
                if record.get("max_iterations") is not None
                else None,
                objective=float(record["objective"]),
                best_gap=None,
                runtime_seconds=float(record["runtime_seconds"]),
            )
        )
    return snapshots


def test_summarize_snapshots_fixture():
    snapshots = _load_fixture_snapshots("telemetry_watch_sample.jsonl")
    summary = summarize_snapshots(snapshots)
    small_key = ("synthetic-small", "sa")
    medium_key = ("synthetic-medium", "ils")
    assert summary[small_key]["best_objective"] == pytest.approx(90.0)
    assert summary[small_key]["runtime_seconds"] == pytest.approx(1.8)
    assert summary[medium_key]["best_objective"] == pytest.approx(45.0)
    assert summary[medium_key]["runtime_seconds"] == pytest.approx(2.5)
