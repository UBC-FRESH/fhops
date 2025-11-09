from pathlib import Path

import pandas as pd

from fhops.scenario.contract.models import Problem
from fhops.scenario.io import load_scenario


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)


def test_loader_reads_shift_calendar(tmp_path):
    blocks = tmp_path / "blocks.csv"
    machines = tmp_path / "machines.csv"
    landings = tmp_path / "landings.csv"
    calendar = tmp_path / "calendar.csv"
    prod_rates = tmp_path / "prod_rates.csv"
    shift_calendar = tmp_path / "shift_calendar.csv"

    _write_csv(
        blocks,
        [{"id": "B1", "landing_id": "L1", "work_required": 10.0, "earliest_start": 1, "latest_finish": 2}],
    )
    _write_csv(machines, [{"id": "M1"}])
    _write_csv(landings, [{"id": "L1", "daily_capacity": 1}])
    _write_csv(calendar, [{"machine_id": "M1", "day": 1, "available": 1}])
    _write_csv(prod_rates, [{"machine_id": "M1", "block_id": "B1", "rate": 5.0}])
    _write_csv(
        shift_calendar,
        [
            {"machine_id": "M1", "day": 1, "shift_id": "AM", "available": 1},
            {"machine_id": "M1", "day": 1, "shift_id": "PM", "available": 0},
            {"machine_id": "M1", "day": 2, "shift_id": "AM", "available": 1},
        ],
    )

    scenario_yaml = tmp_path / "scenario.yaml"
    scenario_yaml.write_text(
        "\n".join(
            [
                "name: Shift Demo",
                "num_days: 2",
                "data:",
                f"  blocks: {blocks.name}",
                f"  machines: {machines.name}",
                f"  landings: {landings.name}",
                f"  calendar: {calendar.name}",
                f"  prod_rates: {prod_rates.name}",
                f"  shift_calendar: {shift_calendar.name}",
            ]
        ),
        encoding="utf-8",
    )

    scenario = load_scenario(scenario_yaml)
    assert scenario.shift_calendar is not None
    assert len(scenario.shift_calendar) == 3

    problem = Problem.from_scenario(scenario)
    shift_labels = {(shift.day, shift.shift_id) for shift in problem.shifts}
    assert shift_labels == {(1, "AM"), (2, "AM")}
