"""Smoke tests for the Scenario Studio project overlay."""

from __future__ import annotations

from pathlib import Path

import pytest

from fhops.tree_inventory import load_tree_inventory
from sandbox.studio.projects import (
    apply_operator_policies,
    create_project,
    materialize_case,
    polygon_area_ha,
    project_dataset,
    save_project,
    stream_buffer_polygon,
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
    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    skidder = next(item for item in project["machines"] if "skidder" in item["role"])
    loader = next(item for item in project["machines"] if item["role"] == "loader")
    processor = next(
        item for item in project["machines"] if item["role"] in {"roadside_processor", "processor"}
    )
    project["operator_policies"][skidder["id"]] = "throughput"
    project["operator_policies"][loader["id"]] = "careful"
    project["operator_policies"][processor["id"]] = "throughput"
    args = apply_operator_policies(project)
    assert args["skidder_empty_speed"] > 1.4
    assert args["loader_process_fixed"] > 45.0
    assert args["processor_productivity_multiplier"] > 1.0
    project["operator_policies"][processor["id"]] = "careful"
    args = apply_operator_policies(project)
    assert args["processor_productivity_multiplier"] < 1.0


def test_stream_buffer_polygon_area_and_width() -> None:
    """A stream centreline becomes a closed buffer polygon with the requested width."""
    polygon = stream_buffer_polygon([[0.0, 0.0], [0.0, 30.0]], 20.0)
    assert len(polygon) == 4
    assert polygon_area_ha(polygon) == pytest.approx(0.06, rel=1e-6)
    assert min(point[0] for point in polygon) == pytest.approx(-10.0)
    assert max(point[0] for point in polygon) == pytest.approx(10.0)


def test_stream_buffer_clump_retains_trees_and_blocks_routing(tmp_path: Path) -> None:
    """A stream buffer follows the normal riparian clump retention and obstacle path."""
    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    tree = next(item for item in project_dataset(case, project)["trees"] if item["inside"])
    x, y = float(tree["x"]), float(tree["y"])
    polygon = stream_buffer_polygon([[x, y - 20.0], [x, y + 20.0]], 20.0)
    project["retention"]["clumps"] = [
        {
            "id": "stream-test",
            "label": "stream riparian buffer (20 m)",
            "kind": "riparian",
            "source": "stream",
            "buffer_m": 20.0,
            "centerline": [[x, y - 20.0], [x, y + 20.0]],
            "polygon": polygon,
        }
    ]
    dataset = project_dataset(case, project)
    assert dataset["stats"]["clump_count"] == 1
    assert dataset["stats"]["retained_tree_count"] >= 1
    derived = materialize_case(tmp_path, project, case)
    assert derived.manifest["retention_clumps"][0]["kind"] == "riparian"
    assert derived.manifest["obstacles"]
