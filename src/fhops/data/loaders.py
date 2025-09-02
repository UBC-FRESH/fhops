from __future__ import annotations
from pathlib import Path
import pandas as pd
import yaml
from pydantic import TypeAdapter
from fhops.core.types import (
    Scenario, Block, Machine, Landing, CalendarEntry, ProductionRate
)

def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)

def load_scenario(yaml_path: str | Path) -> Scenario:
    p = Path(yaml_path)
    with open(p, "r", encoding="utf-8") as f:
        meta = yaml.safe_load(f)
    base = p.parent

    def req(name: str) -> Path:
        q = base / meta["data"][name]
        if not q.exists():
            raise FileNotFoundError(q)
        return q

    blocks = TypeAdapter(list[Block]).validate_python(_read_csv(req("blocks")).to_dict("records"))
    machines = TypeAdapter(list[Machine]).validate_python(_read_csv(req("machines")).to_dict("records"))
    landings = TypeAdapter(list[Landing]).validate_python(_read_csv(req("landings")).to_dict("records"))
    calendar = TypeAdapter(list[CalendarEntry]).validate_python(_read_csv(req("calendar")).to_dict("records"))
    rates = TypeAdapter(list[ProductionRate]).validate_python(_read_csv(req("prod_rates")).to_dict("records"))

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
