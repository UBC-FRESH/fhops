from __future__ import annotations

from pathlib import Path

DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "reference" / "harvest_systems.rst"

# (model substring, machine-rate role substring)
SKYLINE_COST_PAIRS = [
    ("tr125-single-span", "grapple_yarder_skyleadc40"),
    ("fncy12-tmy45", "grapple_yarder_tmy45"),
    ("mcneel-running", "grapple_yarder_cypress7280"),
    ("tn173-ecologger", "skyline_ecologger_tn173"),
    ("tn173-gabriel", "skyline_gabriel_tn173"),
    ("tn173-christie", "skyline_christie_tn173"),
    ("tn173-teletransporteur", "skyline_teletransporteur_tn173"),
    ("tn173-timbermaster-1984", "skyline_timbermaster_tn173"),
    ("hi-skid", "skyline_hi_skid"),
    ("ledoux-skagit-shotgun", "grapple_yarder_skagit_shotgun"),
    ("ledoux-skagit-highlead", "grapple_yarder_skagit_highlead"),
    ("ledoux-washington-208e", "grapple_yarder_washington_208e"),
    ("ledoux-tmy45", "grapple_yarder_tmy45_residue"),
    ("tn147", "grapple_yarder_madill009"),
    ("tn157", "grapple_yarder_cypress7280"),
    ("adv5n28-clearcut", "grapple_yarder_adv5n28"),
]


def test_skyline_cost_matrix_entries_present() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    for model, role in SKYLINE_COST_PAIRS:
        assert model in text, f"Missing skyline preset '{model}' in cost matrix"
        assert role in text, f"Missing machine-rate role '{role}' in cost matrix"
