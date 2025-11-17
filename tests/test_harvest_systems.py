from __future__ import annotations

from fhops.productivity.skidder_ft import DeckingCondition, TrailSpacingPattern
from fhops.scheduling.systems import default_system_registry, system_productivity_overrides


def test_system_productivity_overrides_ground_fb_skid() -> None:
    systems = default_system_registry()
    system = systems["ground_fb_skid"]
    overrides = system_productivity_overrides(system, "grapple_skidder")
    assert overrides is not None
    assert overrides["skidder_trail_pattern"] == TrailSpacingPattern.SINGLE_GHOST_18M.value
    assert overrides["skidder_decking_condition"] == DeckingCondition.CONSTRAINED.value


def test_system_productivity_overrides_missing_role() -> None:
    systems = default_system_registry()
    system = systems["ctl"]
    overrides = system_productivity_overrides(system, "grapple_skidder")
    assert overrides is None
