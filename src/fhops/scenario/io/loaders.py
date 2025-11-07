"""Scenario loading utilities (YAML metadata + CSV tables)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml
from pydantic import TypeAdapter

from fhops.scenario.contract.models import (
    Block,
    CalendarEntry,
    Landing,
    Machine,
    ProductionRate,
    Scenario,
)

__all__ = ["load_scenario", "read_csv"]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def load_scenario(yaml_path: str | Path) -> Scenario:
    base_path = Path(yaml_path).resolve()
    with base_path.open("r", encoding="utf-8") as handle:
        meta = yaml.safe_load(handle)
    root = base_path.parent

    def require(name: str) -> Path:
        candidate = root / meta["data"][name]
        if not candidate.exists():  # pragma: no cover - defensive
            raise FileNotFoundError(candidate)
        return candidate

    blocks = TypeAdapter(list[Block]).validate_python(
        read_csv(require("blocks")).to_dict("records")
    )
    machines = TypeAdapter(list[Machine]).validate_python(
        read_csv(require("machines")).to_dict("records")
    )
    landings = TypeAdapter(list[Landing]).validate_python(
        read_csv(require("landings")).to_dict("records")
    )
    calendar = TypeAdapter(list[CalendarEntry]).validate_python(
        read_csv(require("calendar")).to_dict("records")
    )
    rates = TypeAdapter(list[ProductionRate]).validate_python(
        read_csv(require("prod_rates")).to_dict("records")
    )

    return Scenario(
        name=meta["name"],
        num_days=int(meta["num_days"]),
        start_date=meta.get("start_date"),
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        production_rates=rates,
    )
