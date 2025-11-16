"""Dataset inspection CLI commands."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional

import typer
from rich.console import Console
from rich.table import Table

from fhops.core import FHOPSValueError
from fhops.costing import (
    MachineCostEstimate,
    estimate_unit_cost_from_distribution,
    estimate_unit_cost_from_stand,
)
from fhops.costing.machine_rates import (
    MachineRate,
    compose_default_rental_rate_for_role,
    get_machine_rate,
)
from fhops.productivity import (
    KelloggLoadType,
    LahrsenModel,
    ProductivityDistributionEstimate,
    estimate_cable_skidding_productivity_unver_robust,
    estimate_cable_skidding_productivity_unver_robust_profile,
    estimate_cable_skidding_productivity_unver_spss,
    estimate_cable_skidding_productivity_unver_spss_profile,
    estimate_forwarder_productivity_kellogg_bettinger,
    estimate_forwarder_productivity_large_forwarder_thinning,
    estimate_forwarder_productivity_small_forwarder_thinning,
    estimate_productivity,
    estimate_productivity_distribution,
    load_lahrsen_ranges,
)
from fhops.reference import load_appendix5_stands
from fhops.validation.ranges import validate_block_ranges
from fhops.scenario.contract import Scenario
from fhops.scenario.io import load_scenario
from fhops.scheduling.systems import HarvestSystem, default_system_registry

console = Console()
dataset_app = typer.Typer(help="Inspect FHOPS datasets and bundled examples.")


def _machine_rate_roles_help() -> str:
    from fhops.costing.machine_rates import load_machine_rate_index

    roles = ", ".join(sorted(load_machine_rate_index().keys()))
    return f"Available roles: {roles}"


def _resolve_machine_rate(role: str) -> MachineRate:
    rate = get_machine_rate(role)
    if rate is None:
        from fhops.costing.machine_rates import load_machine_rate_index

        available = ", ".join(sorted(load_machine_rate_index().keys()))
        raise typer.BadParameter(f"Unknown machine role '{role}'. Valid roles: {available}")
    return rate


@dataclass(frozen=True)
class DatasetRef:
    name: str
    path: Path


KNOWN_DATASETS: dict[str, DatasetRef] = {
    "minitoy": DatasetRef("minitoy", Path("examples/minitoy/scenario.yaml")),
    "small21": DatasetRef("small21", Path("examples/small21/scenario.yaml")),
    "med42": DatasetRef("med42", Path("examples/med42/scenario.yaml")),
    "large84": DatasetRef("large84", Path("examples/large84/scenario.yaml")),
    "synthetic-small": DatasetRef(
        "synthetic-small", Path("examples/synthetic/small/scenario.yaml")
    ),
    "synthetic-medium": DatasetRef(
        "synthetic-medium", Path("examples/synthetic/medium/scenario.yaml")
    ),
    "synthetic-large": DatasetRef(
        "synthetic-large", Path("examples/synthetic/large/scenario.yaml")
    ),
}


class ForwarderProductivityModel(str, Enum):
    """Supported forwarder productivity regressions exposed via the CLI."""

    GHAFFARIYAN_SMALL = "ghaffariyan-small"
    GHAFFARIYAN_LARGE = "ghaffariyan-large"
    KELLOGG_SAWLOG = "kellogg-sawlog"
    KELLOGG_PULPWOOD = "kellogg-pulpwood"
    KELLOGG_MIXED = "kellogg-mixed"


_KELLOGG_MODEL_TO_LOAD = {
    ForwarderProductivityModel.KELLOGG_SAWLOG: KelloggLoadType.SAWLOG,
    ForwarderProductivityModel.KELLOGG_PULPWOOD: KelloggLoadType.PULPWOOD,
    ForwarderProductivityModel.KELLOGG_MIXED: KelloggLoadType.MIXED,
}


class CableSkiddingModel(str, Enum):
    """Ünver-Okan cable skidding regressions."""

    UNVER_SPSS = "unver-spss"
    UNVER_ROBUST = "unver-robust"


def _candidate_roots() -> list[Path]:
    """Return candidate roots to resolve bundled dataset paths."""
    roots = [Path.cwd()]
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        if parent not in roots:
            roots.append(parent)
    return roots


def _resolve_known_dataset(ref: DatasetRef) -> Path:
    rel_path = ref.path
    candidates: list[Path] = []
    if rel_path.is_absolute():
        candidates.append(rel_path)
    else:
        for root in _candidate_roots():
            candidates.append((root / rel_path).resolve())
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except FileNotFoundError:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved
    raise FileNotFoundError(f"Bundled dataset not found: {rel_path}")


def _resolve_scenario_from_path(path: Path) -> Path:
    expanded = path.expanduser().resolve()
    if not expanded.exists():
        raise FileNotFoundError(expanded)
    if expanded.is_file():
        return expanded
    scenario_file = expanded / "scenario.yaml"
    if scenario_file.exists():
        return scenario_file
    yaml_files = sorted(expanded.glob("*.yaml"))
    if len(yaml_files) == 1:
        return yaml_files[0]
    raise FileNotFoundError(
        f"No scenario YAML found under {expanded}. "
        "Place a scenario.yaml file or specify the path directly."
    )


def _resolve_dataset(identifier: str) -> tuple[str, Path]:
    key = identifier.strip()
    if not key:
        raise typer.BadParameter("Dataset identifier must be non-empty.")
    if key in KNOWN_DATASETS:
        ref = KNOWN_DATASETS[key]
        path = _resolve_known_dataset(ref)
        return ref.name, path

    candidate = Path(key)
    if candidate.exists():
        return candidate.name, _resolve_scenario_from_path(candidate)

    raise typer.BadParameter(
        f"Dataset '{identifier}' not recognised. Provide a bundled name "
        f"({', '.join(sorted(KNOWN_DATASETS))}) or a valid path to a scenario."
    )


def _prompt_choice(message: str, options: list[str]) -> str:
    if not options:
        raise typer.BadParameter("No options available to prompt.")
    for idx, option in enumerate(options, start=1):
        console.print(f"{idx}. {option}")
    while True:
        choice = typer.prompt(f"{message} [1-{len(options)}]")
        try:
            idx = int(choice)
        except ValueError:
            console.print("[red]Enter a numeric choice.[/red]")
            continue
        if 1 <= idx <= len(options):
            return options[idx - 1]
        console.print("[red]Choice out of range.[/red]")


def _ensure_dataset(identifier: str | None, interactive: bool) -> tuple[str, Scenario, Path]:
    dataset_id = identifier
    if dataset_id is None:
        if not interactive:
            raise typer.BadParameter("Dataset identifier is required when prompts are disabled.")
        dataset_id = typer.prompt(
            "Dataset name or scenario path "
            f"(bundled options: {', '.join(sorted(KNOWN_DATASETS))})"
        )
    name, path = _resolve_dataset(dataset_id)
    scenario = load_scenario(path)
    return name, scenario, path


def _scenario_systems(scenario: Scenario) -> dict[str, HarvestSystem]:
    return scenario.harvest_systems or dict(default_system_registry())


def _select_system(
    scenario: Scenario, system_id: str | None, interactive: bool
) -> tuple[str, HarvestSystem] | None:
    systems = _scenario_systems(scenario)
    if not systems:
        return None
    if system_id:
        system = systems.get(system_id)
        if system is None:
            raise typer.BadParameter(
                f"Unknown harvest system '{system_id}'. "
                f"Options: {', '.join(sorted(systems))}"
            )
        return system.system_id, system
    if not interactive:
        raise typer.BadParameter("System selection required when prompts are disabled.")
    choice = _prompt_choice("Select a harvest system", sorted(systems))
    return choice, systems[choice]


def _select_machine(
    scenario: Scenario, machine_id: str | None, interactive: bool, system: HarvestSystem | None
):
    machines = {machine.id: machine for machine in scenario.machines}
    if machine_id:
        machine = machines.get(machine_id)
        if machine is None:
            raise typer.BadParameter(
                f"Machine '{machine_id}' not found. Options: {', '.join(sorted(machines))}"
            )
        return machine
    relevant_ids: list[str]
    if system:
        roles = {job.machine_role for job in system.jobs}
        relevant_ids = sorted(
            [machine.id for machine in scenario.machines if machine.role in roles]
        )
    else:
        relevant_ids = sorted(machines)
    if not relevant_ids:
        relevant_ids = sorted(machines)
    if not interactive:
        raise typer.BadParameter("Machine selection required when prompts are disabled.")
    choice = _prompt_choice("Select a machine", relevant_ids)
    return machines[choice]


def _select_block(scenario: Scenario, block_id: str | None, interactive: bool):
    blocks = {block.id: block for block in scenario.blocks}
    if block_id:
        block = blocks.get(block_id)
        if block is None:
            raise typer.BadParameter(
                f"Block '{block_id}' not found. Options: {', '.join(sorted(blocks))}"
            )
        return block
    if not interactive:
        raise typer.BadParameter("Block selection required when prompts are disabled.")
    choice = _prompt_choice("Select a block", sorted(blocks))
    return blocks[choice]


def _render_kv_table(title: str, rows: Iterable[tuple[str, str]]) -> None:
    table = Table(title=title, show_header=False, expand=True)
    table.add_column("Field", style="bold cyan", no_wrap=True)
    table.add_column("Value", style="white")
    for key, value in rows:
        table.add_row(key, value)
    console.print(table)


@dataset_app.command("inspect-machine")
def inspect_machine(
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        "-d",
        help="Dataset name (e.g., minitoy) or path to scenario/dataset folder.",
    ),
    system: str | None = typer.Option(
        None, "--system", "-s", help="Harvest system ID to focus on (prompts if omitted)."
    ),
    machine: str | None = typer.Option(
        None, "--machine", "-m", help="Machine ID to inspect (prompts if omitted)."
    ),
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-interactive",
        help="Enable prompts when context is missing.",
    ),
):
    """Inspect machine parameters within a dataset/system context."""
    dataset_name, scenario, path = _ensure_dataset(dataset, interactive)
    system_selection = _select_system(scenario, system, interactive)
    selected_machine = _select_machine(
        scenario, machine, interactive, system_selection[1] if system_selection else None
    )
    context_lines = [
        ("Dataset", dataset_name),
        ("Scenario Path", str(path)),
        ("Machine ID", selected_machine.id),
        ("Crew", selected_machine.crew or "—"),
        ("Daily Hours", f"{selected_machine.daily_hours}"),
        ("Operating Cost", f"{selected_machine.operating_cost}"),
        ("Role", selected_machine.role or "—"),
    ]
    if system_selection:
        system_id, system_model = system_selection
        job_matches = [
            job.name
            for job in system_model.jobs
            if selected_machine.role and job.machine_role == selected_machine.role
        ]
        context_lines.append(("Harvest System", system_id))
        context_lines.append(
            ("System Jobs Matched", ", ".join(job_matches) if job_matches else "—")
        )
    _render_kv_table(f"Machine Inspection — {selected_machine.id}", context_lines)
    if abs(selected_machine.daily_hours - 24.0) > 1e-6:
        console.print(
            "[red]Warning:[/red] machine daily_hours="
            f"{selected_machine.daily_hours} differs from the 24 h/day baseline."
        )
    console.print(
        "[yellow]* TODO: add derived statistics (utilisation, availability) once defined.[/yellow]"
    )


@dataset_app.command("inspect-block")
def inspect_block(
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        "-d",
        help="Dataset name (e.g., minitoy) or path to scenario/dataset folder.",
    ),
    block: str | None = typer.Option(
        None, "--block", "-b", help="Block ID to inspect (prompts if omitted)."
    ),
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-interactive",
        help="Enable prompts when context is missing.",
    ),
):
    """Inspect a single block's declared parameters."""
    dataset_name, scenario, path = _ensure_dataset(dataset, interactive)
    selected_block = _select_block(scenario, block, interactive)
    rows = [
        ("Dataset", dataset_name),
        ("Scenario Path", str(path)),
        ("Block ID", selected_block.id),
        ("Landing ID", selected_block.landing_id),
        ("Work Required", f"{selected_block.work_required}"),
        ("Earliest Start", str(selected_block.earliest_start or 1)),
        (
            "Latest Finish",
            str(selected_block.latest_finish or scenario.num_days),
        ),
        ("Harvest System ID", selected_block.harvest_system_id or "—"),
    ]
    if selected_block.avg_stem_size_m3 is not None:
        rows.append(("Avg Stem Size (m³)", f"{selected_block.avg_stem_size_m3:.3f}"))
    if selected_block.volume_per_ha_m3 is not None:
        rows.append(("Volume per ha (m³)", f"{selected_block.volume_per_ha_m3:.1f}"))
    if selected_block.volume_per_ha_m3_sigma is not None:
        rows.append(("Volume per ha σ (m³)", f"{selected_block.volume_per_ha_m3_sigma:.1f}"))
    if selected_block.stem_density_per_ha is not None:
        rows.append(("Stem Density (/ha)", f"{selected_block.stem_density_per_ha:.1f}"))
    if selected_block.stem_density_per_ha_sigma is not None:
        rows.append(("Stem Density σ (/ha)", f"{selected_block.stem_density_per_ha_sigma:.1f}"))
    if selected_block.ground_slope_percent is not None:
        rows.append(("Ground Slope (%)", f"{selected_block.ground_slope_percent:.1f}"))
    _render_kv_table(f"Block Inspection — {selected_block.id}", rows)
    warnings = validate_block_ranges(
        block_id=selected_block.id,
        stem_size=selected_block.avg_stem_size_m3,
        volume_per_ha=selected_block.volume_per_ha_m3,
        stem_density=selected_block.stem_density_per_ha,
        ground_slope=selected_block.ground_slope_percent,
    )
    if warnings:
        console.print("[red]Stand metric warnings:[/red]")
        for msg in warnings:
            console.print(f"  - {msg}")
    console.print(
        "[yellow]* TODO: add derived statistics (windows, production rates) once defined.[/yellow]"
    )


