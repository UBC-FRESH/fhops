"""Operational MILP builder (day × shift grid).

Builds the Pyomo model of the canonical operational formulation
(``docs/softwarex/manuscript/sections/includes/fhops_operational_formulation.md``) from an
:class:`~fhops.model.milp.data.OperationalMilpBundle`. The driver
(:mod:`fhops.model.milp.driver`) solves it; the heuristics and the playback sequencing tracker
(:mod:`fhops.evaluation.sequencing`) apply the same sequencing rules, so MILP plans replay without
violations.
"""

from __future__ import annotations

from collections import defaultdict

import pyomo.environ as pyo

from fhops.model.milp.data import (
    OperationalMilpBundle,
    headstart_buffer_volumes,
    machine_slot_available,
    resolve_locked_slots,
)

__all__ = ["build_operational_model"]

_REDUNDANCY_TOLERANCE = 1e-6


def build_operational_model(bundle: OperationalMilpBundle) -> pyo.ConcreteModel:
    """Construct a Pyomo model from an :class:`OperationalMilpBundle`.

    Parameters
    ----------
    bundle:
        Normalised operational data (see :func:`fhops.model.milp.data.build_operational_bundle`).

    Returns
    -------
    pyomo.ConcreteModel
        Maximisation model implementing the canonical operational formulation
        (``docs/softwarex/manuscript/sections/includes/fhops_operational_formulation.md``). The
        model carries a ``_warm_start_meta`` dict used by
        :func:`fhops.model.milp.driver.solve_operational_milp` to seed incumbents; its
        ``"warnings"`` entry lists locks the model had to drop or pin to zero (see
        :func:`fhops.model.milp.data.resolve_locked_slots`).

    Notes
    -----
    Sequencing rules shared with the playback tracker and the heuristics (#109, #115; see
    ``docs/howto/system_sequencing.rst``):

    * **Staged inventories per upstream role (E7).** ``inventory[u, b, s]`` is the output of role
      ``u`` on block ``b`` not yet consumed by its downstream roles (``model.InventoryPairs``
      holds every ``(u, b)`` with at least one downstream role). Every downstream role ``r`` of
      ``u`` consumes its own output ``z_r`` from it, and ``inventory_guard`` requires
      ``Σ_{r downstream of u} z_r ≤ inventory_start[u]`` for **every** upstream role, so a role
      with several upstream roles (a join) can only process what each of them has staged — the
      tracker's minimum rule. For linear chains this is the v1.0.0/1.0.0 model with the inventory
      indexed by the upstream instead of the downstream role.
    * ``role_remaining_cap`` limits every role's total output on a block to
      ``R_{r,b} = min(role_remaining, W_b)`` (``role_remaining`` defaults to ``W_b``).
    * ``head_start`` requires the staged volume of every upstream role at the end of the previous
      slot to cover the buffer ``B_{r,b}`` (:func:`fhops.model.milp.data.headstart_buffer_volumes`)
      when the role produces (``role_active = 1``); ``upstream_done_link`` waives it once every
      upstream role has output its carried-in remaining volume (binary ``upstream_done``,
      cumulative output ``role_cumulative``).
    * ``loader_threshold`` requires the staged volume of every upstream role of a loader to cover
      ``min(q_batch, W_b − D_b(<s))`` when the loader produces, where ``D_b(<s)`` is the terminal
      output delivered before the slot (the tracker's dynamic truckload rule). Slots in which the
      remaining volume cannot drop below a truckload use ``q_batch``; blocks no larger than a
      truckload use the remaining volume; otherwise a monotone binary ``loader_tail[b, s]``
      (1 once the remaining volume is at most ``q_batch``) selects the active term.
    * ``role_active`` gates production only (``activation_prod``). An **unlocked** assigned
      machine of the role forces ``role_active = 1`` (``role_active_upper``), so unlocked plans
      keep the published semantics; a locked machine may be assigned and idle (``x = 1``,
      production 0) when its role has nothing to process, so locks never make the model
      infeasible through the activation coupling.
    * ``role_slot_remaining`` adds ``z_r(s) + D_b(≤s) ≤ W_b`` for non-terminal roles whenever it
      is not implied by the flow balances (systems with forks/several terminal roles, or carried-in
      staged inventory inconsistent with ``role_remaining``), matching the tracker's cap of each
      assignment at the block's remaining volume.
    * Blocks listed in ``bundle.unsequenced_blocks`` (no ``harvest_system_id``) have no role
      constraints; all machine production counts towards their balance and the objective.

    Availability ``A_{m,s}`` combines the day/shift calendars with ``bundle.blackout_slots``
    (timeline blackouts, #110): ``machine_capacity`` forces ``Σ_b x[m,b,s] = 0`` in unavailable
    slots.

    Initial state and locks (no-ops for default bundles):

    * ``bundle.initial_staged_inventory`` sets the first-slot ``inventory_start[u, b]`` of each
      upstream role to its carried-in staged volume; head-start and loader thresholds at the first
      slot use the same value.
    * ``bundle.initial_role_remaining`` sets ``R_{r,b}`` (capped at ``W_b``) and the head-start
      waiver threshold.
    * ``bundle.initial_machine_block`` adds a linear boundary term on the first slot:
      ``-(ω_mob·δ(m,b0,b) + ω_trans)·x[m,b,first]`` for ``b ≠ b0``.
    * ``bundle.locked_assignments`` adds ``locked_assignment`` equality constraints resolved by
      :func:`fhops.model.milp.data.resolve_locked_slots`: a day lock pins every available shift of
      the day to its block (other blocks 0); a shift lock pins only its slot. Unavailable slots and
      contradictory locks (outside the block window, role not in the block's system) are pinned to
      0; the latter are reported in ``_warm_start_meta["warnings"]``.
    """

    model = pyo.ConcreteModel()

    machines = bundle.machines
    blocks = bundle.blocks
    shifts = bundle.shifts
    days = bundle.days

    model.M = pyo.Set(initialize=machines)
    model.B = pyo.Set(initialize=blocks)
    model.D = pyo.Set(initialize=days)
    model.S = pyo.Set(initialize=shifts, dimen=2)

    shift_list = list(shifts)
    prev_shift_map: dict[tuple[int, str], tuple[int, str] | None] = {}
    for idx, slot in enumerate(shift_list):
        prev_shift_map[slot] = shift_list[idx - 1] if idx > 0 else None

    machine_roles = bundle.machine_roles
    role_to_machines: dict[str, list[str]] = defaultdict(list)
    for machine_id, role in machine_roles.items():
        if role:
            role_to_machines[role].append(machine_id)

    block_system = bundle.block_system
    system_configs = bundle.systems
    block_roles: dict[str, tuple[str, ...]] = {}
    role_block_pairs: list[tuple[str, str]] = []
    activation_pairs: list[tuple[str, str]] = []
    loader_pairs: list[tuple[str, str]] = []
    loader_gate_pairs: list[tuple[str, str]] = []
    role_upstream: dict[tuple[str, str], tuple[str, ...]] = {}
    role_buffer_volume: dict[tuple[str, str], float] = {}
    role_capacity: dict[tuple[str, str], float] = {}
    loader_batch_volume: dict[tuple[str, str], float] = {}
    block_terminal_roles: dict[str, tuple[str, ...]] = {}
    terminal_pairs: list[tuple[str, str]] = []
    # Staged inventories are indexed by the *upstream* role: (u, b) -> downstream roles of u.
    stage_pairs: list[tuple[str, str]] = []
    stage_downstream: dict[tuple[str, str], list[str]] = {}
    mobilisation_params = bundle.mobilisation_params
    mobilisation_distances = bundle.mobilisation_distances

    headstart_volumes = headstart_buffer_volumes(bundle)
    headstart_pairs: list[tuple[str, str]] = []

    # Carried-in remaining output of a role (R^0_{r,b}; W_b by default). The waiver compares the
    # cumulative upstream output with this value (the tracker's role_remaining); the output cap
    # uses min(R^0, W_b) because no role can handle more wood than the block still holds.
    def _role_remaining_raw(role: str, blk: str) -> float:
        return bundle.initial_role_remaining.get((blk, role), bundle.work_required[blk])

    def _role_remaining(role: str, blk: str) -> float:
        return min(_role_remaining_raw(role, blk), bundle.work_required[blk])

    system_terminal_roles: dict[str, tuple[str, ...]] = {}
    system_downstream: dict[str, dict[str, set[str]]] = {}
    for system in system_configs.values():
        downstream: dict[str, set[str]] = defaultdict(set)
        for role_cfg in system.roles:
            role_name = role_cfg.role
            if not role_name:
                continue
            for upstream in role_cfg.upstream_roles:
                downstream[upstream].add(role_name)
        terminal_roles = tuple(
            role_cfg.role
            for role_cfg in system.roles
            if role_cfg.role and not downstream.get(role_cfg.role)
        )
        system_terminal_roles[system.system_id] = terminal_roles
        system_downstream[system.system_id] = downstream

    unsequenced = frozenset(bundle.unsequenced_blocks)
    for block in blocks:
        if block in unsequenced:
            # No harvest_system_id: no role obligations (data contract), every machine's output
            # counts towards W_b, as in the sequencing tracker and heuristics.
            block_roles[block] = ()
            block_terminal_roles[block] = ()
            continue
        system_id = block_system[block]
        system_cfg = system_configs[system_id]
        roles_for_block: list[str] = []
        for role_cfg in system_cfg.roles:
            role_name = role_cfg.role
            pair = (role_name, block)
            role_block_pairs.append(pair)
            role_upstream[pair] = role_cfg.upstream_roles
            roles_for_block.append(role_name)

            cap = sum(
                bundle.production_rates.get((machine_id, block), 0.0)
                for machine_id in role_to_machines.get(role_name, [])
            )
            if cap <= 0:
                cap = 1.0
            role_capacity[pair] = cap

            buffer_volume = headstart_volumes.get((block, role_name), 0.0)
            if buffer_volume > 0 and role_cfg.upstream_roles:
                headstart_pairs.append(pair)
            role_buffer_volume[pair] = buffer_volume
            loader_gate = bool(
                role_cfg.is_loader
                and role_cfg.upstream_roles
                and system_cfg.loader_batch_volume_m3 > 0
                and bundle.work_required[block] > 0
            )
            if loader_gate:
                loader_gate_pairs.append(pair)

            if role_cfg.upstream_roles:
                for upstream_role in role_cfg.upstream_roles:
                    stage = (upstream_role, block)
                    if stage not in stage_downstream:
                        stage_pairs.append(stage)
                        stage_downstream[stage] = []
                    if role_name not in stage_downstream[stage]:
                        stage_downstream[stage].append(role_name)
                if (buffer_volume > 0) or loader_gate:
                    activation_pairs.append(pair)
            loader_batch_volume[pair] = system_cfg.loader_batch_volume_m3
            if role_cfg.is_loader:
                loader_pairs.append(pair)

        block_roles[block] = tuple(roles_for_block)
        terminal_for_block = tuple(
            role for role in system_terminal_roles.get(system_id, ()) if role in roles_for_block
        )
        block_terminal_roles[block] = terminal_for_block
        terminal_pairs.extend((role, block) for role in terminal_for_block)

    window_lookup = bundle.windows

    def _within_window(block_id: str, day: int) -> bool:
        earliest, latest = window_lookup[block_id]
        return earliest <= day <= latest

    blackout_slots = frozenset(bundle.blackout_slots)

    def _is_available(machine_id: str, day: int, shift_id: str) -> bool:
        # A_{m,s}: calendars, and 0 in timeline blackout slots (same slots the heuristics skip).
        return machine_slot_available(bundle, machine_id, day, shift_id, blackout_slots)

    # Locks are resolved first: the activation coupling needs to know which machines are locked.
    lock_slot_targets, lock_warnings = resolve_locked_slots(bundle)
    locked_on_block: set[tuple[str, str, tuple[int, str]]] = {
        (mach, blk, slot) for (mach, slot), blk in lock_slot_targets.items() if blk is not None
    }

    model.x = pyo.Var(model.M, model.B, model.S, domain=pyo.Binary, initialize=0)
    model.prod = pyo.Var(model.M, model.B, model.S, domain=pyo.NonNegativeReals, initialize=0)

    # Machine capacity & compatibility
    def machine_capacity_rule(mdl, mach, day, shift_id):
        if not _is_available(mach, day, shift_id):
            return sum(mdl.x[mach, blk, (day, shift_id)] for blk in mdl.B) == 0
        return sum(mdl.x[mach, blk, (day, shift_id)] for blk in mdl.B) <= 1

    model.machine_capacity = pyo.Constraint(model.M, model.S, rule=machine_capacity_rule)

    def role_compatibility_rule(mdl, mach, blk, day, shift_id):
        if blk in unsequenced:
            return pyo.Constraint.Skip
        role = machine_roles.get(mach)
        if role and role in block_roles.get(blk, ()):  # allowed
            return pyo.Constraint.Skip
        # machine not compatible with block/system role
        return mdl.x[mach, blk, (day, shift_id)] == 0

    model.role_compatibility = pyo.Constraint(
        model.M, model.B, model.S, rule=role_compatibility_rule
    )

    # Production capacity per assignment
    def prod_cap_rule(mdl, mach, blk, day, shift_id):
        rate = bundle.production_rates.get((mach, blk), 0.0)
        return mdl.prod[mach, blk, (day, shift_id)] <= rate * mdl.x[mach, blk, (day, shift_id)]

    model.production_cap = pyo.Constraint(model.M, model.B, model.S, rule=prod_cap_rule)

    # Window feasibility
    def window_rule(mdl, mach, blk, day, shift_id):
        if _within_window(blk, day):
            return pyo.Constraint.Skip
        return mdl.x[mach, blk, (day, shift_id)] == 0

    model.block_windows = pyo.Constraint(model.M, model.B, model.S, rule=window_rule)

    # Role-level production aggregation
    model.RB = pyo.Set(initialize=role_block_pairs, dimen=2)
    model.role_prod = pyo.Var(model.RB, model.S, domain=pyo.NonNegativeReals)

    def role_prod_balance_rule(mdl, role, blk, day, shift_id):
        machines_for_role = role_to_machines.get(role, [])
        if not machines_for_role:
            return mdl.role_prod[role, blk, (day, shift_id)] == 0
        return mdl.role_prod[role, blk, (day, shift_id)] == sum(
            mdl.prod[mach, blk, (day, shift_id)] for mach in machines_for_role
        )

    model.role_prod_balance = pyo.Constraint(model.RB, model.S, rule=role_prod_balance_rule)

    def _mobil_cost(mach: str, prev_blk: str, curr_blk: str) -> float:
        if prev_blk == curr_blk:
            return 0.0
        params = mobilisation_params.get(mach)
        if not params:
            return 0.0
        distance = mobilisation_distances.get((prev_blk, curr_blk), 0.0)
        cost = params["setup_cost"]
        if distance <= params["walk_threshold_m"]:
            cost += params["walk_cost_per_meter"] * distance
        else:
            cost += params["move_cost_flat"]
        return cost

    # Transition tracking for mobilisation penalties
    transition_slots = [slot for slot in model.S if prev_shift_map.get(slot) is not None]
    needs_transitions = bool(transition_slots)
    mobilisation_expr = None
    transition_expr = None
    if needs_transitions:
        model.S_transition = pyo.Set(initialize=transition_slots, dimen=2)
        model.y = pyo.Var(model.M, model.B, model.B, model.S_transition, domain=pyo.Binary)

        def _prev_match_rule(mdl, mach, prev_blk, curr_blk, day, shift_id):
            prev_index = prev_shift_map[(day, shift_id)]
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
            prev_index = prev_shift_map[(day, shift_id)]
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

        mobilisation_expr = sum(
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

    # Initial staged inventory of each upstream role at the first slot (E7): the carried-in
    # output of u not yet consumed downstream (0.0 without an initial state, as in v1.0.0).
    initial_staged = bundle.initial_staged_inventory
    initial_inventory_start: dict[tuple[str, str], float] = {
        (up_role, blk): float(initial_staged.get((blk, up_role), 0.0))
        for up_role, blk in stage_pairs
    }

    # Inventory tracking per upstream role (E7)
    model.InventoryPairs = pyo.Set(initialize=stage_pairs, dimen=2)
    model.inventory_start = pyo.Var(model.InventoryPairs, model.S, domain=pyo.NonNegativeReals)
    model.inventory = pyo.Var(model.InventoryPairs, model.S, domain=pyo.NonNegativeReals)

    def inventory_start_rule(mdl, up_role, blk, day, shift_id):
        slot = (day, shift_id)
        prev_slot = prev_shift_map[slot]
        if prev_slot is None:
            return (
                mdl.inventory_start[up_role, blk, slot] == initial_inventory_start[(up_role, blk)]
            )
        return mdl.inventory_start[up_role, blk, slot] == mdl.inventory[up_role, blk, prev_slot]

    def inventory_balance_rule(mdl, up_role, blk, day, shift_id):
        slot = (day, shift_id)
        consumed = sum(
            mdl.role_prod[down_role, blk, slot] for down_role in stage_downstream[(up_role, blk)]
        )
        return (
            mdl.inventory[up_role, blk, slot]
            == mdl.inventory_start[up_role, blk, slot]
            + mdl.role_prod[up_role, blk, slot]
            - consumed
        )

    def _prev_inventory(mdl, up_role: str, blk: str, slot: tuple[int, str]):
        prev_slot = prev_shift_map[slot]
        if prev_slot is None:
            return initial_inventory_start[(up_role, blk)]
        return mdl.inventory[up_role, blk, prev_slot]

    if stage_pairs:
        model.inventory_start_eq = pyo.Constraint(
            model.InventoryPairs, model.S, rule=inventory_start_rule
        )
        model.inventory_balance = pyo.Constraint(
            model.InventoryPairs, model.S, rule=inventory_balance_rule
        )

        def downstream_inventory_guard_rule(mdl, up_role, blk, day, shift_id):
            slot = (day, shift_id)
            return (
                sum(
                    mdl.role_prod[down_role, blk, slot]
                    for down_role in stage_downstream[(up_role, blk)]
                )
                <= mdl.inventory_start[up_role, blk, slot]
            )

        model.inventory_guard = pyo.Constraint(
            model.InventoryPairs, model.S, rule=downstream_inventory_guard_rule
        )

    # Delivered terminal output D_b(s) is needed by the dynamic loader threshold and by the
    # per-slot remaining caps; both are only built where they can bind.
    def _system_is_in_forest(system_id: str) -> bool:
        downstream = system_downstream.get(system_id, {})
        return len(system_terminal_roles.get(system_id, ())) == 1 and all(
            len(children) <= 1 for children in downstream.values()
        )

    def _path_to_terminal(system_id: str, role: str) -> list[str]:
        downstream = system_downstream.get(system_id, {})
        path: list[str] = []
        current = role
        seen: set[str] = set()
        while current not in seen and downstream.get(current):
            seen.add(current)
            path.append(current)
            current = next(iter(downstream[current]))
        return path  # roles from `role` up to (excluding) the terminal role

    slot_cap_pairs: list[tuple[str, str]] = []
    for role, blk in role_block_pairs:
        if role in block_terminal_roles.get(blk, ()) or not role_to_machines.get(role):
            continue
        system_id = block_system[blk]
        if _system_is_in_forest(system_id):
            staged_downstream = sum(
                initial_staged.get((blk, path_role), 0.0)
                for path_role in _path_to_terminal(system_id, role)
            )
            work = bundle.work_required[blk]
            if _role_remaining(role, blk) + staged_downstream <= work + _REDUNDANCY_TOLERANCE * max(
                1.0, work
            ):
                continue  # implied by the inventory balances and role_remaining_cap
        slot_cap_pairs.append((role, blk))

    loader_tail_blocks = sorted({blk for _, blk in loader_gate_pairs})
    delivery_blocks = sorted(
        {blk for _, blk in slot_cap_pairs} | set(loader_tail_blocks),
        key=blocks.index,
    )
    delivery_terminal_pairs = {
        (role, blk) for blk in delivery_blocks for role in block_terminal_roles.get(blk, ())
    }

    # Head-start waiver (only for roles with role_headstart_shifts > 0): upstream_done[r,b,s] = 1
    # only if every upstream role of r has output its whole carried-in remaining volume before
    # slot s; the buffer is then waived (the pipeline is draining and the buffer can no longer
    # grow).
    if headstart_pairs:
        model.HeadstartPairs = pyo.Set(initialize=headstart_pairs, dimen=2)
        model.upstream_done = pyo.Var(model.HeadstartPairs, model.S, domain=pyo.Binary)
    cumulative_pairs = sorted(
        {(up_role, blk) for role, blk in headstart_pairs for up_role in role_upstream[(role, blk)]}
        | delivery_terminal_pairs
    )
    if cumulative_pairs:
        model.CumulativePairs = pyo.Set(initialize=cumulative_pairs, dimen=2)
        model.role_cumulative = pyo.Var(model.CumulativePairs, model.S, domain=pyo.NonNegativeReals)

        def role_cumulative_rule(mdl, role, blk, day, shift_id):
            slot = (day, shift_id)
            prev_slot = prev_shift_map[slot]
            previous = mdl.role_cumulative[role, blk, prev_slot] if prev_slot else 0.0
            return mdl.role_cumulative[role, blk, slot] == previous + mdl.role_prod[role, blk, slot]

        model.role_cumulative_eq = pyo.Constraint(
            model.CumulativePairs, model.S, rule=role_cumulative_rule
        )

    def _delivered_through(mdl, blk: str, slot: tuple[int, str] | None):
        """Terminal output delivered on ``blk`` up to and including ``slot`` (0 before s1)."""

        if slot is None:
            return 0.0
        return sum(
            mdl.role_cumulative[role, blk, slot] for role in block_terminal_roles.get(blk, ())
        )

    if headstart_pairs:
        model.UpstreamDoneIndex = pyo.Set(
            initialize=[
                (role, blk, up_role, day, shift_id)
                for role, blk in headstart_pairs
                for up_role in role_upstream[(role, blk)]
                for day, shift_id in shift_list
            ],
            dimen=5,
        )

        def upstream_done_rule(mdl, role, blk, up_role, day, shift_id):
            slot = (day, shift_id)
            prev_slot = prev_shift_map[slot]
            produced = mdl.role_cumulative[up_role, blk, prev_slot] if prev_slot else 0.0
            return (
                produced >= _role_remaining_raw(up_role, blk) * mdl.upstream_done[role, blk, slot]
            )

        model.upstream_done_link = pyo.Constraint(model.UpstreamDoneIndex, rule=upstream_done_rule)

    # Activation binaries gate production of buffered roles and loaders (E8).
    if activation_pairs:
        model.ActivationPairs = pyo.Set(initialize=activation_pairs, dimen=2)
        model.role_active = pyo.Var(model.ActivationPairs, model.S, domain=pyo.Binary)

        def activation_prod_rule(mdl, role, blk, day, shift_id):
            cap = role_capacity[(role, blk)]
            return (
                mdl.role_prod[role, blk, (day, shift_id)]
                <= cap * mdl.role_active[role, blk, (day, shift_id)]
            )

        def head_start_rule(mdl, role, blk, up_role, day, shift_id):
            slot = (day, shift_id)
            buffer_volume = role_buffer_volume[(role, blk)]
            return _prev_inventory(mdl, up_role, blk, slot) >= buffer_volume * (
                mdl.role_active[role, blk, slot] - mdl.upstream_done[role, blk, slot]
            )

        model.activation_prod = pyo.Constraint(
            model.ActivationPairs, model.S, rule=activation_prod_rule
        )
        if headstart_pairs:
            model.HeadStartIndex = pyo.Set(
                initialize=[
                    (role, blk, up_role, day, shift_id)
                    for role, blk in headstart_pairs
                    for up_role in role_upstream[(role, blk)]
                    for day, shift_id in shift_list
                ],
                dimen=5,
            )
            model.head_start = pyo.Constraint(model.HeadStartIndex, rule=head_start_rule)

        def activation_assignment_upper_rule(mdl, role, blk, day, shift_id):
            slot = (day, shift_id)
            machines_for_role = role_to_machines.get(role, [])
            if not machines_for_role:
                return mdl.role_active[role, blk, slot] == 0
            # Locked machines may sit idle (x = 1, no production) without activating the role.
            unlocked = [
                mach for mach in machines_for_role if (mach, blk, slot) not in locked_on_block
            ]
            if not unlocked:
                return pyo.Constraint.Skip
            return (
                sum(mdl.x[mach, blk, slot] for mach in unlocked)
                <= len(unlocked) * mdl.role_active[role, blk, slot]
            )

        def activation_assignment_lower_rule(mdl, role, blk, day, shift_id):
            machines_for_role = role_to_machines.get(role, [])
            if not machines_for_role:
                return mdl.role_active[role, blk, (day, shift_id)] == 0
            return mdl.role_active[role, blk, (day, shift_id)] <= sum(
                mdl.x[mach, blk, (day, shift_id)] for mach in machines_for_role
            )

        model.role_active_upper = pyo.Constraint(
            model.ActivationPairs, model.S, rule=activation_assignment_upper_rule
        )
        model.role_active_lower = pyo.Constraint(
            model.ActivationPairs, model.S, rule=activation_assignment_lower_rule
        )

    # Loader batching constraints
    model.LoaderPairs = pyo.Set(initialize=loader_pairs, dimen=2)
    if loader_pairs:
        model.loads = pyo.Var(model.LoaderPairs, model.S, domain=pyo.NonNegativeIntegers)
        model.loader_partial = pyo.Var(model.LoaderPairs, model.S, domain=pyo.NonNegativeReals)

        def loader_batch_rule(mdl, role, blk, day, shift_id):
            batch = loader_batch_volume[(role, blk)]
            return mdl.role_prod[role, blk, (day, shift_id)] == (
                batch * mdl.loads[role, blk, (day, shift_id)]
                + mdl.loader_partial[role, blk, (day, shift_id)]
            )

        def loader_partial_cap_rule(mdl, role, blk, day, shift_id):
            batch = loader_batch_volume[(role, blk)]
            return mdl.loader_partial[role, blk, (day, shift_id)] <= batch

        model.loader_batch = pyo.Constraint(model.LoaderPairs, model.S, rule=loader_batch_rule)
        model.loader_partial_cap = pyo.Constraint(
            model.LoaderPairs, model.S, rule=loader_partial_cap_rule
        )

    # Dynamic loader threshold (E8): a producing loader needs min(q, W_b - D_b(<s)) staged by
    # every upstream role at the start of the slot.
    loader_slot_mode: dict[tuple[str, tuple[int, str]], str] = {}
    loader_tail_index: list[tuple[str, int, str]] = []
    loader_block_batch: dict[str, float] = {}
    for blk in loader_tail_blocks:
        system_cfg = system_configs[block_system[blk]]
        batch = system_cfg.loader_batch_volume_m3
        loader_block_batch[blk] = batch
        work = bundle.work_required[blk]
        if work <= batch:
            for slot in shift_list:
                loader_slot_mode[(blk, slot)] = "remaining"
            continue
        # Upper bound on terminal deliveries before each slot (terminal fleet capacity in open
        # slots); the remaining volume can only fall to a truckload once this bound exceeds W - q.
        delivered_bound = 0.0
        for slot in shift_list:
            if delivered_bound > work - batch + 1e-9:
                loader_slot_mode[(blk, slot)] = "tail"
                loader_tail_index.append((blk, slot[0], slot[1]))
            else:
                loader_slot_mode[(blk, slot)] = "batch"
            if _within_window(blk, slot[0]):
                for role in block_terminal_roles.get(blk, ()):
                    for mach in role_to_machines.get(role, []):
                        if _is_available(mach, slot[0], slot[1]):
                            delivered_bound += bundle.production_rates.get((mach, blk), 0.0)
            delivered_bound = min(delivered_bound, work)

    if loader_gate_pairs:
        if loader_tail_index:
            model.LoaderTailIndex = pyo.Set(initialize=loader_tail_index, dimen=3)
            model.loader_tail = pyo.Var(model.LoaderTailIndex, domain=pyo.Binary)
            tail_set = frozenset(loader_tail_index)

            def loader_tail_reached_rule(mdl, blk, day, shift_id):
                # loader_tail = 1 only once the remaining volume is at most one truckload.
                slot = (day, shift_id)
                work = bundle.work_required[blk]
                batch = loader_block_batch[blk]
                return (
                    _delivered_through(mdl, blk, prev_shift_map[slot])
                    >= (work - batch) * mdl.loader_tail[blk, day, shift_id]
                )

            def loader_tail_monotone_rule(mdl, blk, day, shift_id):
                prev_slot = prev_shift_map[(day, shift_id)]
                if prev_slot is None or (blk, prev_slot[0], prev_slot[1]) not in tail_set:
                    return pyo.Constraint.Skip
                return (
                    mdl.loader_tail[blk, day, shift_id]
                    >= mdl.loader_tail[blk, prev_slot[0], prev_slot[1]]
                )

            model.loader_tail_reached = pyo.Constraint(
                model.LoaderTailIndex, rule=loader_tail_reached_rule
            )
            model.loader_tail_monotone = pyo.Constraint(
                model.LoaderTailIndex, rule=loader_tail_monotone_rule
            )

        threshold_index = [
            (role, blk, up_role, day, shift_id)
            for role, blk in loader_gate_pairs
            for up_role in role_upstream[(role, blk)]
            for day, shift_id in shift_list
        ]
        model.LoaderThresholdIndex = pyo.Set(initialize=threshold_index, dimen=5)

        def loader_threshold_rule(mdl, role, blk, up_role, day, shift_id):
            slot = (day, shift_id)
            staged = _prev_inventory(mdl, up_role, blk, slot)
            active = mdl.role_active[role, blk, slot]
            batch = loader_block_batch[blk]
            work = bundle.work_required[blk]
            mode = loader_slot_mode[(blk, slot)]
            if mode == "batch":
                return staged >= batch * active
            delivered = _delivered_through(mdl, blk, prev_shift_map[slot])
            if mode == "remaining":
                # min(q, W - D) = W - D: staged >= (W - D)·g, exact because W - D <= W.
                return staged + delivered >= work * active
            # Tail slot, remaining volume above a truckload: staged >= q·g.
            return staged >= batch * (active - mdl.loader_tail[blk, day, shift_id])

        def loader_threshold_tail_rule(mdl, role, blk, up_role, day, shift_id):
            slot = (day, shift_id)
            if loader_slot_mode[(blk, slot)] != "tail":
                return pyo.Constraint.Skip
            staged = _prev_inventory(mdl, up_role, blk, slot)
            delivered = _delivered_through(mdl, blk, prev_shift_map[slot])
            batch = loader_block_batch[blk]
            work = bundle.work_required[blk]
            # Tail reached: staged >= W - D when producing (vacuous otherwise).
            return (
                staged + delivered
                >= batch * mdl.role_active[role, blk, slot]
                + (work - batch) * mdl.loader_tail[blk, day, shift_id]
            )

        model.loader_threshold = pyo.Constraint(
            model.LoaderThresholdIndex, rule=loader_threshold_rule
        )
        if loader_tail_index:
            model.loader_threshold_tail = pyo.Constraint(
                model.LoaderThresholdIndex, rule=loader_threshold_tail_rule
            )

    # Block balance ensures required work is met (with leftover slack)
    model.leftover = pyo.Var(model.B, domain=pyo.NonNegativeReals)

    def block_balance_rule(mdl, blk):
        terminal_roles = block_terminal_roles.get(blk, ())
        if terminal_roles:
            total_prod = sum(
                mdl.role_prod[role, blk, slot] for role in terminal_roles for slot in model.S
            )
        else:
            total_prod = sum(mdl.prod[mach, blk, slot] for mach in mdl.M for slot in model.S)
        return total_prod + mdl.leftover[blk] == bundle.work_required[blk]

    model.block_balance = pyo.Constraint(model.B, rule=block_balance_rule)

    # Per-role output cap: Σ_s z[r,b,s] <= R_{r,b} = min(carried-in role_remaining, W_b).
    role_remaining_pairs = list(role_block_pairs)
    if role_remaining_pairs:
        model.RoleRemainingPairs = pyo.Set(initialize=role_remaining_pairs, dimen=2)

        def role_remaining_rule(mdl, role, blk):
            return sum(mdl.role_prod[role, blk, slot] for slot in mdl.S) <= _role_remaining(
                role, blk
            )

        model.role_remaining_cap = pyo.Constraint(
            model.RoleRemainingPairs, rule=role_remaining_rule
        )

    # Per-slot remaining cap for non-terminal roles where the flow balances do not imply it.
    if slot_cap_pairs:
        model.SlotCapPairs = pyo.Set(initialize=slot_cap_pairs, dimen=2)

        def role_slot_remaining_rule(mdl, role, blk, day, shift_id):
            slot = (day, shift_id)
            return (
                mdl.role_prod[role, blk, slot] + _delivered_through(mdl, blk, slot)
                <= bundle.work_required[blk]
            )

        model.role_slot_remaining = pyo.Constraint(
            model.SlotCapPairs, model.S, rule=role_slot_remaining_rule
        )

    # Scenario locks (resolved by resolve_locked_slots): a day-level lock pins every available
    # shift of that day to the block (other blocks to 0); a shift-level lock pins only its slot.
    # Expressed as equality constraints rather than fixed variables so warm starts cannot
    # overwrite them.
    lock_targets: dict[tuple[str, str, tuple[int, str]], int] = {}
    for (lock_machine, slot), target_block in lock_slot_targets.items():
        for blk in blocks:
            lock_targets[(lock_machine, blk, slot)] = 1 if blk == target_block else 0
    if lock_targets:
        model.LockedSlots = pyo.Set(
            initialize=[(mach, blk, slot[0], slot[1]) for mach, blk, slot in lock_targets],
            dimen=4,
        )

        def locked_assignment_rule(mdl, mach, blk, day, shift_id):
            return mdl.x[mach, blk, (day, shift_id)] == lock_targets[(mach, blk, (day, shift_id))]

        model.locked_assignment = pyo.Constraint(model.LockedSlots, rule=locked_assignment_rule)

    # Landing capacity with slack
    landing_ids = sorted(
        {
            landing
            for landing in bundle.landing_for_block.values()
            if landing in bundle.landing_capacity
        }
    )
    if landing_ids:
        model.Landing = pyo.Set(initialize=landing_ids)
        model.landing_surplus = pyo.Var(model.Landing, model.D, domain=pyo.NonNegativeReals)

        def landing_capacity_rule(mdl, landing_id, day):
            capacity = bundle.landing_capacity.get(landing_id)
            if capacity is None:
                return pyo.Constraint.Skip
            related_blocks = [
                blk for blk, landing in bundle.landing_for_block.items() if landing == landing_id
            ]
            if not related_blocks:
                return pyo.Constraint.Skip
            expr = 0
            for blk in related_blocks:
                for mach in mdl.M:
                    for shift_day, shift_label in model.S:
                        if shift_day == day:
                            expr += mdl.x[mach, blk, (shift_day, shift_label)]
            return expr <= capacity + mdl.landing_surplus[landing_id, day]

        model.landing_capacity = pyo.Constraint(model.Landing, model.D, rule=landing_capacity_rule)

    prod_weight = bundle.objective_weights.production
    landing_weight = bundle.objective_weights.landing_surplus
    mobilisation_weight = bundle.objective_weights.mobilisation
    transition_weight = bundle.objective_weights.transitions
    leftover_penalty = prod_weight

    if terminal_pairs:
        obj_expr = prod_weight * sum(
            model.role_prod[role, blk, slot] for role, blk in terminal_pairs for slot in model.S
        )
        if unsequenced:
            obj_expr += prod_weight * sum(
                model.prod[mach, blk, slot]
                for mach in model.M
                for blk in model.B
                if blk in unsequenced
                for slot in model.S
            )
    else:
        obj_expr = prod_weight * sum(
            model.prod[mach, blk, slot] for mach in model.M for blk in model.B for slot in model.S
        )
    if leftover_penalty:
        obj_expr -= leftover_penalty * sum(model.leftover[blk] for blk in model.B)
    if landing_weight:
        obj_expr -= landing_weight * sum(
            model.landing_surplus[landing_id, day]
            for landing_id in model.Landing
            for day in model.D
        )
    if mobilisation_expr is not None and mobilisation_weight:
        obj_expr -= mobilisation_weight * mobilisation_expr
    if transition_expr is not None and transition_weight:
        obj_expr -= transition_weight * transition_expr

    # Boundary transition from each machine's carried-in block into the first slot (E6). Only
    # added when the initial state names a last block, so default models are unchanged.
    boundary_mobilisation: dict[tuple[str, str], float] = {}
    boundary_transitions: list[tuple[str, str]] = []
    if bundle.initial_machine_block and shift_list:
        for mach, prev_blk in bundle.initial_machine_block.items():
            if mach not in machines or prev_blk not in blocks:
                continue
            for blk in blocks:
                if blk == prev_blk:
                    continue
                boundary_transitions.append((mach, blk))
                cost = _mobil_cost(mach, prev_blk, blk)
                if cost:
                    boundary_mobilisation[(mach, blk)] = cost
    if boundary_transitions:
        first_slot = shift_list[0]
        if mobilisation_weight and boundary_mobilisation:
            obj_expr -= mobilisation_weight * sum(
                cost * model.x[mach, blk, first_slot]
                for (mach, blk), cost in boundary_mobilisation.items()
            )
        if transition_weight:
            obj_expr -= transition_weight * sum(
                model.x[mach, blk, first_slot] for mach, blk in boundary_transitions
            )

    model.objective = pyo.Objective(expr=obj_expr, sense=pyo.maximize)

    # Attach warm-start metadata so the driver can rebuild incumbent states.
    model._warm_start_meta = {
        "bundle": bundle,
        "shift_list": tuple(shift_list),
        "prev_shift_map": prev_shift_map,
        "role_upstream": role_upstream,
        "role_to_machines": {role: tuple(machines) for role, machines in role_to_machines.items()},
        "block_terminal_roles": block_terminal_roles,
        "loader_batch_volume": loader_batch_volume,
        "inventory_pairs": tuple(stage_pairs),
        "stage_downstream": {pair: tuple(roles) for pair, roles in stage_downstream.items()},
        "activation_pairs": tuple(activation_pairs),
        "loader_pairs": tuple(loader_pairs),
        "terminal_pairs": tuple(terminal_pairs),
        "needs_transitions": needs_transitions,
        "initial_inventory_start": dict(initial_inventory_start),
        "boundary_mobilisation": dict(boundary_mobilisation),
        "boundary_transitions": tuple(boundary_transitions),
        "locked_on_block": frozenset(locked_on_block),
        "lock_slot_targets": dict(lock_slot_targets),
        "loader_block_batch": dict(loader_block_batch),
        "warnings": list(lock_warnings),
    }

    return model
