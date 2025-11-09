"""Solver configuration profiles exposed via the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class SolverConfig:
    """Configuration snippet applied to a solver invocation."""

    operator_presets: tuple[str, ...] = ()
    operator_weights: Mapping[str, float] | None = None
    batch_neighbours: int | None = None
    parallel_workers: int | None = None
    parallel_multistart: int | None = None
    extra_kwargs: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Profile:
    """Named solver profile spanning SA, ILS, Tabu, and benchmarking defaults."""

    name: str
    description: str
    sa: SolverConfig = field(default_factory=SolverConfig)
    ils: SolverConfig = field(default_factory=SolverConfig)
    tabu: SolverConfig = field(default_factory=SolverConfig)
    bench: SolverConfig = field(default_factory=SolverConfig)


DEFAULT_PROFILES: dict[str, Profile] = {
    "default": Profile(
        name="default",
        description="Balanced SA configuration (swap/move) with conservative batching.",
        sa=SolverConfig(operator_presets=("balanced",)),
        ils=SolverConfig(operator_presets=("balanced",)),
        tabu=SolverConfig(operator_presets=("balanced",)),
    ),
    "explore": Profile(
        name="explore",
        description="Enable advanced neighbourhoods to diversify search.",
        sa=SolverConfig(operator_presets=("explore",)),
        ils=SolverConfig(operator_presets=("explore",)),
        tabu=SolverConfig(operator_presets=("explore",)),
    ),
    "mobilisation": Profile(
        name="mobilisation",
        description="Bias towards mobilisation-aware moves to escape distance constraints.",
        sa=SolverConfig(operator_presets=("mobilisation",)),
        ils=SolverConfig(
            operator_presets=("mobilisation",),
            parallel_workers=2,
        ),
        tabu=SolverConfig(operator_presets=("mobilisation",)),
    ),
    "stabilise": Profile(
        name="stabilise",
        description="Focus on consolidation/minimal mobilisation; good for cleanup passes.",
        sa=SolverConfig(operator_presets=("stabilise",)),
        ils=SolverConfig(operator_presets=("stabilise",)),
        tabu=SolverConfig(operator_presets=("stabilise",)),
    ),
    "parallel-explore": Profile(
        name="parallel-explore",
        description="Parallel multi-start SA with diversified neighbourhoods.",
        sa=SolverConfig(
            operator_presets=("explore",),
            batch_neighbours=4,
            parallel_workers=4,
            parallel_multistart=4,
        ),
        bench=SolverConfig(
            operator_presets=("explore",),
            batch_neighbours=4,
            parallel_workers=4,
            parallel_multistart=4,
        ),
    ),
    "intense-diversify": Profile(
        name="intense-diversify",
        description="Aggressive diversification plus mobilisation shake for large scenarios.",
        sa=SolverConfig(
            operator_presets=("explore", "mobilisation"),
            batch_neighbours=8,
            parallel_workers=4,
        ),
        ils=SolverConfig(
            operator_presets=("explore", "mobilisation"),
            batch_neighbours=4,
            parallel_workers=4,
            extra_kwargs={"perturbation_strength": 5},
        ),
        tabu=SolverConfig(
            operator_presets=("explore", "mobilisation"),
            extra_kwargs={"tabu_tenure": 30},
        ),
    ),
}


def get_profile(name: str) -> Profile:
    key = name.lower()
    if key not in DEFAULT_PROFILES:
        available = ", ".join(sorted(DEFAULT_PROFILES))
        raise KeyError(f"Unknown profile '{name}'. Available: {available}")
    return DEFAULT_PROFILES[key]


def list_profiles() -> tuple[Profile, ...]:
    return tuple(DEFAULT_PROFILES[key] for key in sorted(DEFAULT_PROFILES))


__all__ = ["SolverConfig", "Profile", "DEFAULT_PROFILES", "get_profile", "list_profiles"]
