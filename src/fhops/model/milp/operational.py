"""Operational MILP builder (day × shift grid)."""

from __future__ import annotations

from collections import defaultdict

import pyomo.environ as pyo

from fhops.model.milp.data import OperationalMilpBundle, headstart_buffer_volumes

__all__ = ["build_operational_model"]


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
        :func:`fhops.model.milp.driver.solve_operational_milp` to seed incumbents.

    Notes
    -----
    Sequencing rules shared with the playback tracker and the heuristics (#109; see
    ``docs/howto/system_sequencing.rst``):

    * ``role_remaining_cap`` limits every role's total output on a block to ``R_{r,b}`` (carried-in
      ``role_remaining`` or ``work_required``), so upstream roles cannot handle more wood than the
      block holds.
    * ``head_start`` requires the staged volume at the end of the previous slot to cover the buffer
      ``B_{r,b}`` (:func:`fhops.model.milp.data.headstart_buffer_volumes`) whenever the role works;
      for loaders the buffer is at least ``min(loader_batch_volume_m3, R_{r,b})``. For roles with a
      head start, ``upstream_done_link`` waives the buffer once every upstream role has output its
      whole remaining volume (binary ``upstream_done``, cumulative output ``role_cumulative``).
    * Blocks listed in ``bundle.unsequenced_blocks`` (no ``harvest_system_id``) have no role
      constraints; all machine production counts towards their balance and the objective.

    Availability ``A_{m,s}`` combines the day/shift calendars with ``bundle.blackout_slots``
    (timeline blackouts, #110): ``machine_capacity`` forces ``Σ_b x[m,b,s] = 0`` in unavailable
    slots.

    Initial state and locks (no-ops for default bundles):

    * ``bundle.initial_staged_inventory`` sets the first-slot ``inventory_start`` of each
      downstream role to the minimum staged volume over its upstream roles; the head-start
      comparison at the first slot uses the same value instead of zero.
    * ``bundle.initial_role_remaining`` sets ``R_{r,b}`` in ``role_remaining_cap``: total role
      output over the horizon cannot exceed the carried-in remaining volume.
    * ``bundle.initial_machine_block`` adds a linear boundary term on the first slot:
      ``-(ω_mob·δ(m,b0,b) + ω_trans)·x[m,b,first]`` for ``b ≠ b0``.
    * ``bundle.locked_assignments`` adds ``locked_assignment`` equality constraints: a day lock
      pins every available shift of the day to its block (other blocks 0); a shift lock pins only
      its slot. Unavailable locked slots are pinned to 0.
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
    inventory_pairs: list[tuple[str, str]] = []
    activation_pairs: list[tuple[str, str]] = []
    loader_pairs: list[tuple[str, str]] = []
    role_upstream: dict[tuple[str, str], tuple[str, ...]] = {}
    role_buffer_volume: dict[tuple[str, str], float] = {}
    role_capacity: dict[tuple[str, str], float] = {}
    loader_batch_volume: dict[tuple[str, str], float] = {}
    block_terminal_roles: dict[str, tuple[str, ...]] = {}
    terminal_pairs: list[tuple[str, str]] = []
    mobilisation_params = bundle.mobilisation_params
    mobilisation_distances = bundle.mobilisation_distances

    headstart_volumes = headstart_buffer_volumes(bundle)
    headstart_pairs: list[tuple[str, str]] = []

    # Remaining output each role may still produce on a block (R_{r,b}): the carried-in
    # ``role_remaining`` when supplied, otherwise W_b. Every role handles the same wood, so no role
    # can output more than the block holds.
    def _role_remaining(role: str, blk: str) -> float:
        return bundle.initial_role_remaining.get((blk, role), bundle.work_required[blk])

    system_terminal_roles: dict[str, tuple[str, ...]] = {}
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
            if role_cfg.is_loader and role_cfg.upstream_roles:
                # One truckload staged, or the whole remaining block volume when it is smaller.
                truckload = min(
                    system_cfg.loader_batch_volume_m3, _role_remaining(role_name, block)
                )
                buffer_volume = max(buffer_volume, truckload)
            role_buffer_volume[pair] = buffer_volume

            if role_cfg.upstream_roles:
                inventory_pairs.append(pair)
                if buffer_volume > 0:
                    activation_pairs.append(pair)
            if role_cfg.is_loader:
                loader_pairs.append(pair)
                loader_batch_volume[pair] = system_cfg.loader_batch_volume_m3
            else:
                loader_batch_volume[pair] = system_cfg.loader_batch_volume_m3

        block_roles[block] = tuple(roles_for_block)
        terminal_for_block = tuple(
            role for role in system_terminal_roles.get(system_id, ()) if role in roles_for_block
        )
        block_terminal_roles[block] = terminal_for_block
        terminal_pairs.extend((role, block) for role in terminal_for_block)

    window_lookup = bundle.windows
    availability_day = bundle.availability_day
    availability_shift = bundle.availability_shift

    def _within_window(block_id: str, day: int) -> bool:
        earliest, latest = window_lookup[block_id]
        return earliest <= day <= latest

    blackout_slots = frozenset(bundle.blackout_slots)

    def _is_available(machine_id: str, day: int, shift_id: str) -> bool:
        # A_{m,s}: calendars, and 0 in timeline blackout slots (same slots the heuristics skip).
        if (machine_id, day, shift_id) in blackout_slots:
            return False
        if (machine_id, day, shift_id) in availability_shift:
            return availability_shift[(machine_id, day, shift_id)] == 1
        return availability_day.get((machine_id, day), 1) == 1

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

    # Initial staged inventory available to each downstream role at the first slot (E7). A role
    # with several upstream roles can only consume what every upstream role has staged, so the
    # start value is the minimum over upstream roles (matching the sequencing tracker). Without an
    # initial state every value is 0.0, which reproduces the v1.0.0 equations.
    initial_staged = bundle.initial_staged_inventory
    initial_inventory_start: dict[tuple[str, str], float] = {}
    for role, blk in inventory_pairs:
        upstream_roles = role_upstream[(role, blk)]
        initial_inventory_start[(role, blk)] = (
            min(initial_staged.get((blk, up_role), 0.0) for up_role in upstream_roles)
            if initial_staged
            else 0.0
        )

    # Inventory tracking (only for roles with upstream requirements)
    model.InventoryPairs = pyo.Set(initialize=inventory_pairs, dimen=2)
    model.inventory_start = pyo.Var(model.InventoryPairs, model.S, domain=pyo.NonNegativeReals)
    model.inventory = pyo.Var(model.InventoryPairs, model.S, domain=pyo.NonNegativeReals)

    def inventory_start_rule(mdl, role, blk, day, shift_id):
        slot = (day, shift_id)
        prev_slot = prev_shift_map[slot]
        if prev_slot is None:
            return mdl.inventory_start[role, blk, slot] == initial_inventory_start[(role, blk)]
        return mdl.inventory_start[role, blk, slot] == mdl.inventory[role, blk, prev_slot]

    def inventory_balance_rule(mdl, role, blk, day, shift_id):
        slot = (day, shift_id)
        upstream_roles = role_upstream[(role, blk)]
        upstream_sum = sum(mdl.role_prod[up_role, blk, slot] for up_role in upstream_roles)
        return (
            mdl.inventory[role, blk, slot]
            == mdl.inventory_start[role, blk, slot] + upstream_sum - mdl.role_prod[role, blk, slot]
        )

    if inventory_pairs:
        model.inventory_start_eq = pyo.Constraint(
            model.InventoryPairs, model.S, rule=inventory_start_rule
        )
        model.inventory_balance = pyo.Constraint(
            model.InventoryPairs, model.S, rule=inventory_balance_rule
        )

        def downstream_inventory_guard_rule(mdl, role, blk, day, shift_id):
            return (
                mdl.role_prod[role, blk, (day, shift_id)]
                <= mdl.inventory_start[role, blk, (day, shift_id)]
            )

        model.inventory_guard = pyo.Constraint(
            model.InventoryPairs, model.S, rule=downstream_inventory_guard_rule
        )

    # Head-start waiver (only for roles with role_headstart_shifts > 0): upstream_done[r,b,s] = 1
    # only if every upstream role of r has output its whole remaining volume R_{u,b} before slot s;
    # the buffer is then waived (the pipeline is draining and the buffer can no longer grow).
    if headstart_pairs:
        model.HeadstartPairs = pyo.Set(initialize=headstart_pairs, dimen=2)
        model.upstream_done = pyo.Var(model.HeadstartPairs, model.S, domain=pyo.Binary)
        cumulative_pairs = sorted(
            {
                (up_role, blk)
                for role, blk in headstart_pairs
                for up_role in role_upstream[(role, blk)]
            }
        )
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
            return produced >= _role_remaining(up_role, blk) * mdl.upstream_done[role, blk, slot]

        model.upstream_done_link = pyo.Constraint(model.UpstreamDoneIndex, rule=upstream_done_rule)

    headstart_set = frozenset(headstart_pairs)

    # Head-start buffers via activation binaries (only when buffer > 0)
    if activation_pairs:
        model.ActivationPairs = pyo.Set(initialize=activation_pairs, dimen=2)
        model.role_active = pyo.Var(model.ActivationPairs, model.S, domain=pyo.Binary)

        def activation_prod_rule(mdl, role, blk, day, shift_id):
            cap = role_capacity[(role, blk)]
            return (
                mdl.role_prod[role, blk, (day, shift_id)]
                <= cap * mdl.role_active[role, blk, (day, shift_id)]
            )

        def head_start_rule(mdl, role, blk, day, shift_id):
            slot = (day, shift_id)
            prev_slot = prev_shift_map[slot]
            prev_inventory = (
                mdl.inventory[role, blk, prev_slot]
                if prev_slot
                else initial_inventory_start[(role, blk)]
            )
            buffer_volume = role_buffer_volume[(role, blk)]
            if buffer_volume <= 0:
                return pyo.Constraint.Skip
            if (role, blk) in headstart_set:
                return prev_inventory >= buffer_volume * (
                    mdl.role_active[role, blk, slot] - mdl.upstream_done[role, blk, slot]
                )
            return prev_inventory >= buffer_volume * mdl.role_active[role, blk, slot]

        model.activation_prod = pyo.Constraint(
            model.ActivationPairs, model.S, rule=activation_prod_rule
        )
        model.head_start = pyo.Constraint(model.ActivationPairs, model.S, rule=head_start_rule)

        def activation_assignment_upper_rule(mdl, role, blk, day, shift_id):
            machines_for_role = role_to_machines.get(role, [])
            if not machines_for_role:
                return mdl.role_active[role, blk, (day, shift_id)] == 0
            return (
                sum(mdl.x[mach, blk, (day, shift_id)] for mach in machines_for_role)
                <= len(machines_for_role) * mdl.role_active[role, blk, (day, shift_id)]
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

    # Per-role output cap: Σ_s z[r,b,s] <= R_{r,b} (carried-in role_remaining, otherwise W_b).
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

    # Scenario locks: a day-level lock pins every available shift of that day to the block (other
    # blocks to 0); a shift-level lock pins only its slot. Expressed as equality constraints rather
    # than fixed variables so warm starts cannot overwrite them.
    lock_targets: dict[tuple[str, str, tuple[int, str]], int] = {}
    for lock_machine, lock_block, lock_day, lock_shift in bundle.locked_assignments:
        if lock_machine not in machines or lock_block not in blocks:
            continue
        for slot in shift_list:
            slot_day, slot_shift = slot
            if slot_day != lock_day or (lock_shift is not None and slot_shift != lock_shift):
                continue
            available = _is_available(lock_machine, slot_day, slot_shift)
            for blk in blocks:
                target = 1 if (blk == lock_block and available) else 0
                lock_targets[(lock_machine, blk, slot)] = target
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
        "inventory_pairs": tuple(inventory_pairs),
        "activation_pairs": tuple(activation_pairs),
        "loader_pairs": tuple(loader_pairs),
        "terminal_pairs": tuple(terminal_pairs),
        "needs_transitions": needs_transitions,
        "initial_inventory_start": dict(initial_inventory_start),
        "boundary_mobilisation": dict(boundary_mobilisation),
        "boundary_transitions": tuple(boundary_transitions),
    }

    return model
