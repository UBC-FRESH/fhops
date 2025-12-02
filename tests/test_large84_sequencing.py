import pandas as pd
import pytest
from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.evaluation.sequencing import build_sequencing_tracker
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario


@pytest.mark.milp_refactor
def test_large84_sequencing_deficit_snapshot(tmp_path):
    runner = CliRunner()
    out_path = tmp_path / "large84_mip.csv"
    result = runner.invoke(
        app,
        [
            "solve-mip-operational",
            "examples/large84/scenario.yaml",
            "--solver",
            "gurobi",
            "--time-limit",
            "900",
            "--gap",
            "0.01",
            "--out",
            str(out_path),
        ],
    )
    if result.exit_code != 0:
        pytest.skip("Gurobi solver unavailable in test environment")

    scenario = load_scenario("examples/large84/scenario.yaml")
    pb = Problem.from_scenario(scenario)
    tracker = build_sequencing_tracker(pb)

    df = pd.read_csv(out_path).sort_values(["day", "shift_id"])
    for row in df.itertuples(index=False):
        tracker.process(
            int(row.day),
            row.machine_id,
            row.block_id,
            float(row.production),
        )

    stats = tracker.debug_snapshot()
    assert stats["sequencing_violation_count"] == 4
    breakdown = stats.get("sequencing_violation_breakdown", {})
    assert breakdown.get("missing_prereq") == 4
    assert stats.get("sequencing_first_violation_block") == "B07"
    assert stats.get("sequencing_first_violation_day") == 24