@dataset_app.command("estimate-productivity")
def estimate_productivity_cmd(
    avg_stem_size: float = typer.Option(
        ...,
        "--avg-stem-size",
        min=0.0,
        help="Average harvested stem size (m³/stem).",
    ),
    volume_per_ha: float = typer.Option(
        ...,
        "--volume-per-ha",
        min=0.0,
        help="Average harvested volume per hectare (m³/ha).",
    ),
    stem_density: float = typer.Option(
        ...,
        "--stem-density",
        min=0.0,
        help="Average stem density (trees/ha).",
    ),
    ground_slope: float = typer.Option(
        ...,
        "--ground-slope",
        min=0.0,
        help="Average ground slope (percent).",
    ),
    model: LahrsenModel = typer.Option(
        LahrsenModel.DAILY,
        "--model",
        case_sensitive=False,
        help="Which Lahrsen (2025) coefficient set to use.",
    ),
    allow_out_of_range: bool = typer.Option(
        False,
        "--allow-out-of-range",
        help="Skip range validation (useful for exploratory synthetic data).",
    ),
):
    """Estimate productivity (m³/PMH15) via Lahrsen (2025) BC regression."""
    try:
        result = estimate_productivity(
            avg_stem_size=avg_stem_size,
            volume_per_ha=volume_per_ha,
            stem_density=stem_density,
            ground_slope=ground_slope,
            model=model,
            validate_ranges=not allow_out_of_range,
        )
    except FHOPSValueError as exc:  # pragma: no cover - Typer surfaces error.
        raise typer.BadParameter(str(exc)) from exc

    rows = [
        ("Model", result.model.value),
        ("Average Stem Size (m³/stem)", f"{result.avg_stem_size:.3f}"),
        ("Volume per Hectare (m³/ha)", f"{result.volume_per_ha:.1f}"),
        ("Stem Density (trees/ha)", f"{result.stem_density:.1f}"),
        ("Ground Slope (%)", f"{result.ground_slope:.1f}"),
        ("Predicted Productivity (m³/PMH15)", f"{result.predicted_m3_per_pmh:.2f}"),
    ]
    _render_kv_table(
        "Lahrsen (2025) Feller-Buncher Productivity Estimate",
        rows,
    )
    if result.out_of_range:
        console.print("[red]Warning: inputs outside observed BC ranges:[/red]")
        for msg in result.out_of_range:
            console.print(f"  - {msg}")
    range_table = Table(title="Observed Ranges (Lahrsen 2025)")
    range_table.add_column("Variable", style="bold")
    range_table.add_column("Min")
    range_table.add_column("Max")
    for label, key in [
        ("Avg stem size (m³)", "avg_stem_size"),
        ("Volume per ha (m³)", "volume_per_ha"),
        ("Stem density (/ha)", "stem_density"),
        ("Ground slope (%)", "ground_slope"),
    ]:
        bounds = result.ranges[key]
        min_val = bounds.get("min")
        max_val = bounds.get("max")
        range_table.add_row(
            label,
            f"{min_val:.3f}" if min_val is not None else "—",
            f"{max_val:.3f}" if max_val is not None else "—",
        )
    console.print(range_table)
    console.print(
        "[dim]Coefficients sourced from Lahrsen, 2025 (UBC PhD) — whole-tree feller-buncher dataset.[/dim]"
    )


