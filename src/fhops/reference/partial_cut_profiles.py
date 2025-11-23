"""Load partial-cut productivity/cost profile multipliers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[3] / "data" / "reference" / "partial_cut_profiles.json"


@dataclass(frozen=True)
class PartialCutProfile:
    profile_id: str
    label: str
    volume_multiplier: float | None
    cost_multiplier: float | None
    retention_summary: str
    citation: str


@lru_cache(maxsize=1)
def load_partial_cut_profiles() -> dict[str, PartialCutProfile]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing partial-cut profile dataset: {DATA_PATH}")
    with DATA_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    profiles: dict[str, PartialCutProfile] = {}
    for entry in payload.get("profiles", []):
        profile_id = entry.get("id")
        if not profile_id:
            continue
        profiles[profile_id.lower()] = PartialCutProfile(
            profile_id=profile_id,
            label=entry.get("label", profile_id),
            volume_multiplier=_maybe_float(entry.get("volume_multiplier")),
            cost_multiplier=_maybe_float(entry.get("cost_multiplier")),
            retention_summary=entry.get("retention_summary", ""),
            citation=entry.get("citation", ""),
        )
    return profiles


def _maybe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_partial_cut_profile(profile_id: str) -> PartialCutProfile:
    profiles = load_partial_cut_profiles()
    normalized = profile_id.strip().lower()
    try:
        return profiles[normalized]
    except KeyError as exc:
        raise KeyError(
            f"Unknown partial-cut profile '{profile_id}'. "
            f"Options: {', '.join(sorted(p.profile_id for p in profiles.values()))}"
        ) from exc


__all__ = ["PartialCutProfile", "get_partial_cut_profile", "load_partial_cut_profiles"]
