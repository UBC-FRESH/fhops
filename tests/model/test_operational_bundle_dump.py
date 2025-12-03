import json
from pathlib import Path

from fhops.model.milp.data import build_operational_bundle, bundle_from_dict, bundle_to_dict
from fhops.scenario.contract import Problem
from fhops.scenario.io.loaders import load_scenario

FIXTURE_PATH = Path("tests/fixtures/milp/tiny7_operational_bundle.json")


def test_bundle_round_trip_dict() -> None:
    scenario = load_scenario("examples/tiny7/scenario.yaml")
    problem = Problem.from_scenario(scenario)
    bundle = build_operational_bundle(problem)

    restored = bundle_from_dict(bundle_to_dict(bundle))
    assert restored == bundle


def test_bundle_fixture_loads() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    bundle = bundle_from_dict(payload)
    assert tuple(bundle.blocks) == tuple(payload["blocks"])
    assert bundle.systems
