"""UNBC hoe-chucking reference data loader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


_DATA_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "reference"
    / "unbc_hoe_chucking.json"
)


@dataclass(frozen=True)
class UNBCHoeChuckingScenario:
    treatment: str
    time_hours: float
    hourly_rate_cad: float
    trees: int
    net_volume_per_tree_m3: float | None
    volume_m3: float
    observed_cost_cad_per_m3: float
    weighted_cost_cad_per_m3: float | None
    productivity_m3_per_smh: float | None


@lru_cache(maxsize=1)
def load_unbc_hoe_chucking_data() -> tuple[UNBCHoeChuckingScenario, ...]:
    if not _DATA_PATH.exists():  # pragma: no cover - configuration error
        raise FileNotFoundError(f"Missing UNBC hoe-chucking data: {_DATA_PATH}")
    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    scenarios: list[UNBCHoeChuckingScenario] = []
    for entry in payload.get("scenarios", []):
        scenarios.append(
            UNBCHoeChuckingScenario(
                treatment=str(entry.get("treatment", "")),
                time_hours=float(entry.get("time_hours", 0.0) or 0.0),
                hourly_rate_cad=float(entry.get("hourly_rate_cad", 0.0) or 0.0),
                trees=int(entry.get("trees", 0) or 0),
                net_volume_per_tree_m3=(
                    float(entry.get("net_volume_per_tree_m3"))
                    if entry.get("net_volume_per_tree_m3") is not None
                    else None
                ),
                volume_m3=float(entry.get("volume_m3", 0.0) or 0.0),
                observed_cost_cad_per_m3=float(entry.get("observed_cost_cad_per_m3", 0.0) or 0.0),
                weighted_cost_cad_per_m3=(
                    float(entry.get("weighted_cost_cad_per_m3"))
                    if entry.get("weighted_cost_cad_per_m3") is not None
                    else None
                ),
                productivity_m3_per_smh=(
                    float(entry.get("productivity_m3_per_smh"))
                    if entry.get("productivity_m3_per_smh") is not None
                    else None
                ),
            )
        )
    return tuple(scenarios)
