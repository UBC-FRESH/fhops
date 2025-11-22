from __future__ import annotations

import pytest

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


def test_system_productivity_overrides_skyline_micro_ecologger() -> None:
    systems = default_system_registry()
    system = systems["cable_micro_ecologger"]
    overrides = system_productivity_overrides(system, "skyline_yarder")
    assert overrides is not None
    assert overrides["skyline_model"] == "tn173-ecologger"


def test_system_productivity_overrides_hi_skid() -> None:
    systems = default_system_registry()
    system = systems["cable_micro_hi_skid"]
    overrides = system_productivity_overrides(system, "skyline_yarder")
    assert overrides is not None
    assert overrides["skyline_model"] == "hi-skid"


def test_system_productivity_overrides_tr125_strip() -> None:
    systems = default_system_registry()
    system = systems["cable_standing_tr125_strip"]
    overrides = system_productivity_overrides(system, "skyline_yarder")
    assert overrides is not None
    assert overrides["skyline_model"] == "tr125-multi-span"
    assert overrides["skyline_lateral_distance_m"] == pytest.approx(40.0)
    assert overrides["tr119_treatment"] == "strip_cut"


def test_system_productivity_overrides_tr127_block5() -> None:
    systems = default_system_registry()
    system = systems["cable_partial_tr127_block5"]
    overrides = system_productivity_overrides(system, "skyline_yarder")
    assert overrides is not None
    assert overrides["skyline_model"] == "tr127-block5"
    assert overrides["skyline_num_logs"] == pytest.approx(3.0)
    assert overrides["skyline_lateral_distance_m"] == pytest.approx(16.0)
    assert overrides["partial_cut_profile"] == "sr109_green_tree"


def test_system_productivity_overrides_tr127_block1_profile() -> None:
    systems = default_system_registry()
    system = systems["cable_partial_tr127_block1"]
    overrides = system_productivity_overrides(system, "skyline_yarder")
    assert overrides is not None
    assert overrides["partial_cut_profile"] == "sr109_patch_cut"


def test_system_productivity_overrides_cable_running_fncy12() -> None:
    systems = default_system_registry()
    system = systems["cable_running_fncy12"]
    overrides = system_productivity_overrides(system, "skyline_yarder")
    assert overrides is not None
    assert overrides["skyline_model"] == "fncy12-tmy45"
