"""Operational MILP driver (solve + watch wrappers)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
import pyomo.environ as pyo
from pyomo.opt import SolverFactory

from fhops.evaluation.sequencing import SequencingTracker, build_role_priority
from fhops.model.milp.data import OperationalMilpBundle, ShiftKey
from fhops.model.milp.operational import build_operational_model
from fhops.optimization.operational_problem import OperationalProblem

ASSIGNMENT_COLUMNS = [
    "machine_id",
    "block_id",
    "day",
    "shift_id",
    "assigned",
    "production",
]

__all__ = ["solve_operational_milp"]


@dataclass(slots=True)
class _IncumbentState:
    assignment_lookup: dict[tuple[str, ShiftKey], str]
    production_lookup: dict[tuple[str, str, ShiftKey], float]
    role_prod_lookup: dict[tuple[str, str, ShiftKey], float]
    role_assignment_counts: dict[tuple[str, str, ShiftKey], int]
    landing_usage: dict[tuple[str, int], int]
    leftover_by_block: dict[str, float]
    block_terminal_total: dict[str, float] | None = None
    block_generic_total: dict[str, float] | None = None


def solve_operational_milp(
    bundle: OperationalMilpBundle,
    solver: str = "highs",
    time_limit: int | None = None,
    gap: float | None = None,
    tee: bool = False,
    solver_options: Mapping[str, object] | None = None,
    incumbent_assignments: pd.DataFrame | None = None,
    context: OperationalProblem | None = None,
) -> dict[str, Any]:
    """
    Solve the operational MILP given a prepared bundle.

    Parameters
    ----------
    bundle :
        Operational bundle emitted by :func:`fhops.model.milp.operational.build_operational_model`.
    solver :
        Solver name understood by ``pyomo.opt.SolverFactory`` (``highs`` by default, ``gurobi`` for
        large ladders).
    time_limit :
        Optional second budget forwarded to the solver (``None`` leaves the solver default).
    gap :
        Optional relative MIP gap target (0–1). We set both ``mipgap`` (Gurobi/CPLEX style) and
        ``mip_rel_gap`` (HiGHS style) so callers do not need to remember solver-specific keywords.
    tee :
        When ``True`` stream the solver log to stdout.
    solver_options :
        Additional ``name → value`` overrides forwarded verbatim to the solver (e.g.,
        ``{"Threads": 36, "LogFile": "med42.log"}`` for Gurobi).
    incumbent_assignments :
        Optional :class:`pandas.DataFrame` with ``machine_id``, ``block_id``, ``day``, ``shift_id``,
        and optional ``assigned``/``production`` columns. When provided we derive every state
        variable implied by the schedule (assignments, production, transitions, mobilisation flags,
        inventories, landing surplus) and request a Pyomo warm start. The solver will still discard
        the start if the incumbent is weak; right now only tiny7/small21 benefit measurably, whereas
        med42/large84 respond better to the solver’s own heuristics.
    context :
        :class:`fhops.optimization.operational_problem.OperationalProblem` describing the scenario.
        Required if the incumbent needs to be expanded into loader and landing state (the CLI and
        benchmark harness populate this automatically).

    Returns
    -------
    dict
        Dictionary carrying ``objective``, ``production``, ``assignments`` (DataFrame), and solver
        status/termination metadata. ``objective`` is ``None`` when the solver fails.

    Notes
    -----
    The warm-start plumbing is “best effort”: setting ``incumbent_assignments`` is always safe, but
    it only accelerates a solve if the incumbent is close to feasible for the operational MILP.
    Today that means tiny7/small21 runs reuse the incumbent immediately, while med42/large84 usually
    ignore the seed and rely on Gurobi/HiGHS built-in heuristics.
    """

    model = build_operational_model(bundle)
    meta = getattr(model, "_warm_start_meta", None)
    if meta is not None and context is not None:
        meta["operational_problem"] = context
    seeded = 0
    if incumbent_assignments is not None:
        seeded = _apply_incumbent_start(model, incumbent_assignments)

    opt = SolverFactory(solver)
    if time_limit is not None:
        opt.options["time_limit"] = time_limit
    if gap is not None:
        # Different solvers expect different gap parameter names.
        opt.options["mipgap"] = gap  # Gurobi/CPLEX-style
        if solver.lower() not in {"gurobi", "cplex"}:
            opt.options["mip_rel_gap"] = gap  # HiGHS-style
    if solver_options:
        for key, value in solver_options.items():
            opt.options[str(key)] = value
    solve_kwargs: dict[str, object] = {"tee": tee, "load_solutions": True}
    if seeded > 0:
        solve_kwargs["warmstart"] = True
    result = opt.solve(model, **solve_kwargs)
    status = str(result.solver.status).lower()
    termination = str(result.solver.termination_condition).lower()
    solved = termination in {"optimal", "feasible"} or status in {"optimal", "feasible"}
    if solved:
        assignments = _extract_assignments(model)
        prod = sum(pyo.value(model.prod[idx]) for idx in model.prod)
    else:
        assignments = pd.DataFrame(columns=ASSIGNMENT_COLUMNS)
        prod = 0.0
    return {
        "objective": pyo.value(model.objective) if solved else None,
        "production": prod,
        "assignments": assignments,
        "solver_status": str(result.solver.status),
        "termination_condition": str(result.solver.termination_condition),
    }


def _extract_assignments(model: pyo.ConcreteModel) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (machine_id, block_id, day, shift_id), var in model.x.items():
        assigned_value = pyo.value(var)
        production_value = pyo.value(model.prod[machine_id, block_id, (day, shift_id)])
        if assigned_value > 0.5 or production_value > 1e-6:
            rows.append(
                {
                    "machine_id": machine_id,
                    "block_id": block_id,
                    "day": int(day),
                    "shift_id": shift_id,
                    "assigned": int(assigned_value > 0.5),
                    "production": float(production_value),
                }
            )
    if rows:
        return pd.DataFrame(rows, columns=ASSIGNMENT_COLUMNS)
    return pd.DataFrame(columns=ASSIGNMENT_COLUMNS)


def _apply_incumbent_start(model: pyo.ConcreteModel, assignments: pd.DataFrame | None) -> int:
    """
    Populate Pyomo variable starting values from an incumbent assignment matrix.

    Parameters
    ----------
    model :
        Operational Pyomo model returned by :func:`build_operational_model`.
    assignments :
        DataFrame with at least ``machine_id``, ``block_id``, ``day``, and ``shift_id`` columns,
        optionally carrying ``assigned``/``production`` floats.

    Returns
    -------
    int
        Count of assignment slots seeded (used to decide whether Pyomo should enable ``warmstart``).

    Notes
    -----
    When the operational builder attaches warm-start metadata we reconstruct the entire schedule
    state (transition binaries, activation flags, loader inventories, landing surplus, leftovers).
    Otherwise we fall back to seeding only the ``x``/``prod`` variables so callers can still supply a
    partial incumbent. Solvers may still discard the start if other integer variables remain unset
    or if the incumbent violates constraints by a large margin.
    """

    if assignments is None or assignments.empty:
        return 0

    required = {"machine_id", "block_id", "day", "shift_id"}
    missing = required - set(assignments.columns)
    if missing:
        raise ValueError(
            "Incumbent assignments missing required columns: " + ", ".join(sorted(missing))
        )

    meta = getattr(model, "_warm_start_meta", None)
    if meta is None:
        return _seed_basic_assignments(model, assignments)

    state = _build_incumbent_state(model, assignments, meta)
    if state is None or not state.assignment_lookup:
        return _seed_basic_assignments(model, assignments)
    _seed_model_from_state(model, meta, state)
    return len(state.assignment_lookup)


def _seed_basic_assignments(model: pyo.ConcreteModel, assignments: pd.DataFrame) -> int:
    """Fallback seeding that only sets x/prod for provided rows."""

    seeded = 0
    has_assigned = "assigned" in assignments.columns
    has_production = "production" in assignments.columns
    for row in assignments.itertuples(index=False):
        machine_id = getattr(row, "machine_id")
        block_id = getattr(row, "block_id")
        day_value = getattr(row, "day")
        shift_value = getattr(row, "shift_id")

        try:
            day = int(day_value)
        except (TypeError, ValueError):
            continue
        shift_id = str(shift_value)
        shift_tuple = (day, shift_id)
        try:
            x_var = model.x[machine_id, block_id, shift_tuple]
        except KeyError:
            continue

        assigned_val = 1.0
        if has_assigned:
            assigned_raw = getattr(row, "assigned")
            if pd.notna(assigned_raw):
                try:
                    assigned_val = float(assigned_raw)
                except (TypeError, ValueError):
                    assigned_val = 1.0
        if assigned_val <= 0:
            continue

        x_var.set_value(1.0)
        x_var.stale = False
        seeded += 1

        if has_production:
            prod_raw = getattr(row, "production")
            if pd.notna(prod_raw):
                try:
                    prod_val = float(prod_raw)
                except (TypeError, ValueError):
                    continue
                try:
                    prod_var = model.prod[machine_id, block_id, shift_tuple]
                except KeyError:
                    continue
                prod_var.set_value(prod_val)
                prod_var.stale = False

    return seeded


def _derive_state_with_tracker(
    ctx: OperationalProblem,
    bundle: OperationalMilpBundle,
    assignment_lookup: dict[tuple[str, ShiftKey], str],
    provided_prod: dict[tuple[str, str, ShiftKey], float],
) -> dict[str, dict]:
    sc = ctx.problem.scenario
    shift_keys = ctx.shift_keys
    rate = bundle.production_rates
    machine_roles = bundle.machine_roles
    allowed_roles = ctx.allowed_roles
    windows = bundle.windows
    availability_day = bundle.availability_day
    availability_shift = bundle.availability_shift
    blackout = ctx.blackout_shifts
    locked = ctx.locked_assignments
    landing_of = bundle.landing_for_block

    plan: dict[str, dict[ShiftKey, str | None]] = {
        machine.id: {shift: None for shift in shift_keys} for machine in sc.machines
    }
    for (machine_id, shift), block_id in assignment_lookup.items():
        if machine_id in plan:
            plan[machine_id][shift] = block_id

    tracker = SequencingTracker(ctx)
    role_priority = build_role_priority(ctx)
    ordered_machines = sorted(
        sc.machines,
        key=lambda m: (role_priority.get(machine_roles.get(m.id) or "", 999), m.id),
    )

    production_lookup: dict[tuple[str, str, ShiftKey], float] = {}
    role_prod_lookup: defaultdict[tuple[str, str, ShiftKey], float] = defaultdict(float)
    role_assignment_counts: defaultdict[tuple[str, str, ShiftKey], int] = defaultdict(int)
    landing_usage: defaultdict[tuple[str, int], int] = defaultdict(int)

    for day, shift_id in shift_keys:
        for machine in ordered_machines:
            slot_block: str | None = plan[machine.id].get((day, shift_id))
            lock_key = (machine.id, day)
            assigned_block = slot_block
            if lock_key in locked:
                assigned_block = locked[lock_key]

            if (
                availability_shift.get((machine.id, day, shift_id), 1) == 0
                or availability_day.get((machine.id, day), 1) == 0
                or (machine.id, day, shift_id) in blackout
            ):
                continue

            if assigned_block is None:
                continue

            role = machine_roles.get(machine.id)
            allowed = allowed_roles.get(assigned_block)
            if allowed is not None and role is not None and role not in allowed:
                continue

            earliest, latest = windows[assigned_block]
            if day < earliest or day > latest:
                continue

            rate_value = rate.get((machine.id, assigned_block), 0.0)
            if rate_value <= 0.0:
                continue

            key = (machine.id, assigned_block, (day, shift_id))
            proposed = provided_prod.get(key, rate_value)
            sequencing = tracker.process(day, machine.id, assigned_block, proposed)
            prod_units = max(0.0, sequencing.production_units)
            production_lookup[key] = prod_units

            if role is not None:
                role_key = (role, assigned_block, (day, shift_id))
                role_prod_lookup[role_key] += prod_units
                role_assignment_counts[role_key] += 1

            landing_id = landing_of.get(assigned_block)
            if landing_id is not None:
                landing_usage[(landing_id, day)] += 1

    tracker.finalize()
    leftover_by_block = {
        block_id: max(0.0, remaining) for block_id, remaining in tracker.remaining_work.items()
    }

    return {
        "production_lookup": production_lookup,
        "role_prod_lookup": dict(role_prod_lookup),
        "role_assignment_counts": dict(role_assignment_counts),
        "landing_usage": dict(landing_usage),
        "leftover_by_block": leftover_by_block,
    }


def _derive_state_with_rates(
    bundle: OperationalMilpBundle,
    assignment_lookup: dict[tuple[str, ShiftKey], str],
    provided_prod: dict[tuple[str, str, ShiftKey], float],
    terminal_pairs: set[tuple[str, str]],
) -> dict[str, dict]:
    machine_roles = bundle.machine_roles
    landing_for_block = bundle.landing_for_block
    production_lookup: dict[tuple[str, str, ShiftKey], float] = {}
    role_prod_lookup: defaultdict[tuple[str, str, ShiftKey], float] = defaultdict(float)
    role_assignment_counts: defaultdict[tuple[str, str, ShiftKey], int] = defaultdict(int)
    landing_usage: defaultdict[tuple[str, int], int] = defaultdict(int)
    block_terminal_total: defaultdict[str, float] = defaultdict(float)
    block_generic_total: defaultdict[str, float] = defaultdict(float)

    for (machine_id, shift), block_id in assignment_lookup.items():
        key = (machine_id, block_id, shift)
        if key in provided_prod:
            prod_val = provided_prod[key]
        else:
            prod_val = bundle.production_rates.get((machine_id, block_id), 0.0)
        production_lookup[key] = prod_val
        block_generic_total[block_id] += prod_val
        role = machine_roles.get(machine_id)
        if role:
            role_key = (role, block_id, shift)
            role_prod_lookup[role_key] += prod_val
            role_assignment_counts[role_key] += 1
            if (role, block_id) in terminal_pairs:
                block_terminal_total[block_id] += prod_val
        landing_id = landing_for_block.get(block_id)
        if landing_id is not None:
            landing_usage[(landing_id, shift[0])] += 1

    leftover_by_block = {
        blk: max(0.0, bundle.work_required.get(blk, 0.0) - block_generic_total.get(blk, 0.0))
        for blk in bundle.blocks
    }

    return {
        "production_lookup": production_lookup,
        "role_prod_lookup": dict(role_prod_lookup),
        "role_assignment_counts": dict(role_assignment_counts),
        "landing_usage": dict(landing_usage),
        "leftover_by_block": leftover_by_block,
        "block_terminal_total": dict(block_terminal_total),
        "block_generic_total": dict(block_generic_total),
    }


def _build_incumbent_state(
    model: pyo.ConcreteModel, assignments: pd.DataFrame, meta: Mapping[str, Any]
) -> _IncumbentState | None:
    bundle: OperationalMilpBundle | None = meta.get("bundle")
    shift_list: tuple[ShiftKey, ...] | None = meta.get("shift_list")
    if bundle is None or not shift_list:
        return None

    shift_lookup = {shift for shift in model.S}
    machines = set(bundle.machines)
    blocks = set(bundle.blocks)
    terminal_pairs = set(meta.get("terminal_pairs", ()))

    assignment_lookup: dict[tuple[str, ShiftKey], str] = {}
    provided_production: dict[tuple[str, str, ShiftKey], float] = {}

    has_assigned = "assigned" in assignments.columns
    has_production = "production" in assignments.columns

    for row in assignments.itertuples(index=False):
        machine_id = str(getattr(row, "machine_id"))
        if machine_id not in machines:
            raise ValueError(f"Incumbent references unknown machine_id={machine_id}")

        block_raw = getattr(row, "block_id")
        if pd.isna(block_raw):
            continue
        block_id = str(block_raw)
        if block_id not in blocks:
            raise ValueError(f"Incumbent references unknown block_id={block_id}")

        try:
            day = int(getattr(row, "day"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid incumbent day for machine={machine_id}") from exc
        shift_id = str(getattr(row, "shift_id"))
        shift_tuple: ShiftKey = (day, shift_id)
        if shift_tuple not in shift_lookup:
            raise ValueError(
                f"Incumbent references shift {(day, shift_id)} that is not in the MILP grid"
            )

        assigned_val = 1.0
        if has_assigned:
            assigned_raw = getattr(row, "assigned")
            if pd.notna(assigned_raw):
                try:
                    assigned_val = float(assigned_raw)
                except (TypeError, ValueError):
                    assigned_val = 1.0
        if assigned_val <= 0:
            continue

        slot_key = (machine_id, shift_tuple)
        if slot_key in assignment_lookup:
            raise ValueError(
                f"Duplicate incumbent row for machine={machine_id} day={day} shift={shift_id}"
            )
        assignment_lookup[slot_key] = block_id

        if has_production:
            prod_raw = getattr(row, "production")
            if pd.notna(prod_raw):
                try:
                    prod_val = max(0.0, float(prod_raw))
                except (TypeError, ValueError):
                    prod_val = 0.0
                provided_production[(machine_id, block_id, shift_tuple)] = prod_val

    context: OperationalProblem | None = meta.get("operational_problem")
    if context is not None:
        derived = _derive_state_with_tracker(
            context,
            bundle,
            assignment_lookup,
            provided_production,
        )
        return _IncumbentState(
            assignment_lookup=assignment_lookup,
            production_lookup=derived["production_lookup"],
            role_prod_lookup=derived["role_prod_lookup"],
            role_assignment_counts=derived["role_assignment_counts"],
            landing_usage=derived["landing_usage"],
            leftover_by_block=derived["leftover_by_block"],
        )

    # Fallback derivation relies on raw production rates.
    derived = _derive_state_with_rates(
        bundle,
        assignment_lookup,
        provided_production,
        terminal_pairs,
    )
    return _IncumbentState(
        assignment_lookup=assignment_lookup,
        production_lookup=derived["production_lookup"],
        role_prod_lookup=derived["role_prod_lookup"],
        role_assignment_counts=derived["role_assignment_counts"],
        landing_usage=derived["landing_usage"],
        leftover_by_block=derived["leftover_by_block"],
        block_terminal_total=derived["block_terminal_total"],
        block_generic_total=derived["block_generic_total"],
    )


def _seed_model_from_state(
    model: pyo.ConcreteModel, meta: Mapping[str, Any], state: _IncumbentState
) -> None:
    bundle: OperationalMilpBundle = meta["bundle"]
    assignment_lookup = state.assignment_lookup
    production_lookup = state.production_lookup
    role_prod_lookup = state.role_prod_lookup
    role_assignment_counts = state.role_assignment_counts
    landing_usage = state.landing_usage
    shift_list: tuple[ShiftKey, ...] = meta.get("shift_list") or tuple(model.S)
    prev_shift_map: Mapping[ShiftKey, ShiftKey | None] = meta.get("prev_shift_map", {})
    inventory_pairs: tuple[tuple[str, str], ...] = tuple(meta.get("inventory_pairs", ()))
    role_upstream: Mapping[tuple[str, str], tuple[str, ...]] = meta.get("role_upstream", {})
    loader_batch_volume: Mapping[tuple[str, str], float] = meta.get("loader_batch_volume", {})
    block_terminal_roles: Mapping[str, tuple[str, ...]] = meta.get("block_terminal_roles", {})

    def _slot_key(day: int, shift_id: str) -> ShiftKey:
        return (int(day), str(shift_id))

    for (machine_id, block_id, day, shift_id), var in model.x.items():
        shift = _slot_key(day, shift_id)
        value = 1.0 if assignment_lookup.get((machine_id, shift)) == block_id else 0.0
        var.set_value(value)
        var.stale = False

    for (machine_id, block_id, day, shift_id), var in model.prod.items():
        shift = _slot_key(day, shift_id)
        key = (machine_id, block_id, shift)
        var.set_value(production_lookup.get(key, 0.0))
        var.stale = False

    for (role, block_id, day, shift_id), var in model.role_prod.items():
        shift = _slot_key(day, shift_id)
        key = (role, block_id, shift)
        var.set_value(role_prod_lookup.get(key, 0.0))
        var.stale = False

    if hasattr(model, "y"):
        for (machine_id, prev_blk, curr_blk, day, shift_id), var in model.y.items():
            shift = _slot_key(day, shift_id)
            prev_slot = prev_shift_map.get(shift)
            value = 0.0
            if prev_slot is not None:
                prev_block = assignment_lookup.get((machine_id, prev_slot))
                curr_block = assignment_lookup.get((machine_id, shift))
                if prev_block == prev_blk and curr_block == curr_blk:
                    value = 1.0
            var.set_value(value)
            var.stale = False

    if hasattr(model, "role_active"):
        for (role, block_id, day, shift_id), var in model.role_active.items():
            shift = _slot_key(day, shift_id)
            key = (role, block_id, shift)
            var.set_value(1.0 if role_assignment_counts.get(key, 0) > 0 else 0.0)
            var.stale = False

    if hasattr(model, "loads") and hasattr(model, "loader_partial"):
        for (role, block_id, day, shift_id), load_var in model.loads.items():
            shift = _slot_key(day, shift_id)
            batch = loader_batch_volume.get((role, block_id), 0.0)
            prod_value = role_prod_lookup.get((role, block_id, shift), 0.0)
            if batch > 0:
                full_loads = int(prod_value // batch)
                remainder = prod_value - full_loads * batch
                if remainder >= batch - 1e-6:
                    full_loads += 1
                    remainder = 0.0
            else:
                full_loads = 0
                remainder = prod_value
            load_var.set_value(full_loads)
            load_var.stale = False
            loader_partial = model.loader_partial[role, block_id, day, shift_id]
            loader_partial.set_value(remainder)
            loader_partial.stale = False

    if hasattr(model, "landing_surplus") and hasattr(model, "Landing"):
        for landing_id in model.Landing:
            cap = bundle.landing_capacity.get(landing_id, 0)
            for day in model.D:
                usage = landing_usage.get((landing_id, day), 0)
                surplus = max(0.0, float(usage - cap))
                var = model.landing_surplus[landing_id, day]
                var.set_value(surplus)
                var.stale = False

    if inventory_pairs:
        inventory_prev: dict[tuple[str, str], float] = {pair: 0.0 for pair in inventory_pairs}
        for day, shift_id in shift_list:
            shift = _slot_key(day, shift_id)
            for role, block_id in inventory_pairs:
                start_value = inventory_prev[(role, block_id)]
                inv_start = model.inventory_start[role, block_id, day, shift_id]
                inv_start.set_value(start_value)
                inv_start.stale = False
                upstream_roles = role_upstream.get((role, block_id), ())
                upstream_sum = sum(
                    role_prod_lookup.get((up_role, block_id, shift), 0.0)
                    for up_role in upstream_roles
                )
                consumed = role_prod_lookup.get((role, block_id, shift), 0.0)
                end_value = start_value + upstream_sum - consumed
                if end_value < -1e-5:
                    end_value = 0.0
                else:
                    end_value = max(0.0, end_value)
                inv_var = model.inventory[role, block_id, day, shift_id]
                inv_var.set_value(end_value)
                inv_var.stale = False
                inventory_prev[(role, block_id)] = end_value

    leftover_map = state.leftover_by_block or {}
    for block_id in model.B:
        if leftover_map:
            leftover_val = leftover_map.get(block_id, 0.0)
        else:
            required = bundle.work_required.get(block_id, 0.0)
            terminal_roles = block_terminal_roles.get(block_id)
            if terminal_roles:
                completed = (
                    state.block_terminal_total.get(block_id, 0.0)
                    if state.block_terminal_total
                    else 0.0
                )
            else:
                completed = (
                    state.block_generic_total.get(block_id, 0.0)
                    if state.block_generic_total
                    else 0.0
                )
            leftover_val = max(0.0, required - completed)
        var = model.leftover[block_id]
        var.set_value(leftover_val)
        var.stale = False