@dataset_app.command("estimate-productivity-rv")
def estimate_productivity_rv_cmd(
    avg_stem_size: float = typer.Option(..., help="Mean stem size (m³)", min=0.0),
    avg_stem_size_sigma: float = typer.Option(0.05, help="Std dev for stem size (m³)", min=0.0),
    volume_per_ha: float = typer.Option(..., help="Mean volume per ha (m³)", min=0.0),
    volume_per_ha_sigma: float = typer.Option(25.0, help="Std dev volume per ha (m³)", min=0.0),
    stem_density: float = typer.Option(..., help="Mean stem density (/ha)", min=0.0),
    stem_density_sigma: float = typer.Option(50.0, help="Std dev stem density (/ha)", min=0.0),
    ground_slope: float = typer.Option(..., help="Mean slope (%)", min=0.0),
    ground_slope_sigma: float = typer.Option(2.0, help="Std dev slope (%)", min=0.0),
    model: LahrsenModel = typer.Option(LahrsenModel.DAILY, case_sensitive=False),
    method: str = typer.Option("auto", help="RV evaluation method: auto|pacal|monte-carlo"),
    samples: int = typer.Option(5000, help="Monte Carlo samples"),
):
    """Estimate expected productivity when inputs are random variates."""

    try:
        result = estimate_productivity_distribution(
            avg_stem_size_mu=avg_stem_size,
            avg_stem_size_sigma=avg_stem_size_sigma,
            volume_per_ha_mu=volume_per_ha,
            volume_per_ha_sigma=volume_per_ha_sigma,
            stem_density_mu=stem_density,
            stem_density_sigma=stem_density_sigma,
            ground_slope_mu=ground_slope,
            ground_slope_sigma=ground_slope_sigma,
            model=model,
            method=method.lower(),
            samples=samples,
        )
    except FHOPSValueError as exc:  # pragma: no cover
        raise typer.BadParameter(str(exc)) from exc

    rows = [
        ("Model", result.model.value),
        ("Method", result.method),
        ("Expected Productivity (m³/PMH15)", f"{result.expected_m3_per_pmh:.2f}"),
        ("Std Dev", f"{result.std_m3_per_pmh:.2f}" if result.std_m3_per_pmh is not None else "—"),
        ("Samples", str(result.sample_count) if result.sample_count else "—"),
        ("PaCal Used", "yes" if result.pacal_used else "no"),
    ]
    _render_kv_table("Lahrsen Productivity (RV)", rows)


