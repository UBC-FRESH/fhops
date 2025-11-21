from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

import yaml

from fhops.scenario.synthetic import SyntheticDatasetConfig, generate_random_dataset
from fhops.scheduling.systems import default_system_registry

console = Console()
synth_app = typer.Typer(no_args_is_help=True, help="Generate synthetic FHOPS scenarios.")

TIER_PRESETS: dict[str, SyntheticDatasetConfig] = {
    "small": SyntheticDatasetConfig(
        name="synthetic-small",
        tier="small",
        num_blocks=(4, 4),
        num_days=(6, 6),
        num_machines=(2, 2),
        num_landings=(1, 1),
        shifts_per_day=1,
    ),
    "medium": SyntheticDatasetConfig(
        name="synthetic-medium",
        tier="medium",
        num_blocks=(8, 8),
        num_days=(12, 12),
        num_machines=(4, 4),
        num_landings=(2, 2),
        shifts_per_day=1,
    ),
    "large": SyntheticDatasetConfig(
        name="synthetic-large",
        tier="large",
        num_blocks=(16, 16),
        num_days=(18, 18),
        num_machines=(6, 6),
        num_landings=(3, 3),
        shifts_per_day=2,
    ),
}

TIER_SEEDS: dict[str, int] = {
    "small": 101,
    "medium": 202,
    "large": 303,
}


def _parse_range(value: str) -> tuple[int, int]:
    try:
        lo, hi = value.split(":")
        return int(lo), int(hi)
    except Exception as exc:  # pragma: no cover - defensive
        raise typer.BadParameter("Expected range in the form 'min:max'.") from exc


