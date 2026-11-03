"""Smoke tests for the Scenario Studio project overlay."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from fhops.tree_inventory import load_tree_inventory
from sandbox.studio.projects import (
    _terrain_elevation,
    apply_operator_policies,
    create_project,
    materialize_case,
    polygon_area_ha,
    project_dataset,
    project_edit_signature,
    road_network_validation,
    road_segments,
    run_freshness,
    save_project,
    stream_buffer_polygon,
    terrain_signature,
)
from sandbox.tree_lab.cases import load_case

ROOT = Path(__file__).resolve().parents[2]


def test_project_catalog_has_machine_costs() -> None:
    """Scenario operating costs are retained for comparison economics."""
    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    h1 = next(item for item in project["catalog"] if item["id"] == "H1")
    assert h1["operating_cost"] == 950.0
    assert h1["daily_hours"] == 24.0


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


def test_road_network_exports_multilinestring(tmp_path: Path) -> None:
    """Multiple authored branches export as a GeoJSON MultiLineString."""
    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    project["road"]["segments"] = [
        {"id": "main", "label": "Main haul", "points": [[0.0, 0.0], [100.0, 0.0]]},
        {"id": "branch", "label": "North branch", "points": [[50.0, 0.0], [50.0, 80.0]]},
    ]
    assert len(road_segments(project)) == 2
    derived = materialize_case(tmp_path, project, case)
    geometry = json.loads((derived.root / "approaches" / "studio_road.geojson").read_text())[
        "features"
    ][0]["geometry"]
    assert geometry["type"] == "MultiLineString"
    assert len(geometry["coordinates"]) == 2
    assert derived.manifest["road_segments"][1]["id"] == "branch"


def test_road_network_validation_detects_disconnected_branches() -> None:
    """Crossing branches are connected; separate branches are flagged."""
    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    project["road"]["segments"] = [
        {"id": "main", "label": "Main", "points": [[0.0, 0.0], [100.0, 0.0]]},
        {"id": "branch", "label": "Branch", "points": [[50.0, -40.0], [50.0, 40.0]]},
    ]
    validation = road_network_validation(project)
    assert validation["connected"] is True
    project["road"]["segments"][1]["points"] = [[200.0, -40.0], [200.0, 40.0]]
    validation = road_network_validation(project)
    assert validation["connected"] is False
    assert any("disconnected" in warning for warning in validation["warnings"])


def test_materialized_tree_elevations_follow_terrain(tmp_path: Path) -> None:
    """Derived inventory elevations use the edited terrain heightfield."""
    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    xs = [point[0] for point in project["block"]["polygon"]]
    ys = [point[1] for point in project["block"]["polygon"]]
    project["terrain"] = {
        "resolution": 2,
        "heights": [0.0, 10.0, 20.0, 30.0],
        "bounds": [min(xs), min(ys), max(xs), max(ys)],
        "base_m": 500.0,
    }
    derived = materialize_case(tmp_path, project, case)
    inventory = load_tree_inventory(
        derived.path("inventory"), metadata_path=derived.path("metadata")
    )
    for tree in inventory.rows[:20]:
        expected = _terrain_elevation(project, 500.0, tree.x_m, tree.y_m)
        assert tree.elevation_m == pytest.approx(expected, abs=1e-6)


def test_project_signatures_detect_run_affecting_changes(tmp_path: Path) -> None:
    """Run freshness ignores labels but detects retention and terrain edits."""
    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    edit_signature = project_edit_signature(project)
    terrain_sig = terrain_signature(project)
    record = {
        "studio": {
            "edit_signature": edit_signature,
            "terrain_signature": terrain_sig,
            "project_revision": project["revision"],
        }
    }
    assert run_freshness(project, record)["stale"] is False

    project["label"] = "Renamed only"
    project["revision"] = 99
    assert project_edit_signature(project) == edit_signature
    assert run_freshness(project, record)["stale"] is False

    project["retention"]["tree_ids"] = ["T00001"]
    assert project_edit_signature(project) != edit_signature
    freshness = run_freshness(project, record)
    assert freshness["stale"] is True
    assert any("Project edits" in reason for reason in freshness["reasons"])

    project["terrain"] = {"resolution": 2, "heights": [0.0, 1.0, 2.0, 3.0]}
    freshness = run_freshness(project, record)
    assert freshness["stale"] is True
    assert any("Terrain edits" in reason for reason in freshness["reasons"])

    assert run_freshness(project, {})["stale"] is True

    truck_project = create_project(case)
    truck_signature = project_edit_signature(truck_project)
    truck_record = {
        "studio": {
            "edit_signature": truck_signature,
            "terrain_signature": terrain_signature(truck_project),
            "project_revision": truck_project["revision"],
        }
    }
    assert run_freshness(truck_project, truck_record)["stale"] is False
    truck_project["landing_trucks"] = {"landing-main": 2}
    assert project_edit_signature(truck_project) != truck_signature
    assert run_freshness(truck_project, truck_record)["stale"] is True


def test_materialized_case_carries_multiple_landings(tmp_path: Path) -> None:
    """Multiple project landings flow into the derived case manifest."""
    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    project["landings"].append(
        {
            "id": "north",
            "label": "North landing",
            "x": project["landing"]["x"] + 40,
            "y": project["landing"]["y"] + 40,
        }
    )
    project["landing_trucks"] = {"landing-main": 1, "north": 2}
    project["landing_truck_specs"] = {
        "landing-main": {"capacity_m3": 25.0, "cycle_time_s": 2400.0},
        "north": {"capacity_m3": 35.0, "cycle_time_s": 3000.0},
    }
    derived = materialize_case(tmp_path, project, case)
    assert len(derived.manifest["landings"]) == 2
    assert derived.manifest["landings"][1]["id"] == "north"
    assert derived.manifest["landing"]["x"] == project["landing"]["x"]
    assert derived.manifest["landing_truck_counts"] == {"landing-main": 1, "north": 2}
    assert derived.manifest["landing_truck_specs"]["north"]["capacity_m3"] == 35.0


def test_materialized_case_carries_landing_fleets(tmp_path: Path) -> None:
    """Fleet machine assignments and clone machine rows reach the derived case."""
    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    project["landings"].append(
        {
            "id": "north",
            "label": "North",
            "x": project["landing"]["x"] + 40,
            "y": project["landing"]["y"] + 40,
        }
    )
    project["machines"].extend(
        [
            {
                "id": "H4-B",
                "role": "loader",
                "type": "loader",
                "policy": "steady",
                "landing_id": "north",
                "spec": {"process_fixed_s": 10.0},
            },
            {
                "id": "H5-B",
                "role": "roadside_processor",
                "type": "roadside_processor",
                "policy": "steady",
                "landing_id": "north",
                "spec": {"seconds_per_m3": 30.0},
            },
        ]
    )
    derived = materialize_case(tmp_path, project, case)
    fleet = derived.manifest["landing_fleets"]["north"]
    assert fleet["loader"] == "H4-B"
    assert fleet["processors"] == ["H5-B"]
    assert derived.manifest["loader_specs"]["H4-B"]["process_fixed_s"] == 10.0
    assert derived.manifest["processor_specs"]["H5-B"]["seconds_per_m3"] == 30.0
    machine_rows = (derived.root / "scenario" / "data" / "machines.csv").read_text(encoding="utf-8")
    assert "H4-B" in machine_rows
    assert "H5-B" in machine_rows


def test_materialized_case_updates_harvester_forwarder_roles(tmp_path: Path) -> None:
    """Project role edits are written into the derived scenario machine CSV."""
    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    roles = {"H1": "harvester", "H2": "forwarder", "H3": "forwarder"}
    for machine in project["machines"]:
        if machine["id"] in roles:
            machine["role"] = roles[machine["id"]]
            machine["type"] = roles[machine["id"]]
            if machine["id"] in {"H2", "H3"}:
                machine["spec"] = {
                    "capacity_m3": 16.0,
                    "forwarder_model": "eriksson-final-felling",
                    "forwarder_load_fixed_s": 100.0,
                    "forwarder_unload_fixed_s": 50.0,
                }
    derived = materialize_case(tmp_path, project, case)
    with (derived.root / "scenario" / "data" / "machines.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = {row["id"]: row["role"] for row in csv.DictReader(handle)}
    assert rows["H1"] == "harvester"
    assert rows["H2"] == "forwarder"
    assert rows["H3"] == "forwarder"
    assert derived.manifest["skidder_specs"]["H2"]["capacity_m3"] == 16.0
    assert derived.manifest["skidder_specs"]["H2"]["forwarder_model"] == "eriksson-final-felling"
    assert derived.manifest["skidder_specs"]["H2"]["forwarder_load_fixed_s"] == 100.0


def test_materialized_case_carries_project_signatures(tmp_path: Path) -> None:
    """Derived cases carry the signatures copied into run metadata."""
    case = load_case(ROOT / "sandbox" / "cases" / "afrf-gavin")
    project = create_project(case)
    derived = materialize_case(tmp_path, project, case)
    assert derived.manifest["studio_edit_signature"] == project_edit_signature(project)
    assert derived.manifest["studio_terrain_signature"] == terrain_signature(project)
    assert derived.manifest["studio_project_revision"] == project["revision"]


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
    assert args["policy_effects"][skidder["id"]]["breakdown_risk"] == "elevated"
    assert args["policy_effects"][loader["id"]]["grade_caution"] == "high"
    if project["system_args"].get("shift_days") is not None:
        assert args["failure_rate"] > 0
        assert args["repair_hours"] > 0
        assert args["max_skidder_grade"] <= 80.0
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
