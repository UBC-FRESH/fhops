"""Advisory harvest-system operability from FEMIC terrain/canopy evidence.

P14.4 is deliberately advisory: it reads the block/landing LiDAR support already attached to a
scenario, classifies the terrain as ground/cable/helicopter, checks the scenario's current harvest
system against that class, and exposes labelled cost context. It does not silently rewrite systems
or apply unvalidated financial multipliers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from fhops.scenario.contract.models import Scenario
from fhops.scheduling.systems import default_system_registry

__all__ = [
    "BlockOperability",
    "OperabilityRules",
    "assess_block_operability",
    "assess_scenario_operability",
]

TerrainClass = Literal["ground", "cable", "helicopter"]


@dataclass(frozen=True)
class OperabilityRules:
    """Assumption thresholds used by the advisory classifier.

    These are planning assumptions, not field-validated rules. They are intentionally conservative
    and visible in every report.
    """

    ground_max_slope_percent: float = 35.0
    ground_max_roughness_m: float = 0.35
    cable_max_slope_percent: float = 60.0
    cable_max_roughness_m: float = 0.55
    fallback_slope_percent: float = 20.0
    fallback_roughness_m: float = 0.20


@dataclass(frozen=True)
class BlockOperability:
    """Advisory operability result for one block."""

    block_id: str
    landing_id: str
    terrain_class: TerrainClass
    current_system_id: str | None
    current_system_class: TerrainClass | None
    current_system_compatible: bool | None
    recommended_system_id: str
    evidence_source: str
    fallbacks: tuple[str, ...]
    slope_percent: float
    roughness_m: float
    canopy_cover_percent: float | None
    aspect_degrees: float | None
    landing_slope_percent: float | None
    landing_roughness_m: float | None
    move_in_multiplier: float
    landing_multiplier: float
    road_multiplier: float
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready payload."""
        return {
            "block_id": self.block_id,
            "landing_id": self.landing_id,
            "terrain_class": self.terrain_class,
            "current_system_id": self.current_system_id,
            "current_system_class": self.current_system_class,
            "current_system_compatible": self.current_system_compatible,
            "recommended_system_id": self.recommended_system_id,
            "evidence_source": self.evidence_source,
            "fallbacks": list(self.fallbacks),
            "slope_percent": self.slope_percent,
            "roughness_m": self.roughness_m,
            "canopy_cover_percent": self.canopy_cover_percent,
            "aspect_degrees": self.aspect_degrees,
            "landing_slope_percent": self.landing_slope_percent,
            "landing_roughness_m": self.landing_roughness_m,
            "cost_context": {
                "move_in_multiplier": self.move_in_multiplier,
                "landing_multiplier": self.landing_multiplier,
                "road_multiplier": self.road_multiplier,
                "basis": "advisory; not applied by the FHOPS solver in P14.4",
            },
            "reasons": list(self.reasons),
        }


def assess_scenario_operability(
    scenario: Scenario, *, rules: OperabilityRules | None = None
) -> tuple[BlockOperability, ...]:
    """Assess every block in a scenario."""
    return tuple(
        assess_block_operability(scenario, block.id, rules=rules) for block in scenario.blocks
    )


