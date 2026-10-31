"""Level manifests for the deterministic FHOPS web serious game."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fhops.scenario.contract.models import ObjectiveWeights

__all__ = ["FleetOption", "GameLevel", "load_levels"]


@dataclass(frozen=True, slots=True)
class FleetOption:
    """One controllable machine role in a level palette.

    Attributes
    ----------
    role:
        Normalized FHOPS machine role.
    owned:
        Number of machines included at no opportunity cost.
    maximum:
        Maximum selectable count, including owned machines.
    unit_cost:
        Fixed opportunity-cost unit in objective units.
    marginal_multipliers:
        Multipliers applied to successive extra machines. The tuple length must
        cover ``maximum - owned`` (or shorter; the last value repeats).
    spot_surcharge:
        Additive surcharge on the last extra slot.
    """

    role: str
    owned: int
    maximum: int
    unit_cost: float
    marginal_multipliers: tuple[float, ...]
    spot_surcharge: float

    def __post_init__(self) -> None:
        if not self.role.strip():
            raise ValueError("FleetOption.role must not be blank")
        if self.owned < 1:
            raise ValueError("FleetOption.owned must be >= 1")
        if self.maximum < self.owned:
            raise ValueError("FleetOption.maximum must be >= owned")
        if self.unit_cost < 0 or self.spot_surcharge < 0:
            raise ValueError("FleetOption costs must be non-negative")
        if not self.marginal_multipliers:
            raise ValueError("FleetOption.marginal_multipliers must not be empty")
        if any(value <= 0 for value in self.marginal_multipliers):
            raise ValueError("FleetOption marginal multipliers must be positive")

    def penalty(self, count: int) -> float:
        """Return the fleet opportunity-cost debit for ``count`` machines."""
        if count < self.owned:
            raise ValueError(f"count {count} is below owned fleet {self.owned}")
        if count > self.maximum:
            raise ValueError(f"count {count} exceeds maximum {self.maximum}")
        extra = count - self.owned
        total = 0.0
        for index in range(extra):
            multiplier = self.marginal_multipliers[min(index, len(self.marginal_multipliers) - 1)]
            total += self.unit_cost * multiplier
            if index == extra - 1:
                total += self.spot_surcharge
        return total


@dataclass(frozen=True, slots=True)
class GameLevel:
    """One ordered serious-game level.

    Attributes
    ----------
    level_id:
        Stable identifier.
    order:
        One-based play order.
    scenario:
        Scenario path relative to the FHOPS repository or absolute.
    name:
        Display name.
    description:
        Player-facing briefing.
    fleet:
        Machine roles and bounds.
    arrival_profiles:
        Named deterministic arrival postures.
    harvest_patterns:
        Named block-release patterns.
    objective_weights:
        Fixed FHOPS objective weights for game scoring.
    breakdowns:
        Hidden deterministic machine/day unavailability events. Each item has
        ``role``, optional ``index`` (zero-based within the role), and ``day``.
    breakdown_seed:
        Provenance seed used to generate the event list.
    """

    level_id: str
    order: int
    scenario: Path
    name: str
    description: str
    fleet: tuple[FleetOption, ...]
    arrival_profiles: tuple[str, ...]
    harvest_patterns: tuple[str, ...]
    objective_weights: ObjectiveWeights
    breakdowns: tuple[dict[str, Any], ...]
    breakdown_seed: int

    def __post_init__(self) -> None:
        if not self.level_id.strip():
            raise ValueError("GameLevel.level_id must not be blank")
        if self.order < 1:
            raise ValueError("GameLevel.order must be >= 1")
        if not self.name.strip():
            raise ValueError("GameLevel.name must not be blank")
        if len({option.role for option in self.fleet}) != len(self.fleet):
            raise ValueError("GameLevel fleet roles must be unique")
        if not self.arrival_profiles:
            raise ValueError("GameLevel.arrival_profiles must not be empty")
        if not self.harvest_patterns:
            raise ValueError("GameLevel.harvest_patterns must not be empty")

    @property
    def roles(self) -> tuple[str, ...]:
        """Return the ordered fleet roles."""
        return tuple(option.role for option in self.fleet)


def load_levels(directory: str | Path) -> tuple[GameLevel, ...]:
    """Load and validate ordered level manifests from ``*.yaml`` files."""
    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(root)
    levels: list[GameLevel] = []
    for path in sorted(root.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Level manifest must be a mapping: {path}")
        levels.append(_level_from_payload(payload, path))
    if not levels:
        raise ValueError(f"No level manifests found in {root}")
    orders = sorted(level.order for level in levels)
    if orders != list(range(1, len(levels) + 1)):
        raise ValueError("Level orders must be consecutive starting at 1")
    if len({level.level_id for level in levels}) != len(levels):
        raise ValueError("Level ids must be unique")
    return tuple(sorted(levels, key=lambda level: level.order))


def _level_from_payload(payload: dict[str, Any], path: Path) -> GameLevel:
    try:
        fleet = tuple(
            FleetOption(
                role=str(item["role"]),
                owned=int(item["owned"]),
                maximum=int(item["maximum"]),
                unit_cost=float(item["unit_cost"]),
                marginal_multipliers=tuple(float(value) for value in item["marginal_multipliers"]),
                spot_surcharge=float(item.get("spot_surcharge", 0.0)),
            )
            for item in payload["fleet"]
        )
        weights = ObjectiveWeights(**payload.get("objective_weights", {}))
        scenario_raw = Path(str(payload["scenario"]))
        scenario = scenario_raw if scenario_raw.is_absolute() else (path.parent / scenario_raw)
        return GameLevel(
            level_id=str(payload["id"]),
            order=int(payload["order"]),
            scenario=scenario.resolve(),
            name=str(payload["name"]),
            description=str(payload.get("description", "")),
            fleet=fleet,
            arrival_profiles=tuple(str(value) for value in payload["arrival_profiles"]),
            harvest_patterns=tuple(str(value) for value in payload["harvest_patterns"]),
            objective_weights=weights,
            breakdowns=tuple(dict(item) for item in payload.get("breakdowns", [])),
            breakdown_seed=int(payload.get("breakdown_seed", 0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid level manifest {path}: {exc}") from exc
