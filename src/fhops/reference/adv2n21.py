"""ADV2N21 (Timberjack 1270/1010) partial-cut reference data."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import json

_ADV2N21_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "reference"
    / "fpinnovations"
    / "adv2n21_partial_cut.json"
)


@dataclass(frozen=True)
class ADV2N21StandSnapshot:
    merchantable_basal_area_m2_per_ha: float | None
    live_trees_per_ha: float | None
    dead_trees_per_ha: float | None
    total_trees_per_ha: float | None
    live_volume_m3_per_ha: float | None
    dead_volume_m3_per_ha: float | None
    total_volume_m3_per_ha: float | None
    avg_dbh_cm: float | None
    avg_height_m: float | None
    avg_tree_volume_m3: float | None


@dataclass(frozen=True)
class ADV2N21Treatment:
    id: str
    label: str
    treatment_type: str
    objective: str
    area_ha: float | None
    cost_per_m3_cad_1997: float
    cost_increase_percent_vs_clearcut1: float
    site_limitations: str
    cppt_classification: str | None
    pre_harvest: ADV2N21StandSnapshot | None
    post_harvest: ADV2N21StandSnapshot | None


@lru_cache(maxsize=1)
def _load_adv2n21_payload() -> dict:
    if not _ADV2N21_PATH.exists():
        raise FileNotFoundError(f"ADV2N21 dataset missing: {_ADV2N21_PATH}")
    return json.loads(_ADV2N21_PATH.read_text(encoding="utf-8"))


def _build_stand_snapshot(data: dict | None) -> ADV2N21StandSnapshot | None:
    if not data:
        return None
    return ADV2N21StandSnapshot(
        merchantable_basal_area_m2_per_ha=_maybe_float(data.get("merchantable_basal_area_m2_per_ha")),
        live_trees_per_ha=_maybe_float(data.get("live_trees_per_ha")),
        dead_trees_per_ha=_maybe_float(data.get("dead_trees_per_ha")),
        total_trees_per_ha=_maybe_float(data.get("total_trees_per_ha")),
        live_volume_m3_per_ha=_maybe_float(data.get("live_volume_m3_per_ha")),
        dead_volume_m3_per_ha=_maybe_float(data.get("dead_volume_m3_per_ha")),
        total_volume_m3_per_ha=_maybe_float(data.get("total_volume_m3_per_ha")),
        avg_dbh_cm=_maybe_float(data.get("avg_dbh_cm")),
        avg_height_m=_maybe_float(data.get("avg_height_m")),
        avg_tree_volume_m3=_maybe_float(data.get("avg_tree_volume_m3")),
    )


def _maybe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive parsing
        return None


def load_adv2n21_treatments() -> tuple[ADV2N21Treatment, ...]:
    payload = _load_adv2n21_payload()
    treatments = []
    for entry in payload.get("costs", {}).get("treatments", []):
        treatments.append(
            ADV2N21Treatment(
                id=str(entry["id"]),
                label=str(entry.get("label", entry["id"])),
                treatment_type=str(entry.get("treatment_type", "unknown")),
                objective=str(entry.get("objective", "")),
                area_ha=_maybe_float(entry.get("area_ha")),
                cost_per_m3_cad_1997=float(entry["cost_per_m3_cad"]),
                cost_increase_percent_vs_clearcut1=float(
                    entry.get("cost_increase_percent_vs_clearcut1", 0.0)
                ),
                site_limitations=str(entry.get("site_limitations", "")).strip(),
                cppt_classification=entry.get("cppt_classification"),
                pre_harvest=_build_stand_snapshot(entry.get("pre_harvest")),
                post_harvest=_build_stand_snapshot(entry.get("post_harvest")),
            )
        )
    return tuple(treatments)


def get_adv2n21_treatment(treatment_id: str) -> ADV2N21Treatment:
    treatment_id_lower = treatment_id.lower()
    for treatment in load_adv2n21_treatments():
        if treatment.id.lower() == treatment_id_lower:
            return treatment
    valid = ", ".join(t.id for t in load_adv2n21_treatments())
    raise ValueError(f"Unknown ADV2N21 treatment '{treatment_id}'. Valid options: {valid}")


def adv2n21_cost_base_year() -> int:
    payload = _load_adv2n21_payload()
    try:
        return int(payload.get("costs", {}).get("base_year", 1997))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return 1997