@dataset_app.command("estimate-forwarder-productivity")
def estimate_forwarder_productivity_cmd(
    model: ForwarderProductivityModel = typer.Option(
        ForwarderProductivityModel.GHAFFARIYAN_SMALL,
        "--model",
        case_sensitive=False,
        help="Forwarder regression to evaluate.",
    ),
    extraction_distance: Optional[float] = typer.Option(
        None,
        "--extraction-distance",
        min=0.0,
        help="Mean forwarding distance (m). Required for Ghaffariyan models.",
    ),
    slope_factor: float = typer.Option(
        1.0,
        "--slope-factor",
        min=0.0,
        help="Multiplier to approximate slope penalties (>0). Applies to Ghaffariyan models.",
    ),
    volume_per_load: Optional[float] = typer.Option(
        None,
        "--volume-per-load",
        min=0.0,
        help="Per-load volume (m³). Required for Kellogg models.",
    ),
    distance_out: Optional[float] = typer.Option(
        None,
        "--distance-out",
        min=0.0,
        help="Distance from landing to the first loading point (m). Required for Kellogg models.",
    ),
    travel_in_unit: Optional[float] = typer.Option(
        None,
        "--travel-in-unit",
        min=0.0,
        help="Distance travelled while loading within the unit (m). Required for Kellogg models.",
    ),
    distance_in: Optional[float] = typer.Option(
        None,
        "--distance-in",
        min=0.0,
        help="Distance from final loading point back to the landing (m). Required for Kellogg models.",
    ),
):
    """Estimate forwarder productivity (m³/PMH0) for thinning operations."""

    if model in (ForwarderProductivityModel.GHAFFARIYAN_SMALL, ForwarderProductivityModel.GHAFFARIYAN_LARGE):
        if extraction_distance is None:
            raise typer.BadParameter("--extraction-distance is required for Ghaffariyan models.")
        if slope_factor <= 0:
            raise typer.BadParameter("--slope-factor must be > 0.")
        if model is ForwarderProductivityModel.GHAFFARIYAN_SMALL:
            value = estimate_forwarder_productivity_small_forwarder_thinning(
                extraction_distance_m=extraction_distance,
                slope_factor=slope_factor,
            )
            reference = "Ghaffariyan et al. 2019 (14 t forwarder)"
        else:
            value = estimate_forwarder_productivity_large_forwarder_thinning(
                extraction_distance_m=extraction_distance,
                slope_factor=slope_factor,
            )
            reference = "Ghaffariyan et al. 2019 (20 t forwarder)"
        rows = [
            ("Model", model.value),
            ("Reference", reference),
            ("Extraction Distance (m)", f"{extraction_distance:.1f}"),
            ("Slope Factor", f"{slope_factor:.2f}"),
            ("Predicted Productivity (m³/PMH0)", f"{value:.2f}"),
        ]
    else:
        missing = []
        if volume_per_load is None:
            missing.append("--volume-per-load")
        if distance_out is None:
            missing.append("--distance-out")
        if travel_in_unit is None:
            missing.append("--travel-in-unit")
        if distance_in is None:
            missing.append("--distance-in")
        if missing:
            raise typer.BadParameter(f"{', '.join(missing)} required for Kellogg models.")
        load_type = _KELLOGG_MODEL_TO_LOAD[model]
        value = estimate_forwarder_productivity_kellogg_bettinger(
            load_type=load_type,
            volume_per_load_m3=volume_per_load,
            distance_out_m=distance_out,
            travel_in_unit_m=travel_in_unit,
            distance_in_m=distance_in,
        )
        rows = [
            ("Model", model.value),
            ("Reference", "Kellogg & Bettinger 1994 (FMG 910)"),
            ("Load Type", load_type.value),
            ("Volume per Load (m³)", f"{volume_per_load:.2f}"),
            ("Distance Out (m)", f"{distance_out:.1f}"),
            ("Travel In Unit (m)", f"{travel_in_unit:.1f}"),
            ("Distance In (m)", f"{distance_in:.1f}"),
            ("Predicted Productivity (m³/PMH0)", f"{value:.2f}"),
        ]

    _render_kv_table("Forwarder Productivity Estimate", rows)
    console.print("[dim]Values expressed in PMH0 (productive machine hours without delays).[/dim]")
    if model in _KELLOGG_MODEL_TO_LOAD:
        console.print("[dim]Regression from Kellogg & Bettinger (1994) western Oregon CTL thinning study.[/dim]")
    else:
        console.print("[dim]Regression from Ghaffariyan et al. (2019) ALPACA thinning dataset.[/dim]")


