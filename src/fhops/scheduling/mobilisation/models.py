"""Mobilisation and setup cost metadata."""

from __future__ import annotations

from pydantic import BaseModel, field_validator

__all__ = ["BlockDistance", "MachineMobilisation", "MobilisationConfig"]


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

    @field_validator("default_walk_threshold_m")
    @classmethod
    def _threshold_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("default_walk_threshold_m must be non-negative")
        return value
