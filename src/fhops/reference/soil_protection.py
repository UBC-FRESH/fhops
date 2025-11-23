"""Soil protection metadata (FNRB3, ADV4N7, etc.)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parents[3] / "data/reference/soil_protection_profiles.json"


@dataclass(frozen=True)
class SoilProfile:
    """Structured soil-protection guidance."""

    id: str
    title: str
    source: str
    description: str | None
    ground_pressure_multiplier: float | None
    productivity_gain_percent: float | None
    compaction_threshold_percent: float | None
    recommendations: tuple[str, ...]


@lru_cache(maxsize=1)
def load_soil_profiles() -> Mapping[str, SoilProfile]:
    if not _DATA_PATH.exists():
        raise FileNotFoundError(f"Soil profile dataset missing: {_DATA_PATH}")
    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    profiles: dict[str, SoilProfile] = {}
    for entry in payload.get("profiles", []):
        profile = SoilProfile(
            id=entry["id"],
            title=entry.get("title", entry["id"]),
            source=entry.get("source", "unknown"),
            description=entry.get("description"),
            ground_pressure_multiplier=entry.get("ground_pressure_multiplier"),
            productivity_gain_percent=entry.get("productivity_gain_percent"),
            compaction_threshold_percent=entry.get("compaction_threshold_percent"),
            recommendations=tuple(entry.get("recommendations") or ()),
        )
        profiles[profile.id] = profile
    return profiles


def get_soil_profile(profile_id: str) -> SoilProfile:
    profiles = load_soil_profiles()
    try:
        return profiles[profile_id]
    except KeyError as exc:
        raise KeyError(
            f"Unknown soil profile '{profile_id}'. Available: {', '.join(sorted(profiles))}"
        ) from exc


def get_soil_profiles(profile_ids: Sequence[str]) -> list[SoilProfile]:
    return [get_soil_profile(pid) for pid in profile_ids]


__all__ = ["SoilProfile", "load_soil_profiles", "get_soil_profile", "get_soil_profiles"]