@dataset_app.command("productivity-ranges")
def show_productivity_ranges():
    """Display Lahrsen (2025) observed parameter ranges."""

    data = load_lahrsen_ranges()
    for section in ("daily", "cutblock"):
        table = Table(title=f"Lahrsen 2025 {section.title()} Ranges")
        table.add_column("Variable", style="bold")
        table.add_column("Min")
        table.add_column("Max")
        table.add_column("Mean")
        table.add_column("Median")
        entries = [
            ("productivity_m3_per_pmh15", "Productivity (m³/PMH15)"),
            ("avg_stem_size_m3", "Avg stem size (m³)"),
            ("volume_per_ha_m3", "Volume per ha (m³)"),
            ("stem_density_per_ha", "Stem density (/ha)"),
            ("ground_slope_percent", "Ground slope (%)"),
            ("block_size_ha", "Block size (ha)"),
        ]
        for key, label in entries:
            if key not in data[section]:
                continue
            entry = data[section][key]
            table.add_row(
                label,
                f"{entry.get('min', float('nan')):.3f}" if "min" in entry else "—",
                f"{entry.get('max', float('nan')):.3f}" if "max" in entry else "—",
                f"{entry.get('mean', float('nan')):.3f}" if "mean" in entry else "—",
                f"{entry.get('median', float('nan')):.3f}" if "median" in entry else "—",
            )
        console.print(table)
    console.print("[dim]Data from Lahrsen (2025) – see thesis for study context.[/dim]")


