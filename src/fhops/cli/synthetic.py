from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Tuple

import typer
from rich.console import Console

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

import yaml

from fhops.scenario.synthetic import SyntheticDatasetConfig, generate_random_dataset

console = Console()
synth_app = typer.Typer(no_args_is_help=True, help="Generate synthetic FHOPS scenarios.")

TIER_PRESETS: Dict[str, SyntheticDatasetConfig] = {
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

TIER_SEEDS: Dict[str, int] = {
    "small": 101,
    "medium": 202,
    "large": 303,
}


def _parse_range(value: str) -> Tuple[int, int]:
    try:
        lo, hi = value.split(":")
        return int(lo), int(hi)
    except Exception as exc:  # pragma: no cover - defensive
        raise typer.BadParameter("Expected range in the form 'min:max'.") from exc


def _load_config(path: Path) -> Dict[str, Any]:
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
    overrides: Dict[str, Any],
) -> SyntheticDatasetConfig:
    data = asdict(base)
    for key, value in overrides.items():
        if key == "seed":
            continue
        if key in {"num_blocks", "num_days", "num_machines", "num_landings", "landing_capacity"}:
            if isinstance(value, (list, tuple)) and len(value) == 2:
                data[key] = tuple(int(part) for part in value)
            elif isinstance(value, str) and ":" in value:
                data[key] = _parse_range(value)
            else:
                data[key] = int(value)
        elif key in {"shift_hours", "work_required", "production_rate"}:
            if isinstance(value, (list, tuple)) and len(value) == 2:
                data[key] = (float(value[0]), float(value[1]))
            elif isinstance(value, str) and ":" in value:
                lo, hi = value.split(":")
                data[key] = (float(lo), float(hi))
            else:
                raise typer.BadParameter(f"{key} expects a two-value range.")
        elif key in {"crew_capability_span"}:
            if isinstance(value, (list, tuple)) and len(value) == 2:
                data[key] = (int(value[0]), int(value[1]))
            else:
                raise typer.BadParameter(f"{key} expects a two-value range.")
        else:
            data[key] = value
    return SyntheticDatasetConfig(**data)


def _describe_metadata(metadata: Dict[str, Any]) -> None:
    console.print("[bold]Synthetic Dataset Summary[/bold]")
    console.print(f"Name: {metadata.get('name')}")
    console.print(f"Tier: {metadata.get('tier')}")
    console.print(f"Seed: {metadata.get('seed')}")
    counts = metadata.get("counts", {})
    console.print(
        "Counts: "
        + ", ".join(f"{key}={counts[key]}" for key in sorted(counts))
    )
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
) -> None:
    tier = (tier or "small").lower()
    if tier not in TIER_PRESETS and tier != "custom":
        raise typer.BadParameter(f"Unknown tier '{tier}'. Valid options: {', '.join(TIER_PRESETS)}.")

    base_config = TIER_PRESETS.get(tier, SyntheticDatasetConfig(
        name="synthetic-custom",
        tier=None,
        num_blocks=(8, 12),
        num_days=(12, 16),
        num_machines=(4, 6),
        num_landings=(2, 3),
    ))

    config_overrides: Dict[str, Any] = {}
    if config is not None:
        config_overrides = _load_config(config)
        if not isinstance(config_overrides, dict):
            raise typer.BadParameter("Config file must yield a mapping/dictionary.")

    cli_overrides: Dict[str, Any] = {}
    if blocks:
        cli_overrides["num_blocks"] = blocks
    if machines:
        cli_overrides["num_machines"] = machines
    if landings:
        cli_overrides["num_landings"] = landings
    if days:
        cli_overrides["num_days"] = days
    if shifts_per_day is not None:
        cli_overrides["shifts_per_day"] = shifts_per_day

    merged = _merge_config(base_config, config_overrides)
    merged = _merge_config(merged, cli_overrides)

    seed_value = seed
    if seed_value is None and "seed" in config_overrides:
        seed_value = int(config_overrides["seed"])
    if seed_value is None:
        seed_value = TIER_SEEDS.get(tier, 123)

    bundle = generate_random_dataset(merged, seed=seed_value)

    metadata = bundle.metadata or {}
    metadata = {
        **metadata,
        "seed": seed_value,
    }

    if preview:
        _describe_metadata(metadata)
        return

    target_dir = output_dir
    if target_dir is None:
        target_dir = Path("examples/synthetic") / (merged.tier or merged.name)
    if target_dir.exists():
        if not overwrite:
            console.print(f"[red]Directory {target_dir} already exists. Use --overwrite to replace.[/red]")
            raise typer.Exit(1)
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = target_dir / "metadata.yaml"
    bundle.metadata = metadata
    bundle.write(target_dir, metadata_path=metadata_path)

    console.print(f"[green]Synthetic dataset written to {target_dir}[/green]")
    _describe_metadata(metadata)
