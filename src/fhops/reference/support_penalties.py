"""Support-machine penalty metadata sourced from ADV15N3 and ADV4N7."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping

_DATA_ROOT = Path(__file__).resolve().parents[3] / "data/reference/fpinnovations"
_ADV15N3_PATH = _DATA_ROOT / "adv15n3_support.json"
_ADV4N7_PATH = _DATA_ROOT / "adv4n7_compaction.json"


@dataclass(frozen=True)
class TractorDriveEfficiency:
    id: str
    label: str
    drive: str
    high_speed_lph: float
    low_speed_lph: float
    low_vs_high_penalty: float
    fuel_savings_vs_baseline_percent: float
    notes: tuple[str, ...]


@dataclass(frozen=True)
class CompactionRisk:
    id: str
    label: str
    cost_multiplier: float
    load_reduction_percent: float
    max_passes_before_reassessment: int
    recommendations: tuple[str, ...]


@lru_cache(maxsize=1)
def load_adv15n3_support() -> tuple[str, Mapping[str, TractorDriveEfficiency]]:
    if not _ADV15N3_PATH.exists():
        raise FileNotFoundError(f"Missing ADV15N3 dataset: {_ADV15N3_PATH}")
    payload = json.loads(_ADV15N3_PATH.read_text(encoding="utf-8"))
    baseline_id = payload.get("baseline_drive_id")
    drives_payload = payload.get("drives") or []
    drives: dict[str, TractorDriveEfficiency] = {}
    for entry in drives_payload:
        drive_id = entry["id"]
        high_speed = entry.get("high_speed") or {}
        low_speed = entry.get("low_speed") or {}
        low_vs_high_penalty = entry.get("low_vs_high_penalty")
        if low_vs_high_penalty is None:
            high_lph = high_speed.get("avg_liters_per_hour")
            low_lph = low_speed.get("avg_liters_per_hour")
            if high_lph and low_lph:
                low_vs_high_penalty = float(low_lph) / float(high_lph)
            else:
                low_vs_high_penalty = 1.0
        drives[drive_id] = TractorDriveEfficiency(
            id=drive_id,
            label=entry.get("label", drive_id),
            drive=entry.get("drive", "mechanical"),
            high_speed_lph=float(high_speed.get("avg_liters_per_hour", 0.0)),
            low_speed_lph=float(low_speed.get("avg_liters_per_hour", 0.0)),
            low_vs_high_penalty=float(low_vs_high_penalty),
            fuel_savings_vs_baseline_percent=float(
                entry.get("fuel_intensity_vs_d7r_high_percent", 0.0)
            ),
            notes=tuple(entry.get("notes") or ()),
        )
    if not drives:
        raise ValueError(f"No drives found in {_ADV15N3_PATH}")
    if not baseline_id:
        baseline_id = next(iter(drives))
    return baseline_id, drives


def adv15n3_baseline_drive_id() -> str:
    baseline_id, _ = load_adv15n3_support()
    return baseline_id


def get_adv15n3_drive(drive_id: str) -> TractorDriveEfficiency:
    _, drives = load_adv15n3_support()
    try:
        return drives[drive_id]
    except KeyError as exc:
        raise KeyError(
            f"Unknown ADV15N3 drive '{drive_id}'. Available: {', '.join(sorted(drives))}"
        ) from exc


def adv15n3_drive_ids() -> tuple[str, ...]:
    _, drives = load_adv15n3_support()
    return tuple(sorted(drives))


@lru_cache(maxsize=1)
def load_adv4n7_compaction() -> tuple[str, Mapping[str, CompactionRisk]]:
    if not _ADV4N7_PATH.exists():
        raise FileNotFoundError(f"Missing ADV4N7 dataset: {_ADV4N7_PATH}")
    payload = json.loads(_ADV4N7_PATH.read_text(encoding="utf-8"))
    default_risk = payload.get("default_risk_id", "some")
    risks_payload = payload.get("risk_levels") or []
    risks: dict[str, CompactionRisk] = {}
    for entry in risks_payload:
        risk_id = entry["id"]
        risks[risk_id] = CompactionRisk(
            id=risk_id,
            label=entry.get("label", risk_id.title()),
            cost_multiplier=float(entry.get("cost_multiplier", 1.0)),
            load_reduction_percent=float(entry.get("load_reduction_percent", 0.0)),
            max_passes_before_reassessment=int(
                entry.get("max_passes_before_reassessment", 0)
            ),
            recommendations=tuple(entry.get("recommendations") or ()),
        )
    if not risks:
        raise ValueError(f"No compaction risk entries found in {_ADV4N7_PATH}")
    if default_risk not in risks:
        default_risk = next(iter(risks))
    return default_risk, risks


def adv4n7_default_risk_id() -> str:
    default_risk, _ = load_adv4n7_compaction()
    return default_risk


def adv4n7_risk_ids() -> tuple[str, ...]:
    _, risks = load_adv4n7_compaction()
    return tuple(sorted(risks))


def get_adv4n7_risk(risk_id: str) -> CompactionRisk:
    _, risks = load_adv4n7_compaction()
    try:
        return risks[risk_id]
    except KeyError as exc:
        raise KeyError(
            f"Unknown ADV4N7 risk '{risk_id}'. Available: {', '.join(sorted(risks))}"
        ) from exc


__all__ = [
    "TractorDriveEfficiency",
    "CompactionRisk",
    "adv15n3_baseline_drive_id",
    "adv15n3_drive_ids",
    "get_adv15n3_drive",
    "adv4n7_default_risk_id",
    "adv4n7_risk_ids",
    "get_adv4n7_risk",
]
