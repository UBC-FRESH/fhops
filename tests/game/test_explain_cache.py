"""Tests for debrief LLM prompt/response and explanation caching."""

from __future__ import annotations

import json
from pathlib import Path

from fhops.game.debrief import build_debrief_facts, explain_debrief_cached
from fhops.game.explain_cache import ExplanationCache, explanation_key
from fhops.game.llm import DEEPSEEK_GAME_MODEL, build_debrief_prompt, parse_debrief_response
from fhops.game.stand_precompute import load_stand_precompute

PRECOMPUTE = Path("examples/game/precomputed/kc_57254551.json")


def test_deepseek_model_and_prompt_schema() -> None:
    assert DEEPSEEK_GAME_MODEL == "opencode-go/deepseek-v4.1-flash"
    prompt = build_debrief_prompt({"level_id": "kc_57254551", "score": 50.0})
    assert "ONLY one JSON object" in prompt
    assert "why_optimal" in prompt
    assert "parameter_costs" in prompt


def test_response_parser_accepts_fenced_json() -> None:
    parsed = parse_debrief_response(
        '```json\n{"why_optimal": "ok", "parameter_costs": {"care_level": "ok"}}\n```'
    )
    assert parsed["why_optimal"] == "ok"


def test_explanation_cache_hits(tmp_path: Path) -> None:
    payload = load_stand_precompute(PRECOMPUTE)
    choices = {
        "care_level": 0.0,
        "skidder_count": 1,
        "log_length_m": 4.9,
        "sawlog_min_dbh_cm": 20.0,
        "road_extension_m": 0.0,
    }
    facts = build_debrief_facts(payload, player_choices=choices, score=0.0)
    cache_path = tmp_path / "explanations.json"
    cache = ExplanationCache(cache_path)
    calls = {"count": 0}

    def fake_llm(_: dict[str, object]) -> dict[str, object]:
        calls["count"] += 1
        return {"why_optimal": "cached", "parameter_costs": {}}

    first = explain_debrief_cached(facts, cache=cache, llm_fn=fake_llm)
    second = explain_debrief_cached(facts, cache=cache, llm_fn=fake_llm)
    assert first == second
    assert calls["count"] == 1
    stored = json.loads(cache_path.read_text())
    assert explanation_key("kc_57254551", choices) in stored


def test_technical_llm_text_falls_back_to_template() -> None:
    payload = load_stand_precompute(PRECOMPUTE)
    choices = {
        "care_level": 0.0,
        "skidder_count": 1,
        "log_length_m": 4.9,
        "sawlog_min_dbh_cm": 20.0,
        "road_extension_m": 0.0,
    }
    facts = build_debrief_facts(payload, player_choices=choices, score=0.0)
    from fhops.game.debrief import explain_debrief

    result = explain_debrief(
        facts,
        llm_fn=lambda _: {
            "why_optimal": "player_net_profit was 123.456789",
            "parameter_costs": {},
        },
    )
    assert result["source"] == "deterministic_template"


def test_prompt_facts_are_rounded_to_presentation_precision() -> None:
    payload = load_stand_precompute(PRECOMPUTE)
    choices = {
        "care_level": 1.0,
        "skidder_count": 1,
        "log_length_m": 4.9,
        "sawlog_min_dbh_cm": 20.0,
        "road_extension_m": 0.0,
    }
    facts = build_debrief_facts(payload, player_choices=choices, score=0.0)
    prompt = build_debrief_prompt(facts.to_dict())
    assert "75705.62948483122" not in prompt
    assert "21969.10009106162" not in prompt
    assert "75706" in prompt
    assert "21969" in prompt