__all__ = ["dataset_app"]
@dataset_app.command("estimate-cost")
def estimate_cost_cmd(
    rental_rate: float | None = typer.Option(None, help="Rental rate ($/SMH)", min=0.0),
    machine_role: str | None = typer.Option(
        None,
        "--machine-role",
        "-r",
        help="Load rental rate components from the FHOPS machine-rate table.",
    ),
    include_repair: bool = typer.Option(
        True,
        "--include-repair/--exclude-repair",
        help="Include FPInnovations repair/maintenance allowance when deriving --machine-role rates.",
    ),
    owning_rate: float | None = typer.Option(
        None,
        "--owning-rate",
        min=0.0,
        help="Override owning component ($/SMH) when --machine-role is supplied.",
    ),
    operating_rate: float | None = typer.Option(
        None,
        "--operating-rate",
        min=0.0,
        help="Override operating component ($/SMH) when --machine-role is supplied.",
    ),
    repair_rate: float | None = typer.Option(
        None,
        "--repair-rate",
        min=0.0,
        help="Override repair/maintenance component ($/SMH). Requires --machine-role.",
    ),
    utilisation: float = typer.Option(0.9, help="Utilisation coefficient (0-1)", min=0.0, max=1.0),
    productivity: float | None = typer.Option(None, help="Direct productivity (m³/PMH15)."),
    use_rv: bool = typer.Option(False, help="Treat stand inputs as random variates with stddevs."),
    avg_stem_size: float | None = typer.Option(None, help="Avg stem size (m³)"),
    avg_stem_size_sigma: float = typer.Option(0.05, help="Std dev stem size (m³)", min=0.0),
    volume_per_ha: float | None = typer.Option(None, help="Volume per ha (m³)"),
    volume_per_ha_sigma: float = typer.Option(25.0, help="Std dev volume/ha", min=0.0),
    stem_density: float | None = typer.Option(None, help="Stem density (/ha)"),
    stem_density_sigma: float = typer.Option(50.0, help="Std dev stem density", min=0.0),
    ground_slope: float | None = typer.Option(None, help="Ground slope (%)"),
    ground_slope_sigma: float = typer.Option(2.0, help="Std dev slope", min=0.0),
    model: LahrsenModel = typer.Option(LahrsenModel.DAILY, case_sensitive=False),
    samples: int = typer.Option(5000, help="Monte Carlo samples (RV mode)", min=1),
):
    """Estimate $/m³ given rental rate, utilisation, and (optionally) Lahrsen stand inputs."""

    overrides = [owning_rate, operating_rate, repair_rate]
    if machine_role is None:
        if any(value is not None for value in overrides):
            raise typer.BadParameter("--owning-rate/--operating-rate/--repair-rate require --machine-role.")
    else:
        if rental_rate is not None:
            raise typer.BadParameter("Use either --rental-rate or --machine-role (not both).")

    machine_entry: MachineRate | None = None
    rental_breakdown: dict[str, float] | None = None
    repair_reference_hours: int | None = None

    if machine_role is not None:
        machine_entry = _resolve_machine_rate(machine_role)
        composed = compose_default_rental_rate_for_role(
            machine_role,
            include_repair_maintenance=include_repair,
            ownership_override=owning_rate,
            operating_override=operating_rate,
            repair_override=repair_rate,
        )
        if composed is None:
            raise typer.BadParameter(f"No default rate available for role '{machine_role}'.")
        rental_rate, rental_breakdown = composed
        if include_repair and machine_entry.repair_maintenance_cost_per_smh is not None:
            repair_reference_hours = machine_entry.repair_maintenance_reference_hours

    if rental_rate is None:
        raise typer.BadParameter("Provide either --rental-rate or --machine-role.")

    if productivity is None:
        required = [avg_stem_size, volume_per_ha, stem_density, ground_slope]
        if any(value is None for value in required):
            raise typer.BadParameter(
                "Provide either --productivity or all stand metrics (avg stem size, volume/ha, stem density, slope)."
            )
        if use_rv:
            cost, prod = estimate_unit_cost_from_distribution(
                rental_rate_smh=rental_rate,
                utilisation=utilisation,
                avg_stem_size_mu=avg_stem_size,
                avg_stem_size_sigma=avg_stem_size_sigma,
                volume_per_ha_mu=volume_per_ha,
                volume_per_ha_sigma=volume_per_ha_sigma,
                stem_density_mu=stem_density,
                stem_density_sigma=stem_density_sigma,
                ground_slope_mu=ground_slope,
                ground_slope_sigma=ground_slope_sigma,
                model=model,
                samples=samples,
                rental_rate_breakdown=rental_breakdown,
            )
            productivity = prod.expected_m3_per_pmh
            prod_info = {
                "method": prod.method,
                "productivity_mean": prod.expected_m3_per_pmh,
                "productivity_std": prod.std_m3_per_pmh,
                "samples": prod.sample_count,
            }
        else:
            cost, prod = estimate_unit_cost_from_stand(
                rental_rate_smh=rental_rate,
                utilisation=utilisation,
                avg_stem_size=avg_stem_size,
                volume_per_ha=volume_per_ha,
                stem_density=stem_density,
                ground_slope=ground_slope,
                model=model,
                rental_rate_breakdown=rental_breakdown,
            )
            prod_info = {
                "method": "deterministic",
                "productivity_mean": prod.predicted_m3_per_pmh,
                "productivity_std": None,
                "samples": 0,
            }
    else:
        cost = MachineCostEstimate(
            rental_rate_smh=rental_rate,
            utilisation=utilisation,
            productivity_m3_per_pmh=productivity,
            cost_per_m3=rental_rate / (utilisation * productivity),
            method="direct",
            rental_rate_breakdown=rental_breakdown,
        )
        prod_info = {
            "method": "direct",
            "productivity_mean": productivity,
            "productivity_std": None,
            "samples": 0,
        }

    rows = []
    if machine_entry is not None:
        rows.extend(
            [
                ("Machine Role", machine_entry.role),
                ("Machine", machine_entry.machine_name),
                ("Source", machine_entry.source),
            ]
        )
    if rental_breakdown:
        rows.append(("Owning Cost ($/SMH)", f"{rental_breakdown['ownership']:.2f}"))
        rows.append(("Operating Cost ($/SMH)", f"{rental_breakdown['operating']:.2f}"))
        repair_value = rental_breakdown.get("repair_maintenance")
        if repair_value is not None:
            rows.append(("Repair/Maint. ($/SMH)", f"{repair_value:.2f}"))
    rows.extend(
        [
            ("Rental Rate ($/SMH)", f"{cost.rental_rate_smh:.2f}"),
            ("Utilisation", f"{cost.utilisation:.3f}"),
            ("Productivity (m³/PMH15)", f"{cost.productivity_m3_per_pmh:.2f}"),
            ("Cost ($/m³)", f"{cost.cost_per_m3:.2f}"),
            ("Productivity Method", prod_info["method"]),
        ]
    )
    if prod_info["productivity_std"] is not None:
        rows.append(("Productivity Std", f"{prod_info['productivity_std']:.2f}"))
    rows.append(("Samples", str(prod_info["samples"])))
    _render_kv_table("Machine Cost Estimate", rows)
    if machine_entry and repair_reference_hours:
        console.print(
            f"[dim]Repair/maintenance allowance derived from Advantage Vol. 4 No. 23 (usage class {repair_reference_hours / 1000:.0f}×1000 h).[/dim]"
        )


