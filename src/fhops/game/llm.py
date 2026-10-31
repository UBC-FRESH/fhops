"""Prompt/response helpers for the optional debrief LLM."""

from __future__ import annotations

import json
from typing import Any

__all__ = [
    "DEEPSEEK_GAME_MODEL",
    "build_debrief_prompt",
    "format_facts_for_prompt",
    "parse_debrief_response",
]

DEEPSEEK_GAME_MODEL = "opencode-go/deepseek-v4.1-flash"

_MONEY_KEYS = {
    "player_net_profit",
    "optimal_net_profit",
    "cost_of_wrong",
    "net_profit_if_optimal",
    "net_profit_delta",
}
_VOLUME_KEYS = {"volume_m3", "processed_volume_m3"}
_CHOICE_KEYS = {
    "care_level",
    "skidder_count",
    "log_length_m",
    "sawlog_min_dbh_cm",
    "road_extension_m",
}


def format_facts_for_prompt(value: Any, key: str | None = None) -> Any:
    """Round a facts payload to presentation precision before prompting."""
    if isinstance(value, dict):
        return {str(k): format_facts_for_prompt(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [format_facts_for_prompt(item, key) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        if key in _MONEY_KEYS:
            return round(float(value))
        if key == "score":
            return round(float(value), 1)
        if key in _VOLUME_KEYS:
            return round(float(value), 1)
        if key in _CHOICE_KEYS:
            return round(float(value), 2)
        return round(float(value), 2)
    return value


def build_debrief_prompt(facts: dict[str, Any]) -> str:
    """Build a strict JSON-only explanation prompt from deterministic facts."""
    return (
        "You are the FHOPS serious-game debrief coach. Explain the result using "
        "ONLY the facts in the JSON below. Write for a student: never mention JSON "
        "field names, snake_case names, raw floats, or implementation details. "
        "Do not include any digits, dollar amounts, percentages, or parameter "
        "values; numeric details are shown separately by the UI. Do not add new "
        "numeric claims, do not change the optimal choice, and do not give "
        "operational advice beyond the supplied facts. Return ONLY one "
        "JSON object with exactly these keys:\n"
        '{"why_optimal": "concise explanation", "parameter_costs": {"parameter": "explanation"}}\n'
        "Facts:\n"
        + json.dumps(format_facts_for_prompt(facts), sort_keys=True, separators=(",", ":"))
    )


def parse_debrief_response(text: str) -> dict[str, Any]:
    """Extract a JSON object from an agent response."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError("Debrief agent did not return valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Debrief agent response must be a JSON object.")
    if not isinstance(payload.get("why_optimal"), str):
        raise ValueError("Debrief agent response needs why_optimal.")
    if not isinstance(payload.get("parameter_costs"), dict):
        raise ValueError("Debrief agent response needs parameter_costs.")
    return payload
