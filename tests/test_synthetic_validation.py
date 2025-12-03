from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from fhops.cli.benchmarks import run_benchmark_suite
from fhops.evaluation import (
    day_dataframe_from_ensemble,
    run_stochastic_playback,
    shift_dataframe_from_ensemble,
)
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from fhops.scenario.synthetic import SyntheticDatasetConfig, sampling_config_for


def _load_sa_assignments(summary: pd.DataFrame, bench_dir: Path) -> pd.DataFrame:
    scenario_label = summary.iloc[0]["scenario"]
    return pd.read_csv(bench_dir / scenario_label / "sa_assignments.csv")


def _run_stochastic_smoke(scenario_path: Path, tmp_path: Path, tier: str) -> None:
    bench_dir = tmp_path / f"bench_{tier}"
    summary = run_benchmark_suite(
        [scenario_path],
        bench_dir,
        time_limit=5,
        sa_iters=80,
        include_mip=False,
    )
    assignments = _load_sa_assignments(summary, bench_dir)
    scenario = load_scenario(scenario_path)
    problem = Problem.from_scenario(scenario)

    config = SyntheticDatasetConfig(
        name=scenario.name,
        tier=tier,
        num_blocks=len(scenario.blocks),
        num_days=scenario.num_days,
        num_machines=len(scenario.machines),
    )
    sampling_config = sampling_config_for(config)
    ensemble = run_stochastic_playback(problem, assignments, sampling_config=sampling_config)

    assert len(ensemble.samples) == sampling_config.samples
    shift_df = shift_dataframe_from_ensemble(ensemble)
    day_df = day_dataframe_from_ensemble(ensemble)
    if not shift_df.empty:
        assert shift_df["sample_id"].nunique() == sampling_config.samples
    else:
        # Some synthetic smoke runs rely solely on day-level summaries.
        assert shift_df.empty
    assert day_df["sample_id"].nunique() == sampling_config.samples
    assert (shift_df["utilisation_ratio"] <= 1.05).all()


def test_synthetic_small_stochastic_validation(tmp_path: Path) -> None:
    _run_stochastic_smoke(Path("examples/synthetic/small/scenario.yaml"), tmp_path, "small")


@pytest.mark.milp_refactor
def test_synthetic_medium_stochastic_validation(tmp_path: Path) -> None:
    _run_stochastic_smoke(Path("examples/synthetic/medium/scenario.yaml"), tmp_path, "medium")