@dataset_app.command("appendix5-stands")
def list_appendix5_stands(
    author_filter: str | None = typer.Option(None, "--author", help="Filter by author substring."),
    limit: int = typer.Option(20, "--limit", min=1, max=200, help="Max rows to display."),
):
    """Show stand metadata extracted from Arnvik (2024) Appendix 5."""

    entries = load_appendix5_stands()
    filtered = [
        entry
        for entry in entries
        if not author_filter or author_filter.lower() in entry.author.lower()
    ]
    table = Table(title="Appendix 5 Stand Profiles")
    table.add_column("Author", style="bold")
    table.add_column("Species")
    table.add_column("Slope (%)")
    table.add_column("Ground Condition")
    table.add_column("Roughness")
    for entry in filtered[:limit]:
        slope = entry.average_slope_percent
        slope_text = f"{slope:.1f}" if slope is not None else entry.slope_text or "—"
        table.add_row(entry.author, entry.tree_species or "—", slope_text, entry.ground_condition or "—", entry.ground_roughness or "—")
    if not filtered:
        console.print("No matching profiles.")
        return
    console.print(table)


@dataset_app.command("estimate-cable-skidding")
def estimate_cable_skidding_cmd(
    model: CableSkiddingModel = typer.Option(CableSkiddingModel.UNVER_SPSS, case_sensitive=False),
    log_volume_m3: float = typer.Option(..., min=0.01, help="Log volume per cycle (m³)."),
    slope_percent: float | None = typer.Option(
        None, "--slope-percent", min=0.1, help="Route slope percent (ignored when --profile is used)."
    ),
    profile: str | None = typer.Option(
        None, "--profile", help="Appendix 5 author/stand name to supply slope defaults."
    ),
):
    """Estimate cable skidding productivity (m³/h) using Ünver-Okan (2020) regressions."""

    if profile:
        if model is CableSkiddingModel.UNVER_SPSS:
            value = estimate_cable_skidding_productivity_unver_spss_profile(profile=profile, log_volume_m3=log_volume_m3)
        else:
            value = estimate_cable_skidding_productivity_unver_robust_profile(profile=profile, log_volume_m3=log_volume_m3)
        rows = [
            ("Model", model.value),
            ("Profile", profile),
            ("Log Volume (m³)", f"{log_volume_m3:.3f}"),
            ("Productivity (m³/h)", f"{value:.2f}"),
        ]
    else:
        if slope_percent is None:
            raise typer.BadParameter("Provide --slope-percent or --profile to supply slope defaults.")
        if model is CableSkiddingModel.UNVER_SPSS:
            value = estimate_cable_skidding_productivity_unver_spss(log_volume_m3, slope_percent)
        else:
            value = estimate_cable_skidding_productivity_unver_robust(log_volume_m3, slope_percent)
        rows = [
            ("Model", model.value),
            ("Log Volume (m³)", f"{log_volume_m3:.3f}"),
            ("Slope (%)", f"{slope_percent:.2f}"),
            ("Productivity (m³/h)", f"{value:.2f}"),
        ]
    _render_kv_table("Cable Skidding Productivity", rows)
