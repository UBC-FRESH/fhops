"""Tree-scale schedule replay tests (P17.5)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from test_stem_models import _reconciled_scenario
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.stem import build_stem_inventory
from fhops.tree_replay import (
    TreeReplayError,
    replay_tree_schedule,
    write_tree_replay,
)

runner = CliRunner()


def _stem_total(scenario: Path) -> float:
    stems = build_stem_inventory(scenario)
    return sum(tree.merchantable_volume_m3 for tree in stems.trees if tree.block_id == "B01")


def _assignments(path: Path, rows: list[dict[str, object]]) -> Path:
    columns = ("machine_id", "block_id", "day", "shift_id", "assigned", "production")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _valid_rows(total: float) -> list[dict[str, object]]:
    return [
        {
            "machine_id": "H1",
            "block_id": "B01",
            "day": 1,
            "shift_id": "S1",
            "assigned": 1,
            "production": total / 2.0,
        },
        {
            "machine_id": "H1",
            "block_id": "B01",
            "day": 2,
            "shift_id": "S1",
            "assigned": 1,
            "production": total / 2.0,
        },
    ]


def test_replay_consumes_trees_and_is_deterministic(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    total = _stem_total(scenario)
    assignments = _assignments(tmp_path / "assignments.csv", _valid_rows(total))
    kwargs = {"generated_utc": "2026-10-27T00:00:00+00:00"}

    first = replay_tree_schedule(scenario, assignments, **kwargs)
    second = replay_tree_schedule(scenario, assignments, **kwargs)

    assert first.to_dict() == second.to_dict()
    assert len(first.assignments) == 2
    assert sum(item.processed_count for item in first.assignments) == 12
    assert first.blocks[0].block_id == "B01"
    assert first.blocks[0].status == "complete"
    assert first.blocks[0].remaining_tree_count == 0
    assert first.blocks[1].status == "no_trees"
    assert all(item.status in {"ok", "under", "over"} for item in first.assignments)


def test_replay_reports_no_remaining_trees(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    total = _stem_total(scenario)
    rows = _valid_rows(total)
    rows.append(
        {
            "machine_id": "H1",
            "block_id": "B01",
            "day": 3,
            "shift_id": "S1",
            "assigned": 1,
            "production": 1.0,
        }
    )
    assignments = _assignments(tmp_path / "assignments.csv", rows)

    replay = replay_tree_schedule(scenario, assignments)
    assert replay.assignments[2].status == "no_remaining_trees"
    assert any(item["kind"] == "no_remaining_trees" for item in replay.discrepancies)


def test_replay_reports_underproduction(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    total = _stem_total(scenario)
    assignments = _assignments(
        tmp_path / "assignments.csv",
        [
            {
                "machine_id": "H1",
                "block_id": "B01",
                "day": 1,
                "shift_id": "S1",
                "assigned": 1,
                "production": total * 10.0,
            }
        ],
    )

    replay = replay_tree_schedule(scenario, assignments)
    assert replay.assignments[0].status == "under"
    assert any(item["kind"] == "under" for item in replay.discrepancies)


def test_replay_reports_missing_machine_and_block(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    assignments = _assignments(
        tmp_path / "assignments.csv",
        [
            {
                "machine_id": "NOPE",
                "block_id": "B01",
                "day": 1,
                "shift_id": "S1",
                "assigned": 1,
                "production": 1.0,
            },
            {
                "machine_id": "H1",
                "block_id": "NOPE",
                "day": 2,
                "shift_id": "S1",
                "assigned": 1,
                "production": 1.0,
            },
        ],
    )

    replay = replay_tree_schedule(scenario, assignments)
    assert {item.status for item in replay.assignments} == {
        "unknown_machine",
        "unknown_block",
    }
    kinds = {item["kind"] for item in replay.discrepancies}
    assert {"unknown_machine", "unknown_block"} <= kinds
    assert "leftover_trees" in kinds


def test_replay_reports_unsupported_system(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    machines = scenario.parent / "data" / "machines.csv"
    text = machines.read_text(encoding="utf-8").replace(
        "H1,CH1,24.0,950.0,feller_buncher",
        "H1,CH1,24.0,950.0,faller",
    )
    machines.write_text(text, encoding="utf-8")
    assignments = _assignments(
        tmp_path / "assignments.csv",
        [
            {
                "machine_id": "H1",
                "block_id": "B01",
                "day": 1,
                "shift_id": "S1",
                "assigned": 1,
                "production": 1.0,
            }
        ],
    )

    replay = replay_tree_schedule(scenario, assignments)
    assert replay.assignments[0].status == "unsupported_system"
    assert any(item["kind"] == "unsupported_system" for item in replay.discrepancies)


def test_strict_replay_refuses_discrepancies(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    assignments = _assignments(
        tmp_path / "assignments.csv",
        [
            {
                "machine_id": "NOPE",
                "block_id": "B01",
                "day": 1,
                "shift_id": "S1",
                "assigned": 1,
                "production": 1.0,
            }
        ],
    )
    with pytest.raises(TreeReplayError, match="incomplete"):
        replay_tree_schedule(scenario, assignments, require_complete=True)


def test_write_replay_outputs(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    total = _stem_total(scenario)
    assignments = _assignments(tmp_path / "assignments.csv", _valid_rows(total))
    replay = replay_tree_schedule(scenario, assignments)

    paths = write_tree_replay(replay, tmp_path / "replay")
    assert paths["events"].is_file()
    assert paths["blocks"].is_file()
    assert paths["manifest"].is_file()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "fhops.tree.replay.v1"
    assert manifest["assignment_count"] == 2
    with paths["events"].open(newline="", encoding="utf-8") as handle:
        event_rows = list(csv.DictReader(handle))
    assert event_rows
    assert event_rows[0]["event_status"] in {"processed", "unreachable"}


def test_cli_replay_writes_outputs(tmp_path: Path) -> None:
    scenario = _reconciled_scenario(tmp_path)
    total = _stem_total(scenario)
    assignments = _assignments(tmp_path / "assignments.csv", _valid_rows(total))
    out = tmp_path / "cli-replay"

    result = runner.invoke(
        app,
        ["tree", "replay", str(scenario), str(assignments), "--out", str(out)],
        prog_name="fhops",
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["assignment_count"] == 2
    assert (out / "tree_replay_events.csv").is_file()
    assert (out / "tree_replay_blocks.csv").is_file()
    assert (out / "tree_replay.json").is_file()
