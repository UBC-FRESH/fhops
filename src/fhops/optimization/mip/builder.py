"""Pyomo builder for the legacy FHOPS day-level MIP (deprecated since 1.0.1, #127).

The builder is kept importable for API compatibility only. It is infeasible for every scenario
whose harvest system has a loader role with machines (see
:mod:`fhops.optimization.mip.deprecation`), and no FHOPS solver uses it any more: ``solve_mip``,
``fhops solve-mip``, ``fhops benchmark`` and the ILS hybrid step all run the operational MILP
(:mod:`fhops.model.milp`).
"""

from __future__ import annotations

import warnings
from collections import defaultdict

import pyomo.environ as pyo

from fhops.optimization.mip.constraints.system_sequencing import apply_system_sequencing_constraints
from fhops.optimization.mip.deprecation import LEGACY_BUILDER_MESSAGE, LegacyMipDeprecationWarning
from fhops.optimization.operational_problem import build_operational_problem
from fhops.scenario.contract import Problem
from fhops.scheduling.mobilisation import MachineMobilisation, build_distance_lookup

__all__ = ["build_model"]


def build_model(pb: Problem) -> pyo.ConcreteModel:
    """Build the legacy FHOPS day-level MIP model (deprecated).

    .. deprecated:: 1.0.1
       Emits :class:`fhops.optimization.mip.deprecation.LegacyMipDeprecationWarning`. The model is
       infeasible whenever a block's harvest system has a loader role with machines (the
       ``system_loader_buffer`` rows demand ``−batch`` m³ of buffer in the first shift), which
       includes the bundled tiny7, small21 and med42 examples. Use the operational MILP
       (:func:`fhops.model.milp.operational.build_operational_model`,
       :func:`fhops.model.milp.driver.solve_operational_milp`).

    Parameters
    ----------
    pb:
        :class:`fhops.scenario.contract.Problem` produced by ``Problem.from_scenario``.  The helper
        must include the full shift list (``pb.shifts``) so the model can build the `(machine, block,
        day, shift)` assignment tensor.

    Returns
    -------
    pyomo.ConcreteModel
        Fully constructed model containing decision variables for assignments/production, optional
        transition binaries (when mobilisation or transition penalties are enabled), and the
        objective/constraints described in the FHOPS roadmap.

    Notes
    -----
    The builder purposely mirrors the documented objective weights:

    * ``ObjectiveWeights.production`` – coefficient for total production.
    * ``ObjectiveWeights.mobilisation`` – coefficient for mobilisation spend derived from transition
      binaries.
    * ``ObjectiveWeights.transitions`` – optional penalty for the number of transitions itself.
    * ``ObjectiveWeights.landing_surplus`` – enables soft landing-capacity overages using surplus
      variables.

    Any change to this function should be reflected in ``docs/howto/thesis_eval.rst`` and the MIP
    section of the API docs.

    ``Scenario.locked_assignments`` are fixed on the assignment variables: a lock without
    ``shift_id`` fixes every shift of its day, a lock with ``shift_id`` fixes only that slot.
    ``Scenario.initial_state`` is **not** modelled by this legacy builder (a ``UserWarning`` is
    emitted); use the operational MILP (:func:`fhops.model.milp.driver.solve_operational_milp`,
    ``fhops solve-mip-operational``) when carrying state into a horizon.
    """

    warnings.warn(LEGACY_BUILDER_MESSAGE, LegacyMipDeprecationWarning, stacklevel=2)
    sc = pb.scenario
    if sc.initial_state is not None:
        warnings.warn(
            "Scenario.initial_state is ignored by the legacy MIP builder; use the operational "
            "MILP (solve-mip-operational) to honour carried-in state.",
            UserWarning,
            stacklevel=2,
        )
    system_ctx = build_operational_problem(pb)

    machines = [machine.id for machine in sc.machines]
    blocks = [block.id for block in sc.blocks]
    shift_list = pb.shifts
    shift_tuples = [(shift.day, shift.shift_id) for shift in shift_list]
    ordered_days = sorted({day for day, _ in shift_tuples})

    rate = {(r.machine_id, r.block_id): r.rate for r in sc.production_rates}
    work_required = {block.id: block.work_required for block in sc.blocks}
    landing_capacity = {landing.id: landing.daily_capacity for landing in sc.landings}

    mobilisation = sc.mobilisation
    mobil_params: dict[str, MachineMobilisation] = {}
    if mobilisation is not None:
        mobil_params = {param.machine_id: param for param in mobilisation.machine_params}
    distance_lookup = build_distance_lookup(mobilisation)

    availability = {(c.machine_id, c.day): int(c.available) for c in sc.calendar}
    shift_availability = (
        {(c.machine_id, c.day, c.shift_id): int(c.available) for c in sc.shift_calendar}
        if sc.shift_calendar
        else {}
    )

    calendar_blackouts: set[tuple[str, int, str]] = set()
    if sc.timeline and sc.timeline.blackouts:
        for blackout in sc.timeline.blackouts:
            for day, shift_id in shift_tuples:
                if blackout.start_day <= day <= blackout.end_day:
                    for machine in sc.machines:
                        calendar_blackouts.add((machine.id, day, shift_id))

    locked_assignments = sc.locked_assignments or []
    locked_slots: set[tuple[str, int, str]] = {
        (lock.machine_id, day, shift_id)
        for lock in locked_assignments
        for day, shift_id in shift_tuples
        if day == lock.day and (lock.shift_id is None or lock.shift_id == shift_id)
    }
    windows = {block_id: sc.window_for(block_id) for block_id in sc.block_ids()}

    model = pyo.ConcreteModel()
    model.M = pyo.Set(initialize=machines)
    model.B = pyo.Set(initialize=blocks)
    model.D = pyo.Set(initialize=ordered_days)
    model.S = pyo.Set(initialize=shift_tuples, dimen=2)

    def within_window(block_id: str, day: int) -> int:
        earliest, latest = windows[block_id]
        return 1 if earliest <= day <= latest else 0

    model.x = pyo.Var(model.M, model.B, model.S, domain=pyo.Binary)
    model.prod = pyo.Var(
        model.M,
        model.B,
        model.S,
        domain=pyo.NonNegativeReals,
        initialize=0.0,
    )

    production_expr = sum(
        model.prod[mach, blk, (day, shift_id)]
        for mach in model.M
        for blk in model.B
        for day, shift_id in model.S
    )

    mobil_cost_expr = 0
    transition_expr = 0
    landing_surplus_expr = 0

    transition_weight = 0.0
    landing_surplus_weight = 0.0
    prod_weight = 1.0
    mobil_weight = 1.0
    if sc.objective_weights is not None:
        prod_weight = sc.objective_weights.production
        mobil_weight = sc.objective_weights.mobilisation
        transition_weight = sc.objective_weights.transitions
        landing_surplus_weight = sc.objective_weights.landing_surplus
    needs_transitions = bool(mobil_params) or transition_weight > 0.0
    enable_landing_surplus = landing_surplus_weight > 0.0

    prev_shift_map: dict[tuple[int, str], tuple[int, str]] = {}
    for idx in range(1, len(shift_tuples)):
        prev_shift_map[shift_tuples[idx]] = shift_tuples[idx - 1]

    if needs_transitions:
        model.S_transition = pyo.Set(initialize=list(prev_shift_map.keys()), dimen=2)

        model.y = pyo.Var(model.M, model.B, model.B, model.S_transition, domain=pyo.Binary)

        def _prev_match_rule(mdl, mach, prev_blk, curr_blk, day, shift_id):
            prev_index = prev_shift_map.get((day, shift_id))
            if prev_index is None:
                return pyo.Constraint.Skip
            prev_day, prev_shift = prev_index
            return (
                mdl.y[mach, prev_blk, curr_blk, (day, shift_id)]
                <= mdl.x[mach, prev_blk, (prev_day, prev_shift)]
            )

        def _curr_match_rule(mdl, mach, prev_blk, curr_blk, day, shift_id):
            return (
                mdl.y[mach, prev_blk, curr_blk, (day, shift_id)]
                <= mdl.x[mach, curr_blk, (day, shift_id)]
            )

        def _link_rule(mdl, mach, prev_blk, curr_blk, day, shift_id):
            prev_index = prev_shift_map.get((day, shift_id))
            if prev_index is None:
                return pyo.Constraint.Skip
            prev_day, prev_shift = prev_index
            return mdl.y[mach, prev_blk, curr_blk, (day, shift_id)] >= (
                mdl.x[mach, prev_blk, (prev_day, prev_shift)]
                + mdl.x[mach, curr_blk, (day, shift_id)]
                - 1
            )

        model.transition_prev = pyo.Constraint(
            model.M, model.B, model.B, model.S_transition, rule=_prev_match_rule
        )
        model.transition_curr = pyo.Constraint(
            model.M, model.B, model.B, model.S_transition, rule=_curr_match_rule
        )
        model.transition_link = pyo.Constraint(
            model.M, model.B, model.B, model.S_transition, rule=_link_rule
        )

        def _mobil_cost(mach: str, prev_blk: str, curr_blk: str) -> float:
            params = mobil_params.get(mach)
            if params is None or prev_blk == curr_blk:
                return 0.0
            distance = distance_lookup.get((prev_blk, curr_blk), 0.0)
            threshold = params.walk_threshold_m
            cost = params.setup_cost
            if distance <= threshold:
                cost += params.walk_cost_per_meter * distance
            else:
                cost += params.move_cost_flat
            return cost

        mobil_cost_expr = sum(
            _mobil_cost(mach, prev_blk, curr_blk)
            * model.y[mach, prev_blk, curr_blk, (day, shift_id)]
            for mach in model.M
            for prev_blk in model.B
            for curr_blk in model.B
            for day, shift_id in model.S_transition
        )

        transition_expr = sum(
            model.y[mach, prev_blk, curr_blk, (day, shift_id)]
            for mach in model.M
            for prev_blk in model.B
            for curr_blk in model.B
            for day, shift_id in model.S_transition
        )

    def mach_one_shift_rule(mdl, mach, day, shift_id):
        if (mach, day, shift_id) in calendar_blackouts:
            return sum(mdl.x[mach, blk, (day, shift_id)] for blk in mdl.B) == 0
        if (mach, day, shift_id) in locked_slots:
            return pyo.Constraint.Skip
        available = shift_availability.get((mach, day, shift_id))
        if available is not None:
            return sum(mdl.x[mach, blk, (day, shift_id)] for blk in mdl.B) <= available
        availability_flag = availability.get((mach, day), 1)
        return sum(mdl.x[mach, blk, (day, shift_id)] for blk in mdl.B) <= availability_flag

    model.mach_one_shift = pyo.Constraint(model.M, model.S, rule=mach_one_shift_rule)

    def prod_cap_rule(mdl, mach, blk, day, shift_id):
        r = rate.get((mach, blk), 0.0)
        w = within_window(blk, day)
        return mdl.prod[mach, blk, (day, shift_id)] <= r * mdl.x[mach, blk, (day, shift_id)] * w

    model.prod_cap = pyo.Constraint(model.M, model.B, model.S, rule=prod_cap_rule)

    def block_cum_rule(mdl, blk):
        return (
            sum(
                mdl.prod[mach, blk, (day, shift_id)]
                for mach in model.M
                for day, shift_id in model.S
            )
            <= work_required[blk]
        )

    model.block_cum = pyo.Constraint(model.B, rule=block_cum_rule)

    blocks_by_landing: dict[str, list[str]] = defaultdict(list)
    for block in sc.blocks:
        blocks_by_landing[block.landing_id].append(block.id)

    landing_ids = sorted(blocks_by_landing.keys())
    model.L = pyo.Set(initialize=landing_ids)

    if enable_landing_surplus:
        model.landing_surplus = pyo.Var(model.L, model.S, domain=pyo.NonNegativeReals)

        def landing_cap_rule(mdl, landing_id, day, shift_id):
            block_ids = blocks_by_landing.get(landing_id, [])
            if not block_ids or len(mdl.M) == 0:
                return pyo.Constraint.Skip
            assignments = sum(
                mdl.x[mach, blk, (day, shift_id)] for mach in model.M for blk in block_ids
            )
            capacity = landing_capacity.get(landing_id, 0)
            return assignments <= capacity + mdl.landing_surplus[landing_id, (day, shift_id)]

        landing_surplus_expr = sum(
            model.landing_surplus[landing_id, (day, shift_id)]
            for landing_id in model.L
            for day, shift_id in model.S
        )
    else:

        def landing_cap_rule(mdl, landing_id, day, shift_id):
            block_ids = blocks_by_landing.get(landing_id, [])
            if not block_ids or len(mdl.M) == 0:
                return pyo.Constraint.Skip
            assignments = sum(
                mdl.x[mach, blk, (day, shift_id)] for mach in model.M for blk in block_ids
            )
            capacity = landing_capacity.get(landing_id, 0)
            return assignments <= capacity

    model.landing_cap = pyo.Constraint(model.L, model.S, rule=landing_cap_rule)

    obj_expr = prod_weight * production_expr
    if mobil_params:
        obj_expr -= mobil_weight * mobil_cost_expr
    if needs_transitions and transition_weight > 0.0:
        obj_expr -= transition_weight * transition_expr
    if enable_landing_surplus and landing_surplus_weight > 0.0:
        obj_expr -= landing_surplus_weight * landing_surplus_expr
    model.obj = pyo.Objective(expr=obj_expr, sense=pyo.maximize)

    sequencing_enabled = getattr(sc, "enforce_sequencing", True)
    apply_system_sequencing_constraints(
        model,
        pb,
        shift_tuples,
        system_ctx=system_ctx,
        sequencing_enabled=sequencing_enabled,
    )

    for lock in locked_assignments:
        lock_slots = [
            (day, shift_id)
            for day, shift_id in model.S
            if day == lock.day and (lock.shift_id is None or lock.shift_id == shift_id)
        ]
        for day, shift_id in lock_slots:
            allowed = shift_availability.get((lock.machine_id, day, shift_id), 1)
            model.x[lock.machine_id, lock.block_id, (day, shift_id)].fix(1 if allowed else 0)
        for other_blk in blocks:
            if other_blk != lock.block_id:
                for day, shift_id in lock_slots:
                    model.x[lock.machine_id, other_blk, (day, shift_id)].fix(0)

    return model
