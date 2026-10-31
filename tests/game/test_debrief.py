"""Tests for deterministic debrief facts and explanation fallback."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fhops.game.debrief import build_debrief_facts, explain_debrief, render_template_debrief
from fhops.game.stand_precompute import load_stand_precompute

PRECOMPUTE = Path("examples/game/precomputed/kc_57254551.json")


def test_debrief_reveals_optimal_and_parameter_costs() -> None:
    payload = load_stand_precompute(PRECOMPUTE)
    choices = {
        "care_level": 0.0,
        "skidder_count": 2,
        "log_length_m": 4.9,
        "sawlog_min_dbh_cm": 20.0,
        "road_extension_m": 0.0,
    }
    facts = build_debrief_facts(payload, player_choices=choices, score=0.0)

    assert facts.optimal_choices["care_level"] == 0.5
    assert facts.optimal_choices["log_length_m"] == 6.1
    assert facts.player_net_profit < facts.optimal_net_profit
    assert {item["parameter"] for item in facts.parameter_deltas} >= {
        "care_level",
        "log_length_m",
    }
    assert all(item["cost_of_wrong"] >= 0 for item in facts.parameter_deltas)


def test_explanation_falls_back_without_llm() -> None:
    payload = load_stand_precompute(PRECOMPUTE)
    choices = {
        "care_level": 0.0,
        "skidder_count": 1,
        "log_length_m": 4.9,
        "sawlog_min_dbh_cm": 20.0,
        "road_extension_m": 0.0,
    }
    facts = build_debrief_facts(payload, player_choices=choices, score=0.0)

    assert render_template_debrief(facts)["source"] == "deterministic_template"
    assert explain_debrief(facts)["source"] == "deterministic_template"
    assert "net profit" in explain_debrief(facts)["why_optimal"]


def test_precompute_artifact_is_readable() -> None:
    payload = json.loads(PRECOMPUTE.read_text())
    assert payload["schema_version"] == "fhops.game.stand_precompute.v1"


def test_gap_and_parameter_cost_explain_the_loss() -> None:
    payload = load_stand_precompute(PRECOMPUTE)
    choices = {
        "care_level": 0.25,
        "skidder_count": 1,
        "log_length_m": 6.1,
        "sawlog_min_dbh_cm": 20.0,
        "road_extension_m": 0.0,
    }
    facts = build_debrief_facts(payload, player_choices=choices, score=96.0)
    explanation = render_template_debrief(facts)

    assert facts.optimal_net_profit - facts.player_net_profit == pytest.approx(2128.09, abs=0.01)
    assert facts.parameter_deltas[0]["cost_of_wrong"] == pytest.approx(2128.09, abs=0.01)
    assert "gap to optimal is $2,128" in explanation["why_optimal"]
    assert "$0" not in explanation["why_optimal"]
