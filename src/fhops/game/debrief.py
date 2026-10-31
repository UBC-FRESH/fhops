"""Fact-grounded post-level debrief for the serious game."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .explain_cache import ExplanationCache, explanation_key

__all__ = [
    "DebriefFacts",
    "build_debrief_facts",
    "render_template_debrief",
    "explain_debrief",
]

PARAMETERS = (
    "care_level",
    "skidder_count",
    "log_length_m",
    "sawlog_min_dbh_cm",
    "road_extension_m",
)
COMPONENTS = (
    "gross_log_value",
    "machine_cost",
    "care_premium",
    "residual_damage_loss",
    "mobilisation_cost",
    "road_extension_cost",
    "net_profit",
)


@dataclass(frozen=True, slots=True)
class DebriefFacts:
    """Validated facts shown after a level is completed."""

    level_id: str
    player_choices: dict[str, Any]
    optimal_choices: dict[str, Any]
    player_net_profit: float
    optimal_net_profit: float
    score: float
    component_deltas: dict[str, float]
    parameter_deltas: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "level_id": self.level_id,
            "player_choices": dict(self.player_choices),
            "optimal_choices": dict(self.optimal_choices),
            "player_net_profit": self.player_net_profit,
            "optimal_net_profit": self.optimal_net_profit,
            "score": self.score,
            "component_deltas": dict(self.component_deltas),
            "parameter_deltas": [dict(item) for item in self.parameter_deltas],
        }


def _matches(record: dict[str, Any], choices: dict[str, Any]) -> bool:
    for key in PARAMETERS:
        value = choices.get(key)
        if value is None:
            continue
        record_value = record[key]
        if key in {"skidder_count"}:
            if int(record_value) != int(value):
                return False
        elif not math.isclose(float(record_value), float(value), abs_tol=1e-9):
            return False
    return True


def _record_for(precompute: dict[str, Any], choices: dict[str, Any]) -> dict[str, Any]:
    for record in precompute["variants"]:
        if _matches(record, choices):
            return record
    raise ValueError("No precomputed variant matches the supplied choices.")


def build_debrief_facts(
    precompute: dict[str, Any],
    *,
    player_choices: dict[str, Any],
    score: float,
) -> DebriefFacts:
    """Build deterministic debrief facts from the level's precompute."""
    player_record = _record_for(precompute, player_choices)
    optimal_choices = dict(precompute["bounds"]["best_choices"])
    optimal_record = _record_for(precompute, optimal_choices)
    player_result = player_record["result"]
    optimal_result = optimal_record["result"]
    component_deltas = {
        component: float(player_result.get(component, 0.0))
        - float(optimal_result.get(component, 0.0))
        for component in COMPONENTS
    }
    parameter_deltas: list[dict[str, Any]] = []
    for parameter in PARAMETERS:
        player_value = player_choices.get(parameter)
        optimal_value = optimal_choices.get(parameter)
        if player_value is None or optimal_value is None:
            continue
        if parameter == "skidder_count":
            changed = int(player_value) != int(optimal_value)
        else:
            changed = not math.isclose(float(player_value), float(optimal_value), abs_tol=1e-9)
        if not changed:
            continue
        alternate = dict(player_choices)
        alternate[parameter] = optimal_value
        alternate_record = _record_for(precompute, alternate)
        delta = float(alternate_record["net_profit"]) - float(player_record["net_profit"])
        parameter_deltas.append(
            {
                "parameter": parameter,
                "player_value": player_value,
                "optimal_value": optimal_value,
                "net_profit_if_optimal": float(alternate_record["net_profit"]),
                "net_profit_delta": delta,
                "cost_of_wrong": max(0.0, delta),
            }
        )
    parameter_deltas.sort(key=lambda item: item["cost_of_wrong"], reverse=True)
    return DebriefFacts(
        level_id=str(precompute["level_id"]),
        player_choices=dict(player_choices),
        optimal_choices=optimal_choices,
        player_net_profit=float(player_record["net_profit"]),
        optimal_net_profit=float(optimal_record["net_profit"]),
        score=float(score),
        component_deltas=component_deltas,
        parameter_deltas=tuple(parameter_deltas),
    )


def render_template_debrief(facts: DebriefFacts) -> dict[str, Any]:
    """Return a deterministic explanation with no LLM dependency."""
    if facts.parameter_deltas:
        largest = facts.parameter_deltas[0]
        cost_text = (
            f"The largest miss was {largest['parameter']} "
            f"({largest['player_value']} instead of {largest['optimal_value']}), "
            f"which cost ${largest['cost_of_wrong']:,.2f} in net profit."
        )
    else:
        cost_text = "Your plan matched the best finite control combination."
    why = (
        f"The best plan earned ${facts.optimal_net_profit:,.2f} net profit; "
        f"your plan earned ${facts.player_net_profit:,.2f} and scored "
        f"{facts.score:.1f}/100. {cost_text}"
    )
    return {
        "why_optimal": why,
        "parameter_costs": {
            item["parameter"]: (
                f"Choosing {item['optimal_value']} instead of {item['player_value']} "
                f"would have changed net profit by ${item['net_profit_delta']:,.2f}."
            )
            for item in facts.parameter_deltas
        },
        "source": "deterministic_template",
    }


def explain_debrief(
    facts: DebriefFacts,
    *,
    llm_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Use an optional LLM explanation, falling back to the template."""
    fallback = render_template_debrief(facts)
    if llm_fn is None:
        return fallback
    try:
        candidate = llm_fn(facts.to_dict())
        if not isinstance(candidate, dict):
            return fallback
        why = candidate.get("why_optimal")
        costs = candidate.get("parameter_costs")
        if not isinstance(why, str) or not why.strip():
            return fallback
        if not isinstance(costs, dict):
            return fallback
        # Numeric claims in the template are generated only from facts; reject
        # extra numeric-looking keys rather than trusting free-form prose.
        allowed = set(facts.parameter_deltas[0].keys()) if facts.parameter_deltas else set()
        if allowed and any(
            key not in {item["parameter"] for item in facts.parameter_deltas} for key in costs
        ):
            return fallback
        return {
            "why_optimal": why,
            "parameter_costs": {str(key): str(value) for key, value in costs.items()},
            "source": "llm",
        }
    except Exception:
        return fallback


def explain_debrief_cached(
    facts: DebriefFacts,
    *,
    cache: ExplanationCache | None = None,
    llm_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Explain a debrief with stable level+choice caching."""
    if cache is not None:
        key = explanation_key(facts.level_id, facts.player_choices)
        cached = cache.get(key)
        if cached is not None:
            return cached
    payload = explain_debrief(facts, llm_fn=llm_fn)
    if cache is not None:
        cache.put(explanation_key(facts.level_id, facts.player_choices), payload)
    return payload
