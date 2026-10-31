"""Deterministic scenario variants for serious-game levels."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from fhops.scenario.contract.models import (
    Block,
    CalendarEntry,
    Machine,
    ProductionRate,
    Scenario,
)

from .levels import GameLevel

__all__ = ["GameChoices", "build_game_scenario", "fleet_penalty", "variant_fingerprint"]


@dataclass(frozen=True, slots=True)
class GameChoices:
    """Team choices for one level."""

    fleet_counts: dict[str, int]
    arrival_profile: str
    harvest_pattern: str

    def __post_init__(self) -> None:
        if not self.fleet_counts:
            raise ValueError("fleet_counts must not be empty")
        if any(count < 1 for count in self.fleet_counts.values()):
            raise ValueError("fleet counts must be >= 1")
        if not self.arrival_profile.strip():
            raise ValueError("arrival_profile must not be blank")
        if not self.harvest_pattern.strip():
            raise ValueError("harvest_pattern must not be blank")


def build_game_scenario(
    base: Scenario,
    level: GameLevel,
    choices: GameChoices,
) -> Scenario:
    """Build a deterministic scenario variant for a level and choice set."""
    if set(choices.fleet_counts) != set(level.roles):
        raise ValueError(
            "fleet_counts roles must match level roles: "
            f"{sorted(choices.fleet_counts)} != {sorted(level.roles)}"
        )
    if choices.arrival_profile not in level.arrival_profiles:
        raise ValueError(f"Unknown arrival profile {choices.arrival_profile!r}")
    if choices.harvest_pattern not in level.harvest_patterns:
        raise ValueError(f"Unknown harvest pattern {choices.harvest_pattern!r}")

    by_role: dict[str, list[Machine]] = {}
    for machine in base.machines:
        if machine.role:
            by_role.setdefault(machine.role, []).append(machine)
    rates = {(rate.machine_id, rate.block_id): rate.rate for rate in base.production_rates}

    machines: list[Machine] = []
    production_rates: list[ProductionRate] = []
    calendar: list[CalendarEntry] = []
    breakdowns = _breakdown_slots(level)
    for option in level.fleet:
        templates = sorted(by_role.get(option.role, []), key=lambda item: item.id)
        if not templates:
            raise ValueError(f"Scenario has no machines for role {option.role!r}")
        count = choices.fleet_counts[option.role]
        if count < option.owned or count > option.maximum:
            raise ValueError(
                f"count for {option.role!r} must be in [{option.owned}, {option.maximum}]"
            )
        for index in range(count):
            template = templates[min(index, len(templates) - 1)]
            machine_id = (
                template.id if index < len(templates) else _machine_id(level, option.role, index)
            )
            machines.append(
                Machine(
                    id=machine_id,
                    crew=template.crew,
                    daily_hours=template.daily_hours,
                    operating_cost=template.operating_cost,
                    role=option.role,
                )
            )
            for block in base.blocks:
                key = (template.id, block.id)
                if key not in rates:
                    raise ValueError(
                        f"No production rate for template {template.id!r} and block {block.id!r}"
                    )
                production_rates.append(
                    ProductionRate(
                        machine_id=machine_id,
                        block_id=block.id,
                        rate=rates[key],
                    )
                )
            arrival_day = _arrival_day(
                choices.arrival_profile,
                option.role,
                index=index,
                owned=option.owned,
            )
            for day in range(1, base.num_days + 1):
                available = 1 if day >= arrival_day else 0
                if (machine_id, day) in breakdowns:
                    available = 0
                calendar.append(CalendarEntry(machine_id=machine_id, day=day, available=available))

    blocks = _apply_harvest_pattern(base.blocks, base.num_days, choices.harvest_pattern)
    payload = base.model_dump()
    payload.update(
        {
            "name": f"{base.name} — {level.name}",
            "machines": [item.model_dump() for item in machines],
            "calendar": [item.model_dump() for item in calendar],
            "shift_calendar": None,
            "production_rates": [item.model_dump() for item in production_rates],
            "blocks": [item.model_dump() for item in blocks],
            "objective_weights": level.objective_weights.model_dump(),
        }
    )
    return Scenario.model_validate(payload)


def variant_fingerprint(scenario: Scenario) -> str:
    """Return a stable SHA-256 digest of the scenario payload."""
    payload = json.dumps(scenario.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fleet_penalty(level: GameLevel, choices: GameChoices) -> float:
    """Return the total fixed fleet opportunity-cost debit."""
    total = 0.0
    for option in level.fleet:
        total += option.penalty(choices.fleet_counts[option.role])
    return float(total)


def _machine_id(level: GameLevel, role: str, index: int) -> str:
    token = role.upper().replace("_", "")[:4]
    return f"{level.level_id.upper()}-{token}-{index + 1}"


def _arrival_day(profile: str, role: str, *, index: int, owned: int) -> int:
    if profile == "hot":
        return 1
    if profile == "staged":
        return 1 if index < owned else 3
    if profile == "phased":
        role_day = {
            "feller_buncher": 1,
            "grapple_skidder": 2,
            "processor": 3,
            "loader": 3,
        }.get(role, 3)
        return role_day if index < owned else min(role_day + 2, 6)
    raise ValueError(f"Unknown arrival profile {profile!r}")


def _breakdown_slots(level: GameLevel) -> set[tuple[str, int]]:
    slots: set[tuple[str, int]] = set()
    for event in level.breakdowns:
        role = str(event["role"])
        index = int(event.get("index", 0))
        day = int(event["day"])
        slots.add((_machine_id(level, role, index), day))
    return slots


def _apply_harvest_pattern(
    blocks: list[Block],
    num_days: int,
    pattern: str,
) -> list[Block]:
    ordered = sorted(blocks, key=lambda block: block.id)
    if pattern == "parallel":
        return blocks
    if pattern == "sequential":
        step = max(1, int(round(num_days * 0.15)))
    elif pattern == "finish_first":
        step = max(1, int(round(num_days * 0.08)))
    else:
        raise ValueError(f"Unknown harvest pattern {pattern!r}")
    starts = {
        block.id: max(block.earliest_start or 1, 1 + rank * step)
        for rank, block in enumerate(ordered)
    }
    return [block.model_copy(update={"earliest_start": starts[block.id]}) for block in blocks]