def assess_block_operability(
    scenario: Scenario,
    block_id: str,
    *,
    rules: OperabilityRules | None = None,
) -> BlockOperability:
    """Classify one block from LiDAR support, block fields, and explicit fallbacks."""
    rules = rules or OperabilityRules()
    block = next((item for item in scenario.blocks if item.id == block_id), None)
    if block is None:
        raise KeyError(f"Unknown block_id={block_id}")
    block_rows = [
        row
        for row in (scenario.lidar_support or [])
        if row.support_unit == "block" and row.support_id == block.id
    ]
    landing_rows = [
        row
        for row in (scenario.lidar_support or [])
        if row.support_unit == "landing" and row.support_id == block.landing_id
    ]
    fallbacks: list[str] = []

    slope, slope_source = _value(
        block_rows,
        "slope_percent",
        fallback=block.ground_slope_percent,
        fallback_label="block.ground_slope_percent",
        default=rules.fallback_slope_percent,
        default_label="class_average_slope",
        fallbacks=fallbacks,
    )
    roughness, roughness_source = _value(
        block_rows,
        "roughness_m",
        fallback=None,
        fallback_label="",
        default=rules.fallback_roughness_m,
        default_label="class_average_roughness",
        fallbacks=fallbacks,
    )
    canopy = _optional_value(block_rows, "canopy_cover_percent")
    aspect = _optional_value(block_rows, "aspect_degrees")
    landing_slope = _optional_value(landing_rows, "slope_percent")
    landing_roughness = _optional_value(landing_rows, "roughness_m")
    evaluation_slope = max(slope, landing_slope or 0.0)
    evaluation_roughness = max(roughness, landing_roughness or 0.0)

    terrain_class: TerrainClass
    reasons: list[str] = []
    if (
        evaluation_slope >= rules.cable_max_slope_percent
        or evaluation_roughness >= rules.cable_max_roughness_m
    ):
        terrain_class = "helicopter"
        reasons.append(
            f"slope {evaluation_slope:.1f}% or roughness {evaluation_roughness:.3f} m "
            "exceeds the cable threshold; helicopter class is explicit."
        )
    elif (
        evaluation_slope >= rules.ground_max_slope_percent
        or evaluation_roughness >= rules.ground_max_roughness_m
    ):
        terrain_class = "cable"
        reasons.append(
            f"slope {evaluation_slope:.1f}% or roughness {evaluation_roughness:.3f} m "
            "exceeds the ground threshold."
        )
    else:
        terrain_class = "ground"
        reasons.append(
            f"slope {evaluation_slope:.1f}% and roughness {evaluation_roughness:.3f} m "
            "are within the ground threshold."
        )

    registry = dict(default_system_registry())
    if scenario.harvest_systems:
        registry.update(scenario.harvest_systems)
    current = registry.get(block.harvest_system_id) if block.harvest_system_id else None
    current_class = _system_class(current.environment if current else None, block.harvest_system_id)
    compatible = None if current_class is None else current_class == terrain_class
    recommended = (
        block.harvest_system_id
        if compatible and block.harvest_system_id
        else _recommended_system(terrain_class, registry)
    )
    source = slope_source if slope_source != "class_average_slope" else roughness_source
    if source == "class_average_roughness" and slope_source != "class_average_slope":
        source = slope_source
    move_in = 1.0 + evaluation_slope / 200.0 + evaluation_roughness * 0.5
    landing = 1.0 + (landing_slope or evaluation_slope) / 250.0 + (canopy or 0.0) / 250.0
    road = 1.0 + evaluation_slope / 150.0 + evaluation_roughness * 0.75
    return BlockOperability(
        block_id=block.id,
        landing_id=block.landing_id,
        terrain_class=terrain_class,
        current_system_id=block.harvest_system_id,
        current_system_class=current_class,
        current_system_compatible=compatible,
        recommended_system_id=recommended,
        evidence_source=source,
        fallbacks=tuple(dict.fromkeys(fallbacks)),
        slope_percent=evaluation_slope,
        roughness_m=evaluation_roughness,
        canopy_cover_percent=canopy,
        aspect_degrees=aspect,
        landing_slope_percent=landing_slope,
        landing_roughness_m=landing_roughness,
        move_in_multiplier=move_in,
        landing_multiplier=landing,
        road_multiplier=road,
        reasons=tuple(reasons),
    )


def _value(
    rows,
    field: str,
    *,
    fallback: float | None,
    fallback_label: str,
    default: float,
    default_label: str,
    fallbacks: list[str],
) -> tuple[float, str]:
    value = _optional_value(rows, field)
    if value is not None:
        return value, f"lidar:{rows[0].support_unit}"
    if fallback is not None:
        if fallback_label:
            fallbacks.append(fallback_label)
        return float(fallback), fallback_label
    fallbacks.append(default_label)
    return default, default_label


def _optional_value(rows, field: str) -> float | None:
    for row in rows:
        value = getattr(row, field, None)
        if value is not None:
            return float(value)
    return None


def _system_class(environment: str | None, system_id: str | None = None) -> TerrainClass | None:
    text = f"{environment or ''} {system_id or ''}".lower()
    if not text.strip():
        return None
    if "helicopter" in text or "heli" in text:
        return "helicopter"
    if "cable" in text or "steep" in text:
        return "cable"
    if "ground" in text or "ctl" in text or "thinning" in text:
        return "ground"
    return None


def _recommended_system(terrain_class: TerrainClass, registry: dict) -> str:
    preferred = {
        "ground": "ground_fb_skid",
        "cable": "cable_running_tr122_clearcut",
        "helicopter": "helicopter",
    }[terrain_class]
    if preferred in registry:
        return preferred
    for system_id, system in registry.items():
        if _system_class(system.environment, system_id) == terrain_class:
            return system_id
    raise KeyError(f"No registered harvest system for terrain class {terrain_class!r}")
