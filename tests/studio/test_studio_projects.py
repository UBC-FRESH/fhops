"""Smoke tests for the Scenario Studio project overlay."""

from __future__ import annotations

from pathlib import Path

from fhops.tree_inventory import load_tree_inventory
from sandbox.studio.projects import (
    create_project,
    materialize_case,
    project_dataset,
    save_project,
)
from sandbox.tree_lab.cases import load_case

ROOT = Path(__file__).resolve().parents[2]


def test_project_dataset_and_retention(tmp_path: Path) -> None:
    """A project can be created, retained, saved, and read back."""
    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    project["retention"]["tree_ids"] = ["T00001", "T00002", "T00003"]
    saved = save_project(tmp_path, project)
    dataset = project_dataset(case, saved)
    assert dataset["stats"]["tree_count"] == 900
    assert dataset["stats"]["retained_tree_count"] == 3
    assert dataset["stats"]["inside_tree_count"] == 900
    assert dataset["stats"]["block_area_ha"] > 0


def test_materialized_case_filters_retention(tmp_path: Path) -> None:
    """Materializing a project removes retained trees from the runnable case."""
    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    project["retention"]["tree_ids"] = ["T00001", "T00002"]
    saved = save_project(tmp_path, project)
    derived = materialize_case(tmp_path, saved, case)
    inventory = load_tree_inventory(
        derived.path("inventory"), metadata_path=derived.path("metadata")
    )
    assert len(inventory.rows) == 898
    assert derived.manifest["landing"]["x"] == saved["landing"]["x"]
    assert derived.manifest["system_args"]["feller"] == "H1"
    assert len(derived.manifest["obstacles"]) == 2


def test_retention_clump_filters_trees(tmp_path: Path) -> None:
    """Clump polygons retain trees and flow into materialized obstacles."""
    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    initial = project_dataset(case, project)
    tree = next(item for item in initial["trees"] if item["inside"])
    x, y = float(tree["x"]), float(tree["y"])
    project["retention"]["clumps"] = [
        {
            "id": "test-clump",
            "label": "test retention clump",
            "polygon": [[x - 8, y - 8], [x + 8, y - 8], [x + 8, y + 8], [x - 8, y + 8]],
        }
    ]
    saved = save_project(tmp_path, project)
    dataset = project_dataset(case, saved)
    assert dataset["stats"]["clump_count"] == 1
    assert dataset["stats"]["clump_area_ha"] > 0
    assert dataset["stats"]["retained_tree_count"] >= 1
    derived = materialize_case(tmp_path, saved, case)
    inventory = load_tree_inventory(
        derived.path("inventory"), metadata_path=derived.path("metadata")
    )
    assert len(inventory.rows) < 900
    assert derived.manifest["retention_clumps"]
    assert derived.manifest["obstacles"]


def test_operator_policy_translation(tmp_path: Path) -> None:
    """Machine policy presets translate into runnable system arguments."""
    from sandbox.studio.projects import apply_operator_policies

    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    skidder = next(item for item in project["machines"] if "skidder" in item["role"])
    loader = next(item for item in project["machines"] if item["role"] == "loader")
    project["operator_policies"][skidder["id"]] = "throughput"
    project["operator_policies"][loader["id"]] = "careful"
    args = apply_operator_policies(project)
    assert args["skidder_empty_speed"] > 1.4
    assert args["loader_process_fixed"] > 45.0
