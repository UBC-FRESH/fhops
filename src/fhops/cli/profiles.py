"""Solver configuration profiles exposed via the CLI."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field

from fhops.cli._utils import resolve_operator_presets


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
    version: str = "1.0.0"
    sa: SolverConfig = field(default_factory=SolverConfig)
    ils: SolverConfig = field(default_factory=SolverConfig)
    tabu: SolverConfig = field(default_factory=SolverConfig)
    bench: SolverConfig = field(default_factory=SolverConfig)


@dataclass(frozen=True)
class ResolvedSolverConfig:
    """Resolved solver configuration after merging profile defaults and CLI overrides."""

    operators: list[str] | None
    operator_weights: dict[str, float]
    batch_neighbours: int | None
    parallel_workers: int | None
    parallel_multistart: int | None
    extra_kwargs: dict[str, object]


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


def merge_profile_with_cli(
    config: SolverConfig | None,
    preset_args: Sequence[str] | None,
    operator_weight_override: Mapping[str, float],
    explicit_ops: Sequence[str],
    batch_neighbours: int | None,
    parallel_workers: int | None,
    parallel_multistart: int | None,
) -> ResolvedSolverConfig:
    """Merge profile defaults with CLI-provided options."""

    ops_pipeline: list[str] = []
    combined_weights: dict[str, float] = {}
    extra_kwargs: dict[str, object] = {}

    if config is not None:
        if config.operator_presets:
            profile_ops, profile_weights = resolve_operator_presets(list(config.operator_presets))
            if profile_ops:
                ops_pipeline.extend(op.lower() for op in profile_ops)
            combined_weights.update({k.lower(): float(v) for k, v in profile_weights.items()})
        if config.operator_weights:
            combined_weights.update(
                {k.lower(): float(v) for k, v in config.operator_weights.items()}
            )
        if config.extra_kwargs:
            extra_kwargs.update(config.extra_kwargs)

    if preset_args:
        preset_ops, preset_weight_map = resolve_operator_presets(list(preset_args))
        if preset_ops:
            ops_pipeline.extend(op.lower() for op in preset_ops)
        combined_weights.update({k.lower(): float(v) for k, v in preset_weight_map.items()})

    ops_pipeline.extend(op.lower() for op in explicit_ops)
    operators = list(dict.fromkeys(ops_pipeline)) or None

    weights = {k.lower(): float(v) for k, v in combined_weights.items()}
    for key, value in operator_weight_override.items():
        weights[key.lower()] = float(value)

    final_batch = batch_neighbours if batch_neighbours and batch_neighbours > 1 else None
    if config and config.batch_neighbours and final_batch is None:
        final_batch = config.batch_neighbours

    final_workers = parallel_workers if parallel_workers and parallel_workers > 1 else None
    if config and config.parallel_workers and final_workers is None:
        final_workers = config.parallel_workers

    final_multistart = (
        parallel_multistart if parallel_multistart and parallel_multistart > 1 else None
    )
    if config and config.parallel_multistart and final_multistart is None:
        final_multistart = config.parallel_multistart

    return ResolvedSolverConfig(
        operators=operators,
        operator_weights=weights,
        batch_neighbours=final_batch,
        parallel_workers=final_workers,
        parallel_multistart=final_multistart,
        extra_kwargs=dict(extra_kwargs),
    )


def solver_config_has_settings(config: SolverConfig | None) -> bool:
    if not config:
        return False
    if config.operator_presets:
        return True
    if config.operator_weights:
        return True
    if config.batch_neighbours and config.batch_neighbours > 1:
        return True
    if config.parallel_workers and config.parallel_workers > 1:
        return True
    if config.parallel_multistart and config.parallel_multistart > 1:
        return True
    if config.extra_kwargs:
        return True
    return False


def combine_solver_configs(*configs: SolverConfig | None) -> SolverConfig | None:
    filtered: list[SolverConfig] = [
        cfg for cfg in configs if cfg is not None and solver_config_has_settings(cfg)
    ]
    if not filtered:
        return None

    presets: list[str] = []
    weights: MutableMapping[str, float] = {}
    batch: int | None = None
    workers: int | None = None
    multistart: int | None = None
    extra: MutableMapping[str, object] = {}

    for cfg in filtered:
        presets.extend(cfg.operator_presets)
        if cfg.operator_weights:
            weights.update({k.lower(): float(v) for k, v in cfg.operator_weights.items()})
        if cfg.batch_neighbours:
            batch = cfg.batch_neighbours
        if cfg.parallel_workers:
            workers = cfg.parallel_workers
        if cfg.parallel_multistart:
            multistart = cfg.parallel_multistart
        if cfg.extra_kwargs:
            extra.update(cfg.extra_kwargs)

    return SolverConfig(
        operator_presets=tuple(presets),
        operator_weights=dict(weights) if weights else None,
        batch_neighbours=batch,
        parallel_workers=workers,
        parallel_multistart=multistart,
        extra_kwargs=dict(extra),
    )


def format_profiles() -> str:
    lines = []
    for profile in list_profiles():
        lines.append(f"{profile.name}: {profile.description}")
    return "\n".join(lines)


__all__ = [
    "SolverConfig",
    "Profile",
    "ResolvedSolverConfig",
    "DEFAULT_PROFILES",
    "get_profile",
    "list_profiles",
    "merge_profile_with_cli",
    "format_profiles",
    "solver_config_has_settings",
    "combine_solver_configs",
]