def _load_config(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix == ".toml":
        if tomllib is None:  # pragma: no cover - Python < 3.11
            raise typer.BadParameter("TOML support requires Python 3.11+")
        return tomllib.loads(path.read_text(encoding="utf-8"))
    raise typer.BadParameter("Unsupported config format. Use YAML, TOML, or JSON.")


def _merge_config(
    base: SyntheticDatasetConfig,
    overrides: dict[str, Any],
) -> SyntheticDatasetConfig:
    data = asdict(base)
    for key, value in overrides.items():
        if key == "seed":
            continue
        if key in {"num_blocks", "num_days", "num_machines", "num_landings", "landing_capacity"}:
            if isinstance(value, list | tuple) and len(value) == 2:
                data[key] = tuple(int(part) for part in value)
            elif isinstance(value, str) and ":" in value:
                data[key] = _parse_range(value)
            else:
                data[key] = int(value)
        elif key in {"shift_hours", "work_required", "production_rate"}:
            if isinstance(value, list | tuple) and len(value) == 2:
                data[key] = (float(value[0]), float(value[1]))
            elif isinstance(value, str) and ":" in value:
                lo, hi = value.split(":")
                data[key] = (float(lo), float(hi))
            else:
                raise typer.BadParameter(f"{key} expects a two-value range.")
        elif key in {"crew_capability_span"}:
            if isinstance(value, list | tuple) and len(value) == 2:
                data[key] = (int(value[0]), int(value[1]))
            else:
                raise typer.BadParameter(f"{key} expects a two-value range.")
        elif key == "machine_daily_hours":
            data[key] = float(value)
        else:
            data[key] = value
    return SyntheticDatasetConfig(**data)


def _resolve_cli_overrides(
    blocks: str | None,
    machines: str | None,
    landings: str | None,
    days: str | None,
    shifts_per_day: int | None,
    machine_daily_hours: float | None,
) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if blocks:
        overrides["num_blocks"] = blocks
    if machines:
        overrides["num_machines"] = machines
    if landings:
        overrides["num_landings"] = landings
    if days:
        overrides["num_days"] = days
    if shifts_per_day is not None:
        overrides["shifts_per_day"] = shifts_per_day
    if machine_daily_hours is not None:
        overrides["machine_daily_hours"] = machine_daily_hours
    return overrides


def _describe_metadata(metadata: dict[str, Any]) -> None:
    console.print("[bold]Synthetic Dataset Summary[/bold]")
    console.print(f"Name: {metadata.get('name')}")
    console.print(f"Tier: {metadata.get('tier')}")
    console.print(f"Seed: {metadata.get('seed')}")
    counts = metadata.get("counts", {})
    console.print("Counts: " + ", ".join(f"{key}={counts[key]}" for key in sorted(counts)))
    terrain = metadata.get("terrain_counts") or {}
    prescription = metadata.get("prescription_counts") or {}
    console.print(
        "Terrain mix: " + (", ".join(f"{k}={terrain[k]}" for k in sorted(terrain)) or "n/a")
    )
    console.print(
        "Prescription mix: "
        + (", ".join(f"{k}={prescription[k]}" for k in sorted(prescription)) or "n/a")
    )
    console.print(f"Blackouts: {len(metadata.get('blackouts', []))}")
    system_mix = metadata.get("system_mix") or {}
    if system_mix:
        console.print(
            "System mix: " + ", ".join(f"{k}={system_mix[k]:.2f}" for k in sorted(system_mix))
        )
    biases = metadata.get("blackout_biases") or []
    if biases:
        bias_summary = ", ".join(
            f"{bias['start_day']}-{bias['end_day']}@{bias['probability']:.2f}" for bias in biases
        )
        console.print(f"Blackout biases: {bias_summary}")
    sampling = metadata.get("sampling_config") or {}
    if sampling:
        downtime = sampling.get("downtime", {})
        weather = sampling.get("weather", {})
        landing = sampling.get("landing", {})
        console.print(
            "Sampling preset: "
            f"samples={sampling.get('samples')} "
            f"downtime={'on' if downtime.get('enabled') else 'off'} "
            f"weather={'on' if weather.get('enabled') else 'off'} "
            f"landing={'on' if landing.get('enabled') else 'off'}"
        )


def _refresh_aggregate_metadata(base_dir: Path) -> None:
    aggregate: dict[str, Any] = {}
    for child in sorted(base_dir.iterdir()):
        if not child.is_dir():
            continue
        metadata_file = child / "metadata.yaml"
        scenario_file = child / "scenario.yaml"
        if not metadata_file.exists() or not scenario_file.exists():
            continue
        data = yaml.safe_load(metadata_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        scenario_payload = yaml.safe_load(scenario_file.read_text(encoding="utf-8"))
        if isinstance(scenario_payload, dict) and "num_days" in scenario_payload:
            data = {**data, "num_days": scenario_payload["num_days"]}
        aggregate[child.name] = data
    if aggregate:
        with (base_dir / "metadata.yaml").open("w", encoding="utf-8") as handle:
            yaml.safe_dump(aggregate, handle, sort_keys=False)


def _maybe_refresh_metadata(target_dir: Path) -> None:
    base_dir = Path("examples/synthetic").resolve()
    try:
        target_dir.resolve().relative_to(base_dir)
    except ValueError:
        return
    _refresh_aggregate_metadata(base_dir)


def _resolve_dataset_inputs(
    tier: str,
    config_path: Path | None,
    config_overrides: dict[str, Any],
    cli_overrides: dict[str, Any],
    seed: int | None,
) -> tuple[SyntheticDatasetConfig, int]:
    tier = (tier or "small").lower()
    if tier not in TIER_PRESETS and tier != "custom":
        raise typer.BadParameter(
            f"Unknown tier '{tier}'. Valid options: {', '.join(TIER_PRESETS)}."
        )

    base_config = TIER_PRESETS.get(
        tier,
        SyntheticDatasetConfig(
            name="synthetic-custom",
            tier=None,
            num_blocks=(8, 12),
            num_days=(12, 16),
            num_machines=(4, 6),
            num_landings=(2, 3),
        ),
    )

    config_data: dict[str, Any] = {}
    if config_path is not None:
        config_data = _load_config(config_path)
        if not isinstance(config_data, dict):
            raise typer.BadParameter("Config file must yield a mapping/dictionary.")

    merged = _merge_config(base_config, config_data)
    merged = _merge_config(merged, config_overrides)
    merged = _merge_config(merged, cli_overrides)

    seed_value = seed
    if seed_value is None and "seed" in config_data:
        seed_value = int(config_data["seed"])
    if seed_value is None and "seed" in config_overrides:
        seed_value = int(config_overrides["seed"])
    if seed_value is None and "seed" in cli_overrides:
        seed_value = int(cli_overrides["seed"])
    if seed_value is None:
        seed_value = TIER_SEEDS.get(tier, 123)

    return merged, seed_value


def _generate_dataset(
    *,
    output_dir: Path | None,
    tier: str,
    config_path: Path | None,
    seed: int | None,
    config_overrides: dict[str, Any] | None,
    cli_overrides: dict[str, Any] | None,
    overwrite: bool,
    preview: bool,
) -> dict[str, Any]:
    merged_config, seed_value = _resolve_dataset_inputs(
        tier,
        config_path,
        config_overrides or {},
        cli_overrides or {},
        seed,
    )
    system_registry = dict(default_system_registry())
    bundle = generate_random_dataset(merged_config, seed=seed_value, systems=system_registry)

    metadata = bundle.metadata or {}
    metadata = {
        **metadata,
        "seed": seed_value,
    }

    if preview:
        _describe_metadata(metadata)
        return metadata

    target_dir = output_dir
    if target_dir is None:
        target_dir = Path("examples/synthetic") / (merged_config.tier or merged_config.name)
    if target_dir.exists():
        if not overwrite:
            console.print(
                f"[red]Directory {target_dir} already exists. Use --overwrite to replace.[/red]"
            )
            raise typer.Exit(1)
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = target_dir / "metadata.yaml"
    bundle.metadata = metadata
    bundle.write(target_dir, metadata_path=metadata_path)

    console.print(f"[green]Synthetic dataset written to {target_dir}[/green]")
    _describe_metadata(metadata)
    _maybe_refresh_metadata(target_dir)
    return metadata


@synth_app.command("generate")
def generate_synthetic_dataset(
    output_dir: Path = typer.Argument(
        None, help="Directory to write the bundle (defaults to examples/synthetic/<tier>)."
    ),
    tier: str = typer.Option(
        "small",
        "--tier",
        case_sensitive=False,
        help="Preset tier to seed the configuration. Use 'custom' to start from defaults only.",
    ),
    config: Path = typer.Option(
        None,
        "--config",
        help="Optional config file (YAML/TOML/JSON) overriding SyntheticDatasetConfig fields.",
    ),
    seed: int = typer.Option(
        None,
        "--seed",
        help="RNG seed. Defaults to tier preset (if available) or 123.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Overwrite existing directory if it already exists.",
    ),
    preview: bool = typer.Option(
        False,
        "--preview",
        help="Print summary without writing files.",
    ),
    blocks: str = typer.Option(
        None,
        "--blocks",
        help="Override block count (int) or range 'min:max'.",
    ),
    machines: str = typer.Option(
        None,
        "--machines",
        help="Override machine count (int) or range 'min:max'.",
    ),
    landings: str = typer.Option(
        None,
        "--landings",
        help="Override landing count (int) or range 'min:max'.",
    ),
    days: str = typer.Option(
        None,
        "--days",
        help="Override horizon length (int) or range 'min:max'.",
    ),
    shifts_per_day: int = typer.Option(
        None,
        "--shifts-per-day",
        min=1,
        help="Override shifts per day.",
    ),
    machine_daily_hours: float | None = typer.Option(
        None,
        "--machine-daily-hours",
        min=0.0,
        help="Override daily hours assigned to each generated machine.",
    ),
):
    cli_overrides = _resolve_cli_overrides(
        blocks, machines, landings, days, shifts_per_day, machine_daily_hours
    )
    _generate_dataset(
        output_dir=output_dir,
        tier=tier,
        config_path=config,
        seed=seed,
        config_overrides={},
        cli_overrides=cli_overrides,
        overwrite=overwrite,
        preview=preview,
    )


@synth_app.command("batch")
def generate_batch(
    plan: Path = typer.Argument(
        ..., help="YAML/TOML/JSON plan file containing a list of bundle entries."
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Overwrite existing bundle directories."
    ),
    preview: bool = typer.Option(
        False, "--preview", help="Preview metadata for all bundles without writing files."
    ),
) -> None:
    payload = _load_config(plan)
    if not isinstance(payload, list):
        raise typer.BadParameter("Batch plan must be a list of bundle entries.")

    for entry in payload:
        if not isinstance(entry, dict):
            raise typer.BadParameter("Each batch entry must be a mapping.")
        tier = entry.get("tier", "small")
        output_dir = entry.get("output_dir")
        output_path = Path(output_dir) if output_dir is not None else None
        config_path = entry.get("config")
        config_path = Path(config_path) if config_path else None
        seed_value = entry.get("seed")
        entry_overrides = entry.get("overrides", {})
        if not isinstance(entry_overrides, dict):
            raise typer.BadParameter("Batch entry 'overrides' must be a mapping.")

        cli_flags = entry.get("flags", {})
        if cli_flags and not isinstance(cli_flags, dict):
            raise typer.BadParameter("Batch entry 'flags' must be a mapping when provided.")

        cli_overrides = _resolve_cli_overrides(
            cli_flags.get("blocks"),
            cli_flags.get("machines"),
            cli_flags.get("landings"),
            cli_flags.get("days"),
            cli_flags.get("shifts_per_day"),
            cli_flags.get("machine_daily_hours"),
        )

        entry_preview = entry.get("preview", preview)
        entry_overwrite = entry.get("overwrite", overwrite)

        console.print(f"[bold]Generating bundle for tier '{tier}'[/bold]")
        _generate_dataset(
            output_dir=output_path,
            tier=tier,
            config_path=config_path,
            seed=seed_value,
            config_overrides=entry_overrides,
            cli_overrides=cli_overrides,
            overwrite=entry_overwrite,
            preview=entry_preview,
        )
