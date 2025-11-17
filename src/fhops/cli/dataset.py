"""Dataset inspection CLI commands."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

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
    select_usage_class_multiplier,
)
from fhops.productivity import (
    ALPACASlopeClass,
    ForwarderBCModel,
    ForwarderBCResult,
    LahrsenModel,
    ADV6N10HarvesterInputs,
    TN292HarvesterInputs,
    alpaca_slope_multiplier,
    estimate_harvester_productivity_adv5n30,
    estimate_harvester_productivity_tn292,
    estimate_cable_skidding_productivity_unver_robust,
    estimate_cable_skidding_productivity_unver_robust_profile,
    estimate_cable_skidding_productivity_unver_spss,
    estimate_cable_skidding_productivity_unver_spss_profile,
    estimate_cable_yarder_cycle_time_tr127_minutes,
    estimate_cable_yarder_productivity_lee2018_downhill,
    estimate_cable_yarder_productivity_lee2018_uphill,
    estimate_cable_yarder_productivity_tr125_multi_span,
    estimate_cable_yarder_productivity_tr125_single_span,
    estimate_cable_yarder_productivity_tr127,
    estimate_forwarder_productivity_bc,
    estimate_harvester_productivity_adv6n10,
    estimate_productivity,
    estimate_productivity_distribution,
    load_lahrsen_ranges,
)
from fhops.reference import get_appendix5_profile, get_tr119_treatment, load_appendix5_stands
from fhops.scenario.contract import Machine, Scenario
from fhops.scenario.io import load_scenario
from fhops.scheduling.systems import HarvestSystem, default_system_registry
from fhops.telemetry import append_jsonl
from fhops.telemetry.machine_costs import build_machine_cost_snapshots
from fhops.validation.ranges import validate_block_ranges

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


class ProductivityMachineRole(str, Enum):
    """Machine roles supported by the productivity command."""

    FELLER_BUNCHER = "feller_buncher"
    FORWARDER = "forwarder"
    CTL_HARVESTER = "ctl_harvester"


class CTLHarvesterModel(str, Enum):
    """CTL harvester regressions."""

    ADV6N10 = "adv6n10"
    ADV5N30 = "adv5n30"
    TN292 = "tn292"


class CableSkiddingModel(str, Enum):
    """Ünver-Okan cable skidding regressions."""

    UNVER_SPSS = "unver-spss"
    UNVER_ROBUST = "unver-robust"


class SkylineProductivityModel(str, Enum):
    """Supported skyline productivity regressions."""

    LEE_UPHILL = "lee-uphill"
    LEE_DOWNHILL = "lee-downhill"
    TR125_SINGLE = "tr125-single-span"
    TR125_MULTI = "tr125-multi-span"
    TR127_BLOCK1 = "tr127-block1"
    TR127_BLOCK2 = "tr127-block2"
    TR127_BLOCK3 = "tr127-block3"
    TR127_BLOCK4 = "tr127-block4"
    TR127_BLOCK5 = "tr127-block5"
    TR127_BLOCK6 = "tr127-block6"


_TR127_MODEL_TO_BLOCK = {
    SkylineProductivityModel.TR127_BLOCK1: 1,
    SkylineProductivityModel.TR127_BLOCK2: 2,
    SkylineProductivityModel.TR127_BLOCK3: 3,
    SkylineProductivityModel.TR127_BLOCK4: 4,
    SkylineProductivityModel.TR127_BLOCK5: 5,
    SkylineProductivityModel.TR127_BLOCK6: 6,
}


_FORWARDER_GHAFFARIYAN_MODELS = {
    ForwarderBCModel.GHAFFARIYAN_SMALL,
    ForwarderBCModel.GHAFFARIYAN_LARGE,
}

_FORWARDER_ADV6N10_MODELS = {ForwarderBCModel.ADV6N10_SHORTWOOD}


def _forwarder_parameters(result: ForwarderBCResult) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [
        ("Model", result.model.value),
        ("Reference", result.reference or ""),
    ]
    params = result.parameters
    if result.model in _FORWARDER_GHAFFARIYAN_MODELS:
        extraction = params.get("extraction_distance_m")
        slope_class = params.get("slope_class")
        slope_factor = params.get("slope_factor")
        rows.extend(
            [
                ("Extraction Distance (m)", f"{float(extraction):.1f}"),
                ("Slope Class", str(slope_class)),
                ("Slope Factor", f"{float(slope_factor):.2f}"),
            ]
        )
    elif result.model in _FORWARDER_ADV6N10_MODELS:
        rows.extend(
            [
                ("Payload per Trip (m³)", f"{float(params['payload_m3']):.2f}"),
                ("Mean Log Length (m)", f"{float(params['mean_log_length_m']):.2f}"),
                ("Trail Length (m)", f"{float(params['trail_length_m']):.1f}"),
                (
                    "Travel Speed (m/min)",
                    f"{float(params['travel_speed_m_per_min']):.1f}",
                ),
                (
                    "Products per Trail",
                    f"{float(params['products_per_trail']):.2f}",
                ),
            ]
        )
    else:
        rows.extend(
            [
                ("Load Type", str(params.get("load_type", ""))),
                ("Volume per Load (m³)", f"{float(params['volume_per_load_m3']):.2f}"),
                ("Distance Out (m)", f"{float(params['distance_out_m']):.1f}"),
                ("Travel In Unit (m)", f"{float(params['travel_in_unit_m']):.1f}"),
                ("Distance In (m)", f"{float(params['distance_in_m']):.1f}"),
            ]
        )
    rows.append(("Predicted Productivity (m³/PMH0)", f"{result.predicted_m3_per_pmh:.2f}"))
    return rows


def _render_forwarder_result(result: ForwarderBCResult) -> None:
    rows = _forwarder_parameters(result)
    _render_kv_table("Forwarder Productivity Estimate", rows)
    console.print("[dim]Values expressed in PMH0 (productive machine hours without delays).[/dim]")
    if result.model in _FORWARDER_GHAFFARIYAN_MODELS:
        console.print(
            "[dim]Regression from Ghaffariyan et al. (2019) ALPACA thinning dataset.[/dim]"
        )
    elif result.model in _FORWARDER_ADV6N10_MODELS:
        console.print(
            "[dim]Regression from Gingras & Favreau (2005) CTL sorting study (ADV6N10).[/dim]"
        )
    else:
        console.print(
            "[dim]Regression from Kellogg & Bettinger (1994) western Oregon CTL study.[/dim]"
        )


def _evaluate_forwarder_result(
    *,
    model: ForwarderBCModel,
    extraction_distance: float | None,
    slope_class: ALPACASlopeClass,
    slope_factor: float | None,
    volume_per_load: float | None,
    distance_out: float | None,
    travel_in_unit: float | None,
    distance_in: float | None,
    payload_per_trip: float | None,
    mean_log_length: float | None,
    travel_speed: float | None,
    trail_length: float | None,
    products_per_trail: float | None,
) -> ForwarderBCResult:
    try:
        return estimate_forwarder_productivity_bc(
            model=model,
            extraction_distance_m=extraction_distance,
            slope_class=slope_class,
            slope_factor=slope_factor,
            volume_per_load_m3=volume_per_load,
            distance_out_m=distance_out,
            travel_in_unit_m=travel_in_unit,
            distance_in_m=distance_in,
            payload_m3=payload_per_trip,
            mean_log_length_m=mean_log_length,
            travel_speed_m_per_min=travel_speed,
            trail_length_m=trail_length,
            products_per_trail=products_per_trail,
        )
    except ValueError as exc:  # pragma: no cover - Typer surfaces error text
        raise typer.BadParameter(str(exc)) from exc


def _render_ctl_harvester_result(
    model: CTLHarvesterModel, inputs: object, productivity: float
) -> None:
    rows: list[tuple[str, str]] = [("Model", model.value)]
    if model is CTLHarvesterModel.ADV6N10 and isinstance(inputs, ADV6N10HarvesterInputs):
        rows.extend(
            [
                ("Stem Volume (m³/stem)", f"{inputs.stem_volume_m3:.3f}"),
                ("Number of Products", f"{inputs.products_count:.2f}"),
                ("Stems per Cycle", f"{inputs.stems_per_cycle:.2f}"),
                ("Mean Log Length (m)", f"{inputs.mean_log_length_m:.2f}"),
            ]
        )
        source = "Gingras & Favreau (2005) ADV6N10 boreal CTL sorting study"
    elif model is CTLHarvesterModel.ADV5N30 and isinstance(inputs, dict):
        rows.extend(
            [
                ("Removal Fraction", f"{inputs['removal_fraction']:.2f}"),
                ("Brushed?", "yes" if inputs.get("brushed") else "no"),
            ]
        )
        source = "Meek (2004) ADV5N30 Alberta white spruce thinning study"
    elif model is CTLHarvesterModel.TN292 and isinstance(inputs, TN292HarvesterInputs):
        rows.extend(
            [
                ("Stem Volume (m³/stem)", f"{inputs.stem_volume_m3:.3f}"),
                ("Stand Density (/ha)", f"{inputs.stand_density_per_ha:.0f}"),
                ("Density Basis", inputs.density_basis),
            ]
        )
        source = "Bulley (1999) TN292 Alberta thinning study"
    else:
        raise RuntimeError("Unhandled CTL harvester model payload.")
    rows.append(("Predicted Productivity (m³/PMH)", f"{productivity:.2f}"))
    _render_kv_table("CTL Harvester Productivity Estimate", rows)
    console.print(f"[dim]Regression from {source}.[/dim]")


def _evaluate_ctl_harvester_result(
    *,
    model: CTLHarvesterModel,
    stem_volume: float | None,
    products_count: float | None,
    stems_per_cycle: float | None,
    mean_log_length: float | None,
    removal_fraction: float | None,
    brushed: bool,
    density: float | None,
    density_basis: str,
) -> tuple[object, float]:
    if model is CTLHarvesterModel.ADV6N10:
        missing = []
        if stem_volume is None:
            missing.append("--ctl-stem-volume")
        if products_count is None:
            missing.append("--ctl-products-count")
        if stems_per_cycle is None:
            missing.append("--ctl-stems-per-cycle")
        if mean_log_length is None:
            missing.append("--ctl-mean-log-length")
        if missing:
            raise typer.BadParameter(
                f"{', '.join(missing)} required when --machine-role {ProductivityMachineRole.CTL_HARVESTER.value} with ADV6N10 model."
            )
        inputs = ADV6N10HarvesterInputs(
            stem_volume_m3=stem_volume,
            products_count=products_count,
            stems_per_cycle=stems_per_cycle,
            mean_log_length_m=mean_log_length,
        )
        try:
            value = estimate_harvester_productivity_adv6n10(inputs)
        except FHOPSValueError as exc:  # pragma: no cover - Typer surfaces error
            raise typer.BadParameter(str(exc)) from exc
        return inputs, value
    if model is CTLHarvesterModel.ADV5N30:
        if removal_fraction is None:
            raise typer.BadParameter("--ctl-removal-fraction required for ADV5N30 model.")
        try:
            value = estimate_harvester_productivity_adv5n30(
                removal_fraction=removal_fraction,
                brushed=brushed,
            )
        except FHOPSValueError as exc:  # pragma: no cover
            raise typer.BadParameter(str(exc)) from exc
        return {"removal_fraction": removal_fraction, "brushed": brushed}, value
    if model is CTLHarvesterModel.TN292:
        missing = []
        if stem_volume is None:
            missing.append("--ctl-stem-volume")
        if density is None:
            missing.append("--ctl-density")
        if missing:
            raise typer.BadParameter(
                f"{', '.join(missing)} required when --machine-role {ProductivityMachineRole.CTL_HARVESTER.value} with TN292 model."
            )
        inputs = TN292HarvesterInputs(
            stem_volume_m3=stem_volume,
            stand_density_per_ha=density,
            density_basis=density_basis,
        )
        try:
            value = estimate_harvester_productivity_tn292(inputs)
        except FHOPSValueError as exc:  # pragma: no cover
            raise typer.BadParameter(str(exc)) from exc
        return inputs, value
    raise typer.BadParameter(f"Unsupported CTL harvester model: {model}")


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
            f"Dataset name or scenario path (bundled options: {', '.join(sorted(KNOWN_DATASETS))})"
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
                f"Unknown harvest system '{system_id}'. Options: {', '.join(sorted(systems))}"
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
    json_out: Path | None = typer.Option(
        None,
        "--json-out",
        help="Optional path to write machine metadata and rental breakdown as JSON.",
        writable=True,
        dir_okay=False,
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
    default_snapshot = build_machine_cost_snapshots([selected_machine])[0]
    default_rate_rows: list[tuple[str, str]] = []
    default_rate_note: str | None = None
    if default_snapshot.rental_rate_smh is not None:
        default_rate_rows.append(
            ("Default Rental Rate ($/SMH)", f"{default_snapshot.rental_rate_smh:.2f}")
        )
        if default_snapshot.ownership is not None:
            default_rate_rows.append(
                ("Default Owning ($/SMH)", f"{default_snapshot.ownership:.2f}")
            )
        if default_snapshot.operating is not None:
            default_rate_rows.append(
                ("Default Operating ($/SMH)", f"{default_snapshot.operating:.2f}")
            )
        if default_snapshot.repair_maintenance is not None:
            default_rate_rows.append(
                ("Default Repair/Maint. ($/SMH)", f"{default_snapshot.repair_maintenance:.2f}")
            )
        if default_snapshot.usage_bucket_hours is not None:
            default_rate_rows.append(
                (
                    "Repair Usage Bucket",
                    f"{default_snapshot.usage_bucket_hours:,} h (multiplier {default_snapshot.usage_multiplier:.3f})",
                )
            )
            default_rate_note = (
                f"[dim]Default rate derived from role '{selected_machine.role}' "
                f"with repair usage {selected_machine.repair_usage_hours:,} h "
                f"(closest bucket {default_snapshot.usage_bucket_hours / 1000:.0f}×1000 h).[/dim]"
            )
        elif selected_machine.repair_usage_hours is not None:
            default_rate_rows.append(
                (
                    "Repair Usage Bucket",
                    f"{selected_machine.repair_usage_hours:,} h (no FPInnovations bucket data)",
                )
            )
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
    if default_rate_rows:
        _render_kv_table("Default Rental Breakdown", default_rate_rows)
        if default_rate_note:
            console.print(default_rate_note)
    if abs(selected_machine.daily_hours - 24.0) > 1e-6:
        console.print(
            "[red]Warning:[/red] machine daily_hours="
            f"{selected_machine.daily_hours} differs from the 24 h/day baseline."
        )
    console.print(
        "[yellow]* TODO: add derived statistics (utilisation, availability) once defined.[/yellow]"
    )
    if json_out is not None:
        payload = {
            "dataset": dataset_name,
            "scenario_path": str(path),
            "machine": {
                "id": selected_machine.id,
                "crew": selected_machine.crew,
                "daily_hours": selected_machine.daily_hours,
                "operating_cost": selected_machine.operating_cost,
                "role": selected_machine.role,
                "repair_usage_hours": selected_machine.repair_usage_hours,
            },
            "default_rental": default_snapshot.to_dict(),
        }
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
    machine_role: ProductivityMachineRole = typer.Option(
        ProductivityMachineRole.FELLER_BUNCHER,
        "--machine-role",
        case_sensitive=False,
        help="Machine role to evaluate (feller_buncher | forwarder | ctl_harvester).",
    ),
    avg_stem_size: float | None = typer.Option(
        None,
        "--avg-stem-size",
        min=0.0,
        help="Average harvested stem size (m³/stem). Required for feller-buncher models.",
    ),
    volume_per_ha: float | None = typer.Option(
        None,
        "--volume-per-ha",
        min=0.0,
        help="Average harvested volume per hectare (m³/ha). Required for feller-buncher models.",
    ),
    stem_density: float | None = typer.Option(
        None,
        "--stem-density",
        min=0.0,
        help="Average stem density (trees/ha). Required for feller-buncher models.",
    ),
    ground_slope: float | None = typer.Option(
        None,
        "--ground-slope",
        min=0.0,
        help="Average ground slope (percent). Required for feller-buncher models.",
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
    ctl_harvester_model: CTLHarvesterModel = typer.Option(
        CTLHarvesterModel.ADV6N10,
        "--ctl-harvester-model",
        case_sensitive=False,
        help="CTL harvester regression to evaluate when --machine-role ctl_harvester is used.",
    ),
    ctl_stem_volume: float | None = typer.Option(
        None,
        "--ctl-stem-volume",
        min=0.0,
        help="Mean stem volume (m³/stem). Required for CTL harvester models.",
    ),
    ctl_products_count: float | None = typer.Option(
        None,
        "--ctl-products-count",
        min=0.0,
        help="Number of products sorted per cycle. Required for CTL harvester models.",
    ),
    ctl_stems_per_cycle: float | None = typer.Option(
        None,
        "--ctl-stems-per-cycle",
        min=0.0,
        help="Average stems processed per cycle. Required for CTL harvester models.",
    ),
    ctl_mean_log_length: float | None = typer.Option(
        None,
        "--ctl-mean-log-length",
        min=0.0,
        help="Mean produced log length (m). Required for CTL harvester models.",
    ),
    ctl_removal_fraction: float | None = typer.Option(
        None,
        "--ctl-removal-fraction",
        min=0.0,
        max=1.0,
        help="Removal fraction (0-1) for ADV5N30 thinning model.",
    ),
    ctl_brushed: bool = typer.Option(
        False,
        "--ctl-brushed/--ctl-unbrushed",
        help="ADV5N30 brushing scenario (adds 21% productivity).",
    ),
    ctl_density: float | None = typer.Option(
        None,
        "--ctl-density",
        min=0.0,
        help="Stand density (trees/ha) for TN292 model.",
    ),
    ctl_density_basis: str = typer.Option(
        "pre",
        "--ctl-density-basis",
        help="Density basis for TN292 model: pre or post (harvest).",
    ),
    forwarder_model: ForwarderBCModel = typer.Option(
        ForwarderBCModel.GHAFFARIYAN_SMALL,
        "--forwarder-model",
        case_sensitive=False,
        help="Forwarder regression to evaluate when --machine-role forwarder is used.",
    ),
    extraction_distance: float | None = typer.Option(
        None,
        "--extraction-distance",
        min=0.0,
        help="Mean forwarding distance (m). Required for Ghaffariyan forwarder models.",
    ),
    slope_class: ALPACASlopeClass = typer.Option(
        ALPACASlopeClass.FLAT,
        "--slope-class",
        case_sensitive=False,
        help="Slope bucket (<10, 10-20, >20 percent) for Ghaffariyan models.",
    ),
    slope_factor: float | None = typer.Option(
        None,
        "--slope-factor",
        min=0.0,
        help="Custom multiplier overriding --slope-class for Ghaffariyan models.",
    ),
    volume_per_load: float | None = typer.Option(
        None,
        "--volume-per-load",
        min=0.0,
        help="Per-load volume (m³). Required for Kellogg forwarder models.",
    ),
    distance_out: float | None = typer.Option(
        None,
        "--distance-out",
        min=0.0,
        help="Distance from landing to first loading point (m). Required for Kellogg models.",
    ),
    travel_in_unit: float | None = typer.Option(
        None,
        "--travel-in-unit",
        min=0.0,
        help="Distance while loading within the unit (m). Required for Kellogg models.",
    ),
    distance_in: float | None = typer.Option(
        None,
        "--distance-in",
        min=0.0,
        help="Return distance to the landing (m). Required for Kellogg models.",
    ),
    payload_per_trip: float | None = typer.Option(
        None,
        "--payload-per-trip",
        min=0.0,
        help="Payload per forwarder trip (m³). Required for ADV6N10 model.",
    ),
    mean_log_length: float | None = typer.Option(
        None,
        "--mean-log-length",
        min=0.0,
        help="Mean log length (m). Required for ADV6N10 model.",
    ),
    travel_speed: float | None = typer.Option(
        None,
        "--travel-speed",
        min=0.0,
        help="Forwarder travel speed (m/min). Required for ADV6N10 model.",
    ),
    trail_length: float | None = typer.Option(
        None,
        "--trail-length",
        min=0.0,
        help="Trail length from landing to loading point (m). Required for ADV6N10 model.",
    ),
    products_per_trail: float | None = typer.Option(
        None,
        "--products-per-trail",
        min=0.0,
        help="Number of products separated on the trail (ADV6N10).",
    ),
):
    """Estimate productivity for Lahrsen (feller-buncher) or forwarder models."""

    role = machine_role.value
    if role == ProductivityMachineRole.FORWARDER.value:
        result = _evaluate_forwarder_result(
            model=forwarder_model,
            extraction_distance=extraction_distance,
            slope_class=slope_class,
            slope_factor=slope_factor,
            volume_per_load=volume_per_load,
            distance_out=distance_out,
            travel_in_unit=travel_in_unit,
            distance_in=distance_in,
            payload_per_trip=payload_per_trip,
            mean_log_length=mean_log_length,
            travel_speed=travel_speed,
            trail_length=trail_length,
            products_per_trail=products_per_trail,
        )
        _render_forwarder_result(result)
        return
    if role == ProductivityMachineRole.CTL_HARVESTER.value:
        inputs, value = _evaluate_ctl_harvester_result(
            model=ctl_harvester_model,
            stem_volume=ctl_stem_volume,
            products_count=ctl_products_count,
            stems_per_cycle=ctl_stems_per_cycle,
            mean_log_length=ctl_mean_log_length,
            removal_fraction=ctl_removal_fraction,
            brushed=ctl_brushed,
            density=ctl_density,
            density_basis=ctl_density_basis,
        )
        _render_ctl_harvester_result(ctl_harvester_model, inputs, value)
        return

    missing: list[str] = []
    if avg_stem_size is None:
        missing.append("--avg-stem-size")
    if volume_per_ha is None:
        missing.append("--volume-per-ha")
    if stem_density is None:
        missing.append("--stem-density")
    if ground_slope is None:
        missing.append("--ground-slope")
    if missing:
        raise typer.BadParameter(
            f"{', '.join(missing)} required when --machine-role {ProductivityMachineRole.FELLER_BUNCHER.value}."
        )
    assert avg_stem_size is not None
    assert volume_per_ha is not None
    assert stem_density is not None
    assert ground_slope is not None

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
    model: ForwarderBCModel = typer.Option(
        ForwarderBCModel.GHAFFARIYAN_SMALL,
        "--model",
        case_sensitive=False,
        help="Forwarder regression to evaluate.",
    ),
    extraction_distance: float | None = typer.Option(
        None,
        "--extraction-distance",
        min=0.0,
        help="Mean forwarding distance (m). Required for Ghaffariyan models.",
    ),
    slope_class: ALPACASlopeClass = typer.Option(
        ALPACASlopeClass.FLAT,
        "--slope-class",
        case_sensitive=False,
        help="Slope bin (<10, 10-20, >20 percent) from Ghaffariyan et al. 2019.",
    ),
    slope_factor: float | None = typer.Option(
        None,
        "--slope-factor",
        min=0.0,
        help="Custom multiplier overriding --slope-class for Ghaffariyan models.",
    ),
    volume_per_load: float | None = typer.Option(
        None,
        "--volume-per-load",
        min=0.0,
        help="Per-load volume (m³). Required for Kellogg models.",
    ),
    distance_out: float | None = typer.Option(
        None,
        "--distance-out",
        min=0.0,
        help="Distance from landing to the first loading point (m). Required for Kellogg models.",
    ),
    travel_in_unit: float | None = typer.Option(
        None,
        "--travel-in-unit",
        min=0.0,
        help="Distance travelled while loading within the unit (m). Required for Kellogg models.",
    ),
    distance_in: float | None = typer.Option(
        None,
        "--distance-in",
        min=0.0,
        help="Distance from final loading point back to the landing (m). Required for Kellogg models.",
    ),
    payload_per_trip: float | None = typer.Option(
        None,
        "--payload-per-trip",
        min=0.0,
        help="Payload per forwarder trip (m³). Required for ADV6N10 model.",
    ),
    mean_log_length: float | None = typer.Option(
        None,
        "--mean-log-length",
        min=0.0,
        help="Mean log length (m). Required for ADV6N10 model.",
    ),
    travel_speed: float | None = typer.Option(
        None,
        "--travel-speed",
        min=0.0,
        help="Forwarder travel speed (m/min). Required for ADV6N10 model.",
    ),
    trail_length: float | None = typer.Option(
        None,
        "--trail-length",
        min=0.0,
        help="Trail length from landing to loading point (m). Required for ADV6N10 model.",
    ),
    products_per_trail: float | None = typer.Option(
        None,
        "--products-per-trail",
        min=0.0,
        help="Number of products separated on the trail (ADV6N10).",
    ),
):
    """Estimate forwarder productivity (m³/PMH0) for thinning operations."""

    result = _evaluate_forwarder_result(
        model=model,
        extraction_distance=extraction_distance,
        slope_class=slope_class,
        slope_factor=slope_factor,
        volume_per_load=volume_per_load,
        distance_out=distance_out,
        travel_in_unit=travel_in_unit,
        distance_in=distance_in,
        payload_per_trip=payload_per_trip,
        mean_log_length=mean_log_length,
        travel_speed=travel_speed,
        trail_length=trail_length,
        products_per_trail=products_per_trail,
    )
    _render_forwarder_result(result)


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
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        "-d",
        help="Dataset name or scenario path to pull machine defaults (role, repair usage hours, $/SMH).",
    ),
    machine_id: str | None = typer.Option(
        None, "--machine", "-m", help="Machine ID within --dataset used to auto-fill inputs."
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
    usage_hours: int | None = typer.Option(
        None,
        "--usage-hours",
        min=0,
        help="Approximate cumulative usage hours when applying FPInnovations repair multipliers (nearest 5k bucket).",
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
            raise typer.BadParameter(
                "--owning-rate/--operating-rate/--repair-rate require --machine-role."
            )
    else:
        if rental_rate is not None:
            raise typer.BadParameter("Use either --rental-rate or --machine-role (not both).")

    dataset_name: str | None = None
    dataset_path: Path | None = None
    scenario_machine: Machine | None = None
    if dataset is not None or machine_id is not None:
        if dataset is None or machine_id is None:
            raise typer.BadParameter("--dataset and --machine must be provided together.")
        dataset_name, scenario, dataset_path = _ensure_dataset(dataset, interactive=False)
        scenario_machine = next((m for m in scenario.machines if m.id == machine_id), None)
        if scenario_machine is None:
            raise typer.BadParameter(
                f"Machine '{machine_id}' not found in dataset '{dataset_name}'. "
                f"Options: {', '.join(sorted(machine.id for machine in scenario.machines))}"
            )
        if machine_role is None:
            if scenario_machine.role is None:
                raise typer.BadParameter(
                    f"Machine '{machine_id}' has no role assigned; specify --machine-role explicitly."
                )
            machine_role = scenario_machine.role
        if usage_hours is None and scenario_machine.repair_usage_hours is not None:
            usage_hours = scenario_machine.repair_usage_hours
        if rental_rate is None and machine_role is None and scenario_machine.operating_cost > 0:
            rental_rate = float(scenario_machine.operating_cost)

    machine_entry: MachineRate | None = None
    rental_breakdown: dict[str, float] | None = None
    repair_reference_hours: int | None = None
    repair_usage_bucket: tuple[int, float] | None = None

    if machine_role is not None:
        machine_entry = _resolve_machine_rate(machine_role)
        composed = compose_default_rental_rate_for_role(
            machine_role,
            include_repair_maintenance=include_repair,
            ownership_override=owning_rate,
            operating_override=operating_rate,
            repair_override=repair_rate,
            usage_hours=usage_hours if include_repair else None,
        )
        if composed is None:
            raise typer.BadParameter(f"No default rate available for role '{machine_role}'.")
        rental_rate, rental_breakdown = composed
        if include_repair and machine_entry.repair_maintenance_cost_per_smh is not None:
            repair_reference_hours = machine_entry.repair_maintenance_reference_hours
            if usage_hours is not None:
                repair_usage_bucket = select_usage_class_multiplier(machine_entry, usage_hours)

    if rental_rate is None:
        raise typer.BadParameter(
            "Provide either --rental-rate or --machine-role (or use --dataset/--machine)."
        )

    prod_info: dict[str, object]
    if productivity is None:
        required = [avg_stem_size, volume_per_ha, stem_density, ground_slope]
        if any(value is None for value in required):
            raise typer.BadParameter(
                "Provide either --productivity or all stand metrics (avg stem size, volume/ha, stem density, slope)."
            )
        assert avg_stem_size is not None
        assert volume_per_ha is not None
        assert stem_density is not None
        assert ground_slope is not None
        if use_rv:
            cost, prod_distribution = estimate_unit_cost_from_distribution(
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
            productivity = prod_distribution.expected_m3_per_pmh
            prod_info = {
                "method": prod_distribution.method,
                "productivity_mean": prod_distribution.expected_m3_per_pmh,
                "productivity_std": prod_distribution.std_m3_per_pmh,
                "samples": prod_distribution.sample_count,
            }
        else:
            cost, prod_point = estimate_unit_cost_from_stand(
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
                "productivity_mean": prod_point.predicted_m3_per_pmh,
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

    rows: list[tuple[str, str]] = []
    if dataset_name is not None:
        rows.append(("Dataset", dataset_name))
        if dataset_path is not None:
            rows.append(("Scenario Path", str(dataset_path)))
    if machine_entry is not None:
        rows.extend(
            [
                ("Machine Role", machine_entry.role),
                ("Machine", machine_entry.machine_name),
                ("Source", machine_entry.source),
            ]
        )
    if scenario_machine is not None:
        rows.append(("Scenario Machine", scenario_machine.id))
        rows.append(
            (
                "Repair Usage Hours (dataset)",
                f"{scenario_machine.repair_usage_hours:,}"
                if scenario_machine.repair_usage_hours is not None
                else "—",
            )
        )
    if rental_breakdown:
        rows.append(("Owning Cost ($/SMH)", f"{rental_breakdown['ownership']:.2f}"))
        rows.append(("Operating Cost ($/SMH)", f"{rental_breakdown['operating']:.2f}"))
        repair_value = rental_breakdown.get("repair_maintenance")
        if repair_value is not None:
            rows.append(("Repair/Maint. ($/SMH)", f"{repair_value:.2f}"))
            if repair_usage_bucket is not None:
                bucket_hours, multiplier = repair_usage_bucket
                rows.append(
                    (
                        "Repair Usage Bucket",
                        f"{bucket_hours:,} h (multiplier {multiplier:.3f})",
                    )
                )
    rows.extend(
        [
            ("Rental Rate ($/SMH)", f"{cost.rental_rate_smh:.2f}"),
            ("Utilisation", f"{cost.utilisation:.3f}"),
            ("Productivity (m³/PMH15)", f"{cost.productivity_m3_per_pmh:.2f}"),
            ("Cost ($/m³)", f"{cost.cost_per_m3:.2f}"),
            ("Productivity Method", str(prod_info["method"])),
        ]
    )
    if prod_info["productivity_std"] is not None:
        rows.append(("Productivity Std", f"{prod_info['productivity_std']:.2f}"))
    rows.append(("Samples", str(prod_info["samples"])))
    _render_kv_table("Machine Cost Estimate", rows)
    if machine_entry and include_repair:
        if repair_usage_bucket is not None and usage_hours is not None:
            bucket_hours, multiplier = repair_usage_bucket
            console.print(
                f"[dim]Repair/maintenance allowance derived from Advantage Vol. 4 No. 23 (closest usage class {bucket_hours / 1000:.0f}×1000 h, multiplier {multiplier:.3f} for requested {usage_hours:,} h).[/dim]"
            )
        elif repair_reference_hours:
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
    table.add_column("Age (y)")
    table.add_column("Volume (m³)")
    table.add_column("DBH (cm)")
    table.add_column("Slope (%)")
    table.add_column("Ground Condition")
    table.add_column("Roughness")
    table.add_column("Operators")
    for entry in filtered[:limit]:
        slope = entry.average_slope_percent
        slope_text = f"{slope:.1f}" if slope is not None else entry.slope_text or "—"
        age_text = (
            f"{entry.stand_age_years:.1f}"
            if entry.stand_age_years is not None
            else entry.stand_age_text or "—"
        )
        volume_text = (
            f"{entry.stem_volume_m3:.3f}"
            if entry.stem_volume_m3 is not None
            else entry.stem_volume_text or "—"
        )
        dbh_text = f"{entry.dbh_cm:.1f}" if entry.dbh_cm is not None else entry.dbh_text or "—"
        operators_text = str(entry.num_operators) if entry.num_operators is not None else "—"
        table.add_row(
            entry.author,
            entry.tree_species or "—",
            age_text,
            volume_text,
            dbh_text,
            slope_text,
            entry.ground_condition or "—",
            entry.ground_roughness or "—",
            operators_text,
        )
    if not filtered:
        console.print("No matching profiles.")
        return
    console.print(table)


@dataset_app.command("estimate-cable-skidding")
def estimate_cable_skidding_cmd(
    model: CableSkiddingModel = typer.Option(CableSkiddingModel.UNVER_SPSS, case_sensitive=False),
    log_volume_m3: float = typer.Option(..., min=0.01, help="Log volume per cycle (m³)."),
    slope_percent: float | None = typer.Option(
        None,
        "--slope-percent",
        min=0.1,
        help="Route slope percent (ignored when --profile is used).",
    ),
    profile: str | None = typer.Option(
        None, "--profile", help="Appendix 5 author/stand name to supply slope defaults."
    ),
    telemetry_log: Path | None = typer.Option(
        None,
        "--telemetry-log",
        help="Append cable-skidding inputs/output to a JSONL telemetry file.",
        dir_okay=False,
        writable=True,
    ),
):
    """Estimate cable skidding productivity (m³/h) using Ünver-Okan (2020) regressions."""

    source_label = "Ünver-Okan 2020 (North-East Turkey spruce uphill skidding)."
    slope_value = slope_percent
    if profile:
        if model is CableSkiddingModel.UNVER_SPSS:
            value = estimate_cable_skidding_productivity_unver_spss_profile(
                profile=profile, log_volume_m3=log_volume_m3
            )
        else:
            value = estimate_cable_skidding_productivity_unver_robust_profile(
                profile=profile, log_volume_m3=log_volume_m3
            )
        slope_value = get_appendix5_profile(profile).average_slope_percent
        rows = [
            ("Model", model.value),
            ("Profile", profile),
            ("Log Volume (m³)", f"{log_volume_m3:.3f}"),
            ("Productivity (m³/h)", f"{value:.2f}"),
        ]
    else:
        if slope_percent is None:
            raise typer.BadParameter(
                "Provide --slope-percent or --profile to supply slope defaults."
            )
        source_label = "Ünver-Okan 2020 (SPSS linear regression, North-East Turkey spruce uphill skidding)."
        if model is CableSkiddingModel.UNVER_ROBUST:
            value = estimate_cable_skidding_productivity_unver_robust(log_volume_m3, slope_percent)
            source_label = "Ünver-Okan 2020 (robust regression, North-East Turkey spruce uphill skidding)."
        else:
            value = estimate_cable_skidding_productivity_unver_spss(log_volume_m3, slope_percent)
        rows = [
            ("Model", model.value),
            ("Log Volume (m³)", f"{log_volume_m3:.3f}"),
            ("Slope (%)", f"{slope_percent:.2f}"),
            ("Productivity (m³/h)", f"{value:.2f}"),
        ]
    console_warning = None
    if model in {CableSkiddingModel.UNVER_SPSS, CableSkiddingModel.UNVER_ROBUST}:
        console_warning = (
            "[yellow]Warning:[/yellow] Ünver-Okan regressions were calibrated outside BC "
            "(North-East Turkey spruce uphill skidding). Use with caution."
        )
    _render_kv_table("Cable Skidding Productivity", rows)
    if source_label:
        console.print(f"[dim]Source: {source_label}[/dim]")
    if console_warning:
        console.print(console_warning)
    if telemetry_log:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "command": "dataset estimate-cable-skidding",
            "model": model.value,
            "profile": profile,
            "slope_percent": slope_value,
            "log_volume_m3": log_volume_m3,
            "productivity_m3_per_h": value,
            "source": source_label,
            "non_bc_source": True,
        }
        append_jsonl(telemetry_log, payload)


@dataset_app.command("estimate-skyline-productivity")
def estimate_skyline_productivity_cmd(
    model: SkylineProductivityModel = typer.Option(
        SkylineProductivityModel.LEE_UPHILL, case_sensitive=False
    ),
    slope_distance_m: float = typer.Option(..., min=1.0, help="Slope yarding distance (m)."),
    lateral_distance_m: float = typer.Option(25.0, min=0.0, help="Lateral yarding distance (m)."),
    payload_m3: float = typer.Option(None, help="Payload per turn (m³). Defaults per source."),
    large_end_diameter_cm: float = typer.Option(
        34.0, min=1.0, help="Required for Lee downhill (cm).", show_default=False
    ),
    num_logs: float | None = typer.Option(
        None,
        "--num-logs",
        min=0.0,
        help="Number of logs per turn (required for TR127 Blocks 5–6).",
    ),
    tr119_treatment: str | None = typer.Option(
        None,
        "--tr119-treatment",
        help="Optional TR119 treatment (e.g., strip_cut, 70_retention, 65_retention) to scale output and show costs.",
    ),
    telemetry_log: Path | None = typer.Option(
        None,
        "--telemetry-log",
        help="Append skyline inputs/output to a JSONL telemetry file.",
        dir_okay=False,
        writable=True,
    ),
):
    """Estimate skyline productivity (m³/PMH) using Lee et al. (2018) or TR-125 regressions."""

    if payload_m3 is not None and payload_m3 <= 0:
        raise typer.BadParameter("--payload-m3 must be > 0 when specified.")

    source_label = None
    console_warning = None
    cycle_minutes = None
    if model is SkylineProductivityModel.LEE_UPHILL:
        value = estimate_cable_yarder_productivity_lee2018_uphill(
            yarding_distance_m=slope_distance_m,
            payload_m3=payload_m3 or 0.57,
        )
        source_label = "Lee et al. 2018 (HAM300 uphill, South Korea)."
        console_warning = (
            "[yellow]Warning:[/yellow] Lee et al. (2018) regressions are non-BC small-scale skyline "
            "studies (South Korea). Validate before using for BC costing."
        )
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Payload (m³)", f"{(payload_m3 or 0.57):.2f}"),
        ]
    elif model is SkylineProductivityModel.LEE_DOWNHILL:
        value = estimate_cable_yarder_productivity_lee2018_downhill(
            yarding_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
            large_end_diameter_cm=large_end_diameter_cm,
            payload_m3=payload_m3 or 0.61,
        )
        source_label = "Lee et al. 2018 (HAM300 downhill, South Korea)."
        console_warning = (
            "[yellow]Warning:[/yellow] Lee et al. (2018) regressions are non-BC small-scale skyline "
            "studies (South Korea). Validate before using for BC costing."
        )
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Lateral Distance (m)", f"{lateral_distance_m:.1f}"),
            ("Large-end Diameter (cm)", f"{large_end_diameter_cm:.1f}"),
            ("Payload (m³)", f"{(payload_m3 or 0.61):.2f}"),
        ]
    elif model is SkylineProductivityModel.TR125_SINGLE:
        value = estimate_cable_yarder_productivity_tr125_single_span(
            slope_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
            payload_m3=payload_m3 or 1.6,
        )
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Lateral Distance (m)", f"{lateral_distance_m:.1f}"),
            ("Payload (m³)", f"{(payload_m3 or 1.6):.2f}"),
        ]
        source_label = "FPInnovations TR-125 single-span regression (coastal BC)."
        cycle_minutes = None
    elif model is SkylineProductivityModel.TR125_MULTI:
        value = estimate_cable_yarder_productivity_tr125_multi_span(
            slope_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
            payload_m3=payload_m3 or 1.6,
        )
        rows = [
            ("Model", model.value),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Lateral Distance (m)", f"{lateral_distance_m:.1f}"),
            ("Payload (m³)", f"{(payload_m3 or 1.6):.2f}"),
        ]
        source_label = "FPInnovations TR-125 multi-span regression (coastal BC)."
        cycle_minutes = None
    elif model in _TR127_MODEL_TO_BLOCK:
        block_id = _TR127_MODEL_TO_BLOCK[model]
        if block_id in (5, 6) and num_logs is None:
            raise typer.BadParameter("--num-logs is required for TR127 Block 5/6 models.")
        cycle_minutes = estimate_cable_yarder_cycle_time_tr127_minutes(
            block=block_id,
            slope_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
            num_logs=num_logs,
        )
        value = estimate_cable_yarder_productivity_tr127(
            block=block_id,
            payload_m3=payload_m3 or 1.6,
            slope_distance_m=slope_distance_m,
            lateral_distance_m=lateral_distance_m,
            num_logs=num_logs,
        )
        rows = [
            ("Model", model.value),
            ("Block", str(block_id)),
            ("Slope Distance (m)", f"{slope_distance_m:.1f}"),
            ("Lateral Distance (m)", f"{lateral_distance_m:.1f}"),
            ("Logs per Turn", f"{num_logs:.1f}" if num_logs is not None else "—"),
            ("Payload (m³)", f"{(payload_m3 or 1.6):.2f}"),
            ("Cycle Time (min)", f"{cycle_minutes:.2f}"),
        ]
        source_label = f"FPInnovations TR-127 Block {block_id} regression (northwestern BC)."
    else:
        raise typer.BadParameter(f"Unsupported skyline model: {model}")
    if tr119_treatment:
        try:
            treatment = get_tr119_treatment(tr119_treatment)
        except KeyError as exc:
            raise typer.BadParameter(str(exc))
        value *= treatment.volume_multiplier
        rows.append(("TR119 Treatment", treatment.treatment))
        rows.append(("TR119 Volume Multiplier", f"{treatment.volume_multiplier:.3f}"))
        if treatment.yarding_total_cost_per_m3 is not None:
            rows.append(("TR119 Yarding Cost ($/m³)", f"{treatment.yarding_total_cost_per_m3:.2f}"))
    rows.append(("Productivity (m³/PMH)", f"{value:.2f}"))
    _render_kv_table("Skyline Productivity", rows)
    if source_label:
        console.print(f"[dim]Source: {source_label}[/dim]")
    if console_warning:
        console.print(console_warning)
    if telemetry_log:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "command": "dataset estimate-skyline",
            "model": model.value,
            "slope_distance_m": slope_distance_m,
            "lateral_distance_m": lateral_distance_m,
            "num_logs": num_logs,
            "payload_m3": payload_m3,
            "cycle_minutes": cycle_minutes,
            "productivity_m3_per_pmh": value,
            "tr119_treatment": tr119_treatment,
            "source": source_label,
            "non_bc_source": bool(console_warning),
        }
        append_jsonl(telemetry_log, payload)
