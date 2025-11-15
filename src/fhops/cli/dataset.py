"""Dataset inspection CLI commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import typer
from rich.console import Console
from rich.table import Table

from fhops.core import FHOPSValueError
from fhops.costing import (
    MachineCostEstimate,
    estimate_unit_cost_from_distribution,
    estimate_unit_cost_from_stand,
)
from fhops.productivity import (
    LahrsenModel,
    ProductivityDistributionEstimate,
    estimate_productivity,
    estimate_productivity_distribution,
    load_lahrsen_ranges,
)
from fhops.validation.ranges import validate_block_ranges
from fhops.scenario.contract import Scenario
from fhops.scenario.io import load_scenario
from fhops.scheduling.systems import HarvestSystem, default_system_registry

console = Console()
dataset_app = typer.Typer(help="Inspect FHOPS datasets and bundled examples.")


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
    if selected_block.stem_density_per_ha is not None:
        rows.append(("Stem Density (/ha)", f"{selected_block.stem_density_per_ha:.1f}"))
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
    rental_rate: float = typer.Option(..., help="Rental rate ($/SMH)", min=0.0),
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
        )
        prod_info = {
            "method": "direct",
            "productivity_mean": productivity,
            "productivity_std": None,
            "samples": 0,
        }

    rows = [
        ("Rental Rate ($/SMH)", f"{cost.rental_rate_smh:.2f}"),
        ("Utilisation", f"{cost.utilisation:.3f}"),
        ("Productivity (m³/PMH15)", f"{cost.productivity_m3_per_pmh:.2f}"),
        ("Cost ($/m³)", f"{cost.cost_per_m3:.2f}"),
        ("Productivity Method", prod_info["method"]),
    ]
    if prod_info["productivity_std"] is not None:
        rows.append(("Productivity Std", f"{prod_info['productivity_std']:.2f}"))
    rows.append(("Samples", str(prod_info["samples"])) )
    _render_kv_table("Machine Cost Estimate", rows)
