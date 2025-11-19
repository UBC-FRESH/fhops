"""UNBC hoe-chucking reference data loader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


_HOE_DATA_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "reference"
    / "unbc_hoe_chucking.json"
)

_PROC_DATA_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "reference"
    / "unbc_processing_costs.json"
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
    if not _HOE_DATA_PATH.exists():  # pragma: no cover - configuration error
        raise FileNotFoundError(f"Missing UNBC hoe-chucking data: {_HOE_DATA_PATH}")
    payload = json.loads(_HOE_DATA_PATH.read_text(encoding="utf-8"))
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


@dataclass(frozen=True)
class UNBCProcessingCostScenario:
    harvesting_system: str
    treatment: str
    layout_planning_cost_cad_per_m3: float
    felling_cost_cad_per_m3: float
    skidding_yarding_cost_cad_per_m3: float
    processing_cost_cad_per_m3: float
    loading_cost_cad_per_m3: float
    total_cost_cad_per_m3: float


@dataclass(frozen=True)
class UNBCConstructionCost:
    harvesting_system: str
    treatment: str
    time_hours: float
    hourly_rate_cad: float
    final_net_volume_m3: float
    cost_cad_per_m3: float


@lru_cache(maxsize=1)
def load_unbc_processing_costs() -> tuple[UNBCProcessingCostScenario, ...]:
    if not _PROC_DATA_PATH.exists():  # pragma: no cover - configuration error
        raise FileNotFoundError(f"Missing UNBC processing cost data: {_PROC_DATA_PATH}")
    payload = json.loads(_PROC_DATA_PATH.read_text(encoding="utf-8"))
    scenarios: list[UNBCProcessingCostScenario] = []
    for entry in payload.get("scenarios", []):
        scenarios.append(
            UNBCProcessingCostScenario(
                harvesting_system=str(entry.get("harvesting_system", "")),
                treatment=str(entry.get("treatment", "")),
                layout_planning_cost_cad_per_m3=float(entry.get("layout_planning_cost_cad_per_m3", 0.0) or 0.0),
                felling_cost_cad_per_m3=float(entry.get("felling_cost_cad_per_m3", 0.0) or 0.0),
                skidding_yarding_cost_cad_per_m3=float(entry.get("skidding_yarding_cost_cad_per_m3", 0.0) or 0.0),
                processing_cost_cad_per_m3=float(entry.get("processing_cost_cad_per_m3", 0.0) or 0.0),
                loading_cost_cad_per_m3=float(entry.get("loading_cost_cad_per_m3", 0.0) or 0.0),
                total_cost_cad_per_m3=float(entry.get("total_cost_cad_per_m3", 0.0) or 0.0),
            )
        )
    return tuple(scenarios)


@lru_cache(maxsize=1)
def load_unbc_construction_costs() -> tuple[UNBCConstructionCost, ...]:
    if not _PROC_DATA_PATH.exists():  # pragma: no cover - configuration error
        raise FileNotFoundError(f"Missing UNBC processing cost data: {_PROC_DATA_PATH}")
    payload = json.loads(_PROC_DATA_PATH.read_text(encoding="utf-8"))
    entries = []
    for entry in payload.get("construction", []):
        entries.append(
            UNBCConstructionCost(
                harvesting_system=str(entry.get("harvesting_system", "")),
                treatment=str(entry.get("treatment", "")),
                time_hours=float(entry.get("time_hours", 0.0) or 0.0),
                hourly_rate_cad=float(entry.get("hourly_rate_cad", 0.0) or 0.0),
                final_net_volume_m3=float(entry.get("final_net_volume_m3", 0.0) or 0.0),
                cost_cad_per_m3=float(entry.get("cost_cad_per_m3", 0.0) or 0.0),
            )
        )
    return tuple(entries)
