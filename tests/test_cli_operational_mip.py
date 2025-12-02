import pandas as pd

from fhops.cli.main import app
from tests.cli import CliRunner, cli_text

FIXTURE_BUNDLE = "tests/fixtures/milp/tiny7_operational_bundle.json"


def test_solve_mip_operational_cli(tmp_path):
    runner = CliRunner()
    out_path = tmp_path / "tiny7_operational.csv"
    bundle_path = tmp_path / "bundle.json"
    telemetry_log = tmp_path / "telemetry.jsonl"
    result = runner.invoke(
        app,
        [
            "solve-mip-operational",
            "examples/tiny7/scenario.yaml",
            "--out",
            str(out_path),
            "--time-limit",
            "1",
            "--dump-bundle",
            str(bundle_path),
            "--telemetry-log",
            str(telemetry_log),
        ],
    )
    assert result.exit_code == 0, cli_text(result)
    assert out_path.exists()
    assert bundle_path.exists()
    assert telemetry_log.exists()

    out_path2 = tmp_path / "tiny7_operational_bundle.csv"
    result_bundle = runner.invoke(
        app,
        [
            "solve-mip-operational",
            "--bundle-json",
            FIXTURE_BUNDLE,
            "--out",
            str(out_path2),
            "--time-limit",
            "1",
        ],
    )
    assert result_bundle.exit_code == 0, cli_text(result_bundle)
    assert out_path2.exists()


def test_solve_mip_operational_solver_options(monkeypatch, tmp_path):
    runner = CliRunner()
    out_path = tmp_path / "tiny7_operational_threads.csv"

    captured: dict[str, object] = {}

    def _fake_solver(
        bundle,
        *,
        solver="highs",
        time_limit=None,
        gap=None,
        tee=False,
        solver_options=None,
        incumbent_assignments=None,
    ):
        captured["solver_options"] = solver_options
        return {
            "objective": 0.0,
            "production": 0.0,
            "assignments": pd.DataFrame(
                columns=["machine_id", "block_id", "day", "shift_id", "assigned", "production"]
            ),
            "solver_status": "ok",
            "termination_condition": "optimal",
        }

    monkeypatch.setattr("fhops.cli.main.solve_operational_milp", _fake_solver)

    result = runner.invoke(
        app,
        [
            "solve-mip-operational",
            "examples/tiny7/scenario.yaml",
            "--out",
            str(out_path),
            "--solver-option",
            "Threads=3",
        ],
    )
    assert result.exit_code == 0, cli_text(result)
    assert captured["solver_options"] == {"Threads": 3}


def test_solve_mip_operational_incumbent(monkeypatch, tmp_path):
    runner = CliRunner()
    out_path = tmp_path / "tiny7_operational_incumbent.csv"
    incumbent_path = tmp_path / "start.csv"
    sample = pd.DataFrame(
        [
            {"machine_id": "H1", "block_id": "B01", "day": 1, "shift_id": "S1", "assigned": 1},
            {"machine_id": "H2", "block_id": "B01", "day": 1, "shift_id": "S1", "assigned": 1},
        ]
    )
    sample.to_csv(incumbent_path, index=False)

    captured: dict[str, object] = {}

    def _fake_solver(
        bundle,
        *,
        solver="highs",
        time_limit=None,
        gap=None,
        tee=False,
        solver_options=None,
        incumbent_assignments=None,
    ):
        captured["incumbent"] = incumbent_assignments
        return {
            "objective": 0.0,
            "production": 0.0,
            "assignments": pd.DataFrame(
                columns=["machine_id", "block_id", "day", "shift_id", "assigned", "production"]
            ),
            "solver_status": "ok",
            "termination_condition": "optimal",
        }

    monkeypatch.setattr("fhops.cli.main.solve_operational_milp", _fake_solver)

    result = runner.invoke(
        app,
        [
            "solve-mip-operational",
            "examples/tiny7/scenario.yaml",
            "--out",
            str(out_path),
            "--incumbent",
            str(incumbent_path),
        ],
    )
    assert result.exit_code == 0, cli_text(result)
    assert isinstance(captured["incumbent"], pd.DataFrame)
    assert len(captured["incumbent"]) == 2
