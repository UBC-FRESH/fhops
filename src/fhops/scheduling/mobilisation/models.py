"""Mobilisation and setup cost metadata."""

from __future__ import annotations

from pydantic import BaseModel, field_validator

__all__ = [
    "BlockDistance",
    "MachineMobilisation",
    "MobilisationConfig",
    "build_distance_lookup",
]


class BlockDistance(BaseModel):
    """Distance between two blocks in metres."""

    from_block: str
    to_block: str
    distance_m: float

    @field_validator("distance_m")
    @classmethod
    def _distance_positive(cls, value: float) -> float:
        if value < 0:
            raise ValueError("distance_m must be non-negative")
        return value


class MachineMobilisation(BaseModel):
    """Mobilisation parameters for a machine/system."""

    machine_id: str
    walk_cost_per_meter: float
    move_cost_flat: float
    walk_threshold_m: float = 1000.0
    setup_cost: float = 0.0

    @field_validator("walk_cost_per_meter", "move_cost_flat", "walk_threshold_m", "setup_cost")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("mobilisation parameters must be non-negative")
        return value


class MobilisationConfig(BaseModel):
    """Complete mobilisation configuration for a scenario."""

    machine_params: list[MachineMobilisation]
    distances: list[BlockDistance] | None = None
    default_walk_threshold_m: float = 1000.0
    distance_csv: str | None = None

    @field_validator("default_walk_threshold_m")
    @classmethod
    def _threshold_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("default_walk_threshold_m must be non-negative")
        return value


def build_distance_lookup(config: MobilisationConfig | None) -> dict[tuple[str, str], float]:
    """Return symmetric distance lookup from mobilisation config."""

    if config is None or not config.distances:
        return {}

    lookup: dict[tuple[str, str], float] = {}
    for dist in config.distances:
        lookup[(dist.from_block, dist.to_block)] = dist.distance_m
        lookup[(dist.to_block, dist.from_block)] = dist.distance_m
        lookup.setdefault((dist.from_block, dist.from_block), 0.0)
        lookup.setdefault((dist.to_block, dist.to_block), 0.0)
    return lookup
