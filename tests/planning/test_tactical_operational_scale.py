"""Scale-generator and benchmark coverage for tactical–operational planning."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from fhops.cli.main import app
from fhops.model.milp.tactical_operational import (
    build_tactical_operational_bundle,
    solve_tactical_operational_milp,
)
from fhops.planning.tactical_operational.io import load_tactical_operational_scenario
from fhops.planning.tactical_operational.scale import (
    TacticalScaleConfig,
    generate_tactical_scale_scenario,
    run_tactical_scale_benchmark,
    write_tactical_scale_benchmark,
)


def test_tactical_scale_generator_and_model_statistics() -> None:
    scenario = generate_tactical_scale_scenario(
        TacticalScaleConfig(
            num_blocks=4,
            years=1,
            periods_per_year=2,
            num_products=2,
            num_facilities=2,
            num_systems=2,
            seed=44,
            demand_fraction=0.1,
        )
    )

    assert scenario.dimension_summary()["planning_units"] == 4
    assert scenario.dimension_summary()["periods"] == 2
    assert scenario.dimension_summary()["harvest_system_options"] == 16

    result = solve_tactical_operational_milp(
        build_tactical_operational_bundle(scenario), solver="highs", time_limit=30
    )
    assert result["termination_condition"].lower() == "optimal"
    assert result["build_time_s"] >= 0.0
    assert result["solve_time_s"] >= 0.0
    stats = result["model_statistics"]
    assert stats["number_of_variables"] > 0
    assert stats["number_of_constraints"] > 0
    assert stats["number_of_binary_variables"] > 0


def test_tactical_scale_benchmark_outputs(tmp_path: Path) -> None:
    frame = run_tactical_scale_benchmark(
        [
            TacticalScaleConfig(num_blocks=2, periods_per_year=1, demand_fraction=0.1),
            TacticalScaleConfig(num_blocks=3, periods_per_year=1, demand_fraction=0.1),
        ],
        solver="highs",
        time_limit=30,
    )
    assert len(frame) == 2
    assert frame["model_number_of_variables"].gt(0).all()
    assert "peak_memory_mb" in frame.columns

    written = write_tactical_scale_benchmark(frame, tmp_path)
    assert written["csv"].exists()
    assert written["json"].exists()
    assert written["markdown"].exists()


def test_tactical_scale_cli_and_benchmark_cli(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scale.yaml"
    result = CliRunner().invoke(
        app,
        [
            "synth",
            "tactical",
            "--out",
            str(scenario_path),
            "--blocks",
            "4",
            "--periods-per-year",
            "2",
            "--demand-fraction",
            "0.1",
        ],
        prog_name="fhops",
    )
    assert result.exit_code == 0
    loaded = load_tactical_operational_scenario(scenario_path)
    assert loaded.dimension_summary()["planning_units"] == 4

    out_dir = tmp_path / "benchmark"
    result = CliRunner().invoke(
        app,
        [
            "scenario",
            "benchmark",
            "--blocks",
            "2",
            "--periods-per-year",
            "1",
            "--demand-fraction",
            "0.1",
            "--time-limit",
            "30",
            "--out-dir",
            str(out_dir),
        ],
        prog_name="fhops",
    )
    assert result.exit_code == 0
    assert (out_dir / "tactical_scale_benchmark.csv").exists()
    assert (out_dir / "tactical_scale_benchmark.md").exists()
