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
from dataclasses import dataclass

import pyomo.environ as pyo

from fhops.model.milp.data import (
    OperationalMilpBundle,
    headstart_buffer_volumes,
    machine_slot_available,
    resolve_locked_slots,
)

__all__ = ["build_operational_model"]

_REDUNDANCY_TOLERANCE = 1e-6

SlotKey = tuple[str, int, str]
#: Position flow entering a layer: a constant (1.0 for the carried-in block or the unplaced
#: state at the start) or the ``(machine, day, shift_id)`` key of the previous layer.
_FlowSource = float | SlotKey


@dataclass(frozen=True, slots=True)
class _MoveLayer:
    """One slot of a machine's position network (a slot in which the machine can work).

    ``reach`` maps each position the machine can hold before the slot to its flow source;
    ``cost`` is the common move cost of a machine whose move costs are all equal (hub arcs
    ``depart``/``arrive``), ``None`` when pair arcs ``y`` carry block-specific costs;
    ``unplaced`` is the source of the not-yet-worked state (``None`` with a carried-in block).
    """

    mach: str
    slot: tuple[int, str]
    cost: float | None
    reach: dict[str, _FlowSource]
    open_blocks: tuple[str, ...]
    unplaced: _FlowSource | None


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
      tracker's minimum rule — and the downstream roles of a fork share (split) the pool of their
      upstream role. In a fork that joins again (a diamond ``u → {r1, r2} → t``) the terminal
      role can therefore deliver at most half of what ``u`` outputs (see
      ``docs/howto/system_sequencing.rst``). For linear chains this is the v1.0.0 model with the
      inventory indexed by the upstream instead of the downstream role.
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

    Machine moves (#139): a machine moves when it works a block other than its *position*, the
    block of its last worked slot (idle slots keep it) or its carried-in ``last_block_id``. Each
    move costs ``ω_mob·δ(m, b', b) + ω_trans`` -- staying on a block costs nothing -- exactly as
    in the heuristics (``_recompute_mobilisation_for``) and the KPIs. The position of each machine
    is a unit flow through one network layer per slot in which it can work: ``stay`` keeps the
    position, ``y[m, b', b, s]`` moves it (``depart``/``arrive`` through a hub when all move
    costs of the machine are equal), ``first`` places a machine without carried-in block at its
    first worked block (``unplaced`` until then); ``position_balance``, ``hub_balance`` and
    ``unplaced_balance`` conserve the flow, ``move_requires_work`` allows a position change only
    into a worked block and ``work_sets_position`` puts the whole unit on a worked block. For
    binary ``x`` every path of a flow decomposition follows the true position sequence, so the
    move cost is exact. Machines that can never be charged (zero weights, a single workable
    block) have no network.

    Landing capacity (per shift slot since 1.0.1, #125): ``landing_capacity[l, d, s]``
    limits the machines assigned to the blocks of landing ``l`` in slot ``(d, s)`` to
    ``Landing.daily_capacity`` (machines working the landing concurrently), exactly as the
    heuristics count it. With ``objective_weights.landing_surplus == 0`` the limit is hard (the
    heuristics charge 1000 per extra machine); a slot in which locks alone exceed the capacity has
    its limit raised to the locked count, with a warning. With a positive weight the overload is
    covered by unit slack pieces ``landing_surplus[l, d, s, k] ∈ [0, 1]`` priced ``k·ω_land``, so
    ``e`` surplus machines cost ``ω_land·e(e+1)/2`` — the heuristics' surplus accounting, in
    which the ``k``-th machine beyond capacity adds ``k``.

    Initial state and locks (no-ops for default bundles):

    * ``bundle.initial_staged_inventory`` sets the first-slot ``inventory_start[u, b]`` of each
      upstream role to its carried-in staged volume; head-start and loader thresholds at the first
      slot use the same value.
    * ``bundle.initial_role_remaining`` sets ``R_{r,b}`` (capped at ``W_b``) and the head-start
      waiver threshold.
    * ``bundle.initial_machine_block`` is the machine's position before the first slot: its
      first worked slot (not necessarily the first slot) is charged a move to any other block.
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
    loader_gate_pairs: list[tuple[str, str]] = []
    role_upstream: dict[tuple[str, str], tuple[str, ...]] = {}
    role_buffer_volume: dict[tuple[str, str], float] = {}
    role_capacity: dict[tuple[str, str], float] = {}
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

    # Locks are resolved before the activation coupling and the move tracking, which need them.
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

    # Machine moves (mobilisation and transitions, #139). A machine moves when it works block b in
    # slot s while its *position* -- the block of its last worked slot, or the carried-in block
    # b0 -- is another block b'. Idle slots keep the position, so moves across idle slots and from
    # b0 into the first worked slot are charged exactly as by the heuristics
    # (_recompute_mobilisation_for) and the KPIs. Each machine's position is a unit flow through a
    # layered network (one layer per slot in which the machine can work): `stay` keeps the
    # position, `y` (or `depart` -> hub -> `arrive` when all move costs of the machine are equal)
    # moves it, `first` places a machine without b0 at its first worked block (`unplaced` before).
    # `move_requires_work` (no position change without working the new block) and
    # `work_sets_position` (working b puts the whole unit at b) force every path of a flow
    # decomposition along the true position sequence when x is binary, so the move cost is exact.
    mobilisation_weight = bundle.objective_weights.mobilisation
    transition_weight = bundle.objective_weights.transitions
    moves_priced = bool(mobilisation_weight > 0 or transition_weight > 0)

    def _move_cost(mach: str, prev_blk: str, curr_blk: str) -> float:
        return mobilisation_weight * _mobil_cost(mach, prev_blk, curr_blk) + transition_weight

    def _open_blocks(mach: str, slot: tuple[int, str], candidates: list[str]) -> list[str]:
        """Blocks the machine may be assigned to in ``slot`` (``x`` not fixed to 0)."""

        if not _is_available(mach, slot[0], slot[1]):
            return []
        open_blocks = [blk for blk in candidates if _within_window(blk, slot[0])]
        if (mach, slot) in lock_slot_targets:
            target = lock_slot_targets[(mach, slot)]
            open_blocks = [blk for blk in open_blocks if blk == target]
        return open_blocks

    stay_index: list[tuple[str, str, int, str]] = []
    depart_index: list[tuple[str, str, int, str]] = []
    arrive_index: list[tuple[str, str, int, str]] = []
    pair_index: list[tuple[str, str, str, int, str]] = []
    pair_cost: dict[tuple[str, str, str, int, str], float] = {}
    first_index: list[tuple[str, str, int, str]] = []
    unplaced_index: list[SlotKey] = []
    # One layer per machine and slot in which the machine can work (see _MoveLayer).
    layers: list[_MoveLayer] = []
    for mach in machines if moves_priced else ():
        role = machine_roles.get(mach)
        eligible = [
            blk
            for blk in blocks
            if blk in unsequenced or (role is not None and role in block_roles.get(blk, ()))
        ]
        open_by_slot = {slot: _open_blocks(mach, slot, eligible) for slot in shift_list}
        workable = [blk for blk in eligible if any(blk in open_by_slot[s] for s in shift_list)]
        start_block = bundle.initial_machine_block.get(mach)
        if start_block not in blocks:
            start_block = None
        tracked = list(workable)
        if start_block is not None and start_block not in tracked:
            tracked.append(start_block)
        costs = {
            (prev_blk, blk): _move_cost(mach, prev_blk, blk)
            for prev_blk in tracked
            for blk in workable
            if prev_blk != blk
        }
        if not costs or max(costs.values()) <= 0:
            continue  # the machine can never be charged a move
        uniform = max(costs.values()) - min(costs.values()) <= 1e-12
        # reach[b]: position b before the slot -- 1.0 (b0 at the start), or the previous layer.
        reach: dict[str, _FlowSource] = {start_block: 1.0} if start_block is not None else {}
        unplaced: _FlowSource | None = None if start_block is not None else 1.0
        for slot in shift_list:
            open_here = open_by_slot[slot]
            if not open_here:
                continue  # the machine cannot work: its position carries over
            day, shift_id = slot
            for blk in reach:
                stay_index.append((mach, blk, day, shift_id))
                if uniform:
                    depart_index.append((mach, blk, day, shift_id))
                else:
                    for curr_blk in open_here:
                        if curr_blk != blk:
                            key = (mach, blk, curr_blk, day, shift_id)
                            pair_index.append(key)
                            pair_cost[key] = costs[(blk, curr_blk)]
            if uniform and reach:
                arrive_index.extend((mach, blk, day, shift_id) for blk in open_here)
            if unplaced is not None:
                unplaced_index.append((mach, day, shift_id))
                first_index.extend((mach, blk, day, shift_id) for blk in open_here)
            layers.append(
                _MoveLayer(
                    mach=mach,
                    slot=slot,
                    cost=max(costs.values()) if uniform else None,
                    reach=dict(reach),
                    open_blocks=tuple(open_here),
                    unplaced=unplaced,
                )
            )
            reach = {
                blk: (mach, day, shift_id) for blk in tracked if blk in reach or blk in open_here
            }
            if unplaced is not None:
                unplaced = (mach, day, shift_id)

    mobilisation_expr = None
    if layers:
        model.StayIndex = pyo.Set(initialize=stay_index, dimen=4)
        model.stay = pyo.Var(model.StayIndex, domain=pyo.NonNegativeReals)
        model.DepartIndex = pyo.Set(initialize=depart_index, dimen=4)
        model.depart = pyo.Var(model.DepartIndex, domain=pyo.NonNegativeReals)
        model.ArriveIndex = pyo.Set(initialize=arrive_index, dimen=4)
        model.arrive = pyo.Var(model.ArriveIndex, domain=pyo.NonNegativeReals)
        model.TransitionIndex = pyo.Set(initialize=pair_index, dimen=5)
        model.y = pyo.Var(model.TransitionIndex, domain=pyo.NonNegativeReals)
        model.FirstIndex = pyo.Set(initialize=first_index, dimen=4)
        model.first = pyo.Var(model.FirstIndex, domain=pyo.NonNegativeReals)
        model.UnplacedIndex = pyo.Set(initialize=unplaced_index, dimen=3)
        model.unplaced = pyo.Var(model.UnplacedIndex, domain=pyo.NonNegativeReals)
        stay_set = frozenset(stay_index)
        arrive_set = frozenset(arrive_index)
        first_set = frozenset(first_index)
        moves_in: dict[tuple[str, str, int, str], list] = defaultdict(list)
        moves_out: dict[tuple[str, str, int, str], list] = defaultdict(list)
        for mach, prev_blk, blk, day, shift_id in pair_index:
            var = model.y[mach, prev_blk, blk, day, shift_id]
            moves_in[(mach, blk, day, shift_id)].append(var)
            moves_out[(mach, prev_blk, day, shift_id)].append(var)

        def _arrivals(mach: str, blk: str, day: int, shift_id: str):
            key = (mach, blk, day, shift_id)
            total = sum(moves_in.get(key, []))
            if key in arrive_set:
                total = total + model.arrive[key]
            return total

        def _placed(mach: str, blk: str, day: int, shift_id: str):
            key = (mach, blk, day, shift_id)
            return model.first[key] if key in first_set else 0.0

        def _position_after(mach: str, blk: str, day: int, shift_id: str):
            """Flow at position ``blk`` after the slot (0 when the block is unreachable)."""

            total = _arrivals(mach, blk, day, shift_id) + _placed(mach, blk, day, shift_id)
            if (mach, blk, day, shift_id) in stay_set:
                total = total + model.stay[mach, blk, day, shift_id]
            return total

        balance_rows: list[tuple[str, str, int, str]] = []
        balance_source: dict[tuple[str, str, int, str], _FlowSource] = {}
        hub_rows: list[SlotKey] = []
        link_rows: list[tuple[str, str, int, str]] = []
        unplaced_source: dict[SlotKey, _FlowSource] = {}
        move_terms: list = []
        for layer in layers:
            mach = layer.mach
            day, shift_id = layer.slot
            for blk, source in layer.reach.items():
                balance_rows.append((mach, blk, day, shift_id))
                balance_source[(mach, blk, day, shift_id)] = source
            if layer.cost is not None and layer.reach:
                hub_rows.append((mach, day, shift_id))
                move_terms.extend(
                    layer.cost * model.arrive[mach, blk, day, shift_id] for blk in layer.open_blocks
                )
            if layer.unplaced is not None:
                unplaced_source[(mach, day, shift_id)] = layer.unplaced
            link_rows.extend((mach, blk, day, shift_id) for blk in layer.open_blocks)
        move_terms.extend(cost * model.y[key] for key, cost in pair_cost.items() if cost > 0)

        def _source_value(source: _FlowSource, blk: str | None):
            if isinstance(source, float):
                return source
            mach, day, shift_id = source
            if blk is None:
                return model.unplaced[mach, day, shift_id]
            return _position_after(mach, blk, day, shift_id)

        model.PositionBalanceIndex = pyo.Set(initialize=balance_rows, dimen=4)

        def position_balance_rule(mdl, mach, blk, day, shift_id):
            key = (mach, blk, day, shift_id)
            leaving = sum(moves_out.get(key, []))
            if key in mdl.DepartIndex:
                leaving = leaving + mdl.depart[key]
            return _source_value(balance_source[key], blk) == mdl.stay[key] + leaving

        model.position_balance = pyo.Constraint(
            model.PositionBalanceIndex, rule=position_balance_rule
        )
        if hub_rows:
            model.HubIndex = pyo.Set(initialize=hub_rows, dimen=3)
            depart_by_slot: dict[SlotKey, list[str]] = defaultdict(list)
            arrive_by_slot: dict[SlotKey, list[str]] = defaultdict(list)
            for mach, blk, day, shift_id in depart_index:
                depart_by_slot[(mach, day, shift_id)].append(blk)
            for mach, blk, day, shift_id in arrive_index:
                arrive_by_slot[(mach, day, shift_id)].append(blk)

            def hub_balance_rule(mdl, mach, day, shift_id):
                key = (mach, day, shift_id)
                return sum(mdl.depart[mach, blk, day, shift_id] for blk in depart_by_slot[key]) == (
                    sum(mdl.arrive[mach, blk, day, shift_id] for blk in arrive_by_slot[key])
                )

            model.hub_balance = pyo.Constraint(model.HubIndex, rule=hub_balance_rule)
        if unplaced_index:
            first_by_slot: dict[SlotKey, list[str]] = defaultdict(list)
            for mach, blk, day, shift_id in first_index:
                first_by_slot[(mach, day, shift_id)].append(blk)

            def unplaced_balance_rule(mdl, mach, day, shift_id):
                key = (mach, day, shift_id)
                return _source_value(unplaced_source[key], None) == mdl.unplaced[key] + sum(
                    mdl.first[mach, blk, day, shift_id] for blk in first_by_slot[key]
                )

            model.unplaced_balance = pyo.Constraint(model.UnplacedIndex, rule=unplaced_balance_rule)
        model.MoveLinkIndex = pyo.Set(initialize=link_rows, dimen=4)

        def move_requires_work_rule(mdl, mach, blk, day, shift_id):
            moved_in = _arrivals(mach, blk, day, shift_id) + _placed(mach, blk, day, shift_id)
            if isinstance(moved_in, float):
                return pyo.Constraint.Skip
            return moved_in <= mdl.x[mach, blk, (day, shift_id)]

        def work_sets_position_rule(mdl, mach, blk, day, shift_id):
            return mdl.x[mach, blk, (day, shift_id)] <= _position_after(mach, blk, day, shift_id)

        model.move_requires_work = pyo.Constraint(model.MoveLinkIndex, rule=move_requires_work_rule)
        model.work_sets_position = pyo.Constraint(model.MoveLinkIndex, rule=work_sets_position_rule)
        if move_terms:
            mobilisation_expr = sum(move_terms)

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

    # Landing capacity per shift slot (E11): machines working the landing's blocks in a slot.
    # Hard when the landing_surplus weight is 0; otherwise the k-th machine beyond capacity is
    # priced k·ω_land (unit slack pieces), the heuristics' surplus accounting.
    prod_weight = bundle.objective_weights.production
    landing_weight = bundle.objective_weights.landing_surplus
    landing_blocks: dict[str, list[str]] = defaultdict(list)
    for blk in blocks:
        landing = bundle.landing_for_block.get(blk)
        if landing is not None and landing in bundle.landing_capacity:
            landing_blocks[landing].append(blk)
    landing_ids = sorted(landing_blocks)
    landing_cap_eff, landing_warnings = _landing_slot_capacities(
        bundle, landing_blocks, lock_slot_targets, hard=not landing_weight
    )
    lock_warnings = tuple(lock_warnings) + landing_warnings
    if landing_ids:
        model.Landing = pyo.Set(initialize=landing_ids)
        if landing_weight:
            piece_index = [
                (landing_id, day, shift_id, piece)
                for landing_id in landing_ids
                for day, shift_id in shift_list
                for piece in range(
                    1, len(machines) - max(int(bundle.landing_capacity[landing_id]), 0) + 1
                )
            ]
            model.LandingSurplusIndex = pyo.Set(initialize=piece_index, dimen=4)
            model.landing_surplus = pyo.Var(
                model.LandingSurplusIndex, domain=pyo.NonNegativeReals, bounds=(0.0, 1.0)
            )
            surplus_pieces: dict[tuple[str, tuple[int, str]], list[int]] = defaultdict(list)
            for landing_id, day, shift_id, piece in piece_index:
                surplus_pieces[(landing_id, (day, shift_id))].append(piece)

        def landing_capacity_rule(mdl, landing_id, day, shift_id):
            slot = (day, shift_id)
            capacity = max(int(bundle.landing_capacity[landing_id]), 0)
            assigned = [
                mdl.x[mach, blk, slot] for blk in landing_blocks[landing_id] for mach in machines
            ]
            if len(machines) <= capacity:
                return pyo.Constraint.Skip  # each machine works at most one block per slot
            if landing_weight:
                pieces = surplus_pieces.get((landing_id, slot), [])
                return sum(assigned) <= capacity + sum(
                    mdl.landing_surplus[landing_id, day, shift_id, piece] for piece in pieces
                )
            return sum(assigned) <= landing_cap_eff.get((landing_id, slot), capacity)

        model.landing_capacity = pyo.Constraint(model.Landing, model.S, rule=landing_capacity_rule)

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
    if landing_weight and hasattr(model, "landing_surplus"):
        obj_expr -= landing_weight * sum(
            piece * model.landing_surplus[landing_id, day, shift_id, piece]
            for landing_id, day, shift_id, piece in model.LandingSurplusIndex
        )
    if mobilisation_expr is not None:
        # ω_mob·δ + ω_trans per move, including moves from the carried-in block b0.
        obj_expr -= mobilisation_expr

    model.objective = pyo.Objective(expr=obj_expr, sense=pyo.maximize)

    # Attach warm-start metadata so the driver can rebuild incumbent states.
    model._warm_start_meta = {
        "bundle": bundle,
        "shift_list": tuple(shift_list),
        "prev_shift_map": prev_shift_map,
        "role_upstream": role_upstream,
        "role_to_machines": {role: tuple(machines) for role, machines in role_to_machines.items()},
        "block_terminal_roles": block_terminal_roles,
        "inventory_pairs": tuple(stage_pairs),
        "stage_downstream": {pair: tuple(roles) for pair, roles in stage_downstream.items()},
        "activation_pairs": tuple(activation_pairs),
        "terminal_pairs": tuple(terminal_pairs),
        "initial_inventory_start": dict(initial_inventory_start),
        "locked_on_block": frozenset(locked_on_block),
        "lock_slot_targets": dict(lock_slot_targets),
        "loader_block_batch": dict(loader_block_batch),
        "warnings": list(lock_warnings),
    }

    return model


def _landing_slot_capacities(
    bundle: OperationalMilpBundle,
    landing_blocks: dict[str, list[str]],
    lock_slot_targets: dict[tuple[str, tuple[int, str]], str | None],
    *,
    hard: bool,
) -> tuple[dict[tuple[str, tuple[int, str]], int], tuple[str, ...]]:
    """Return per-slot landing capacities raised to the number of machines locked there.

    With a hard landing capacity (``landing_surplus`` weight 0), locks that place more machines on
    a landing in one slot than ``Landing.daily_capacity`` would make the model infeasible. The
    capacity of such a slot is raised to the locked count (so no unlocked machine may join) and a
    warning is returned; the heuristics charge the same unavoidable overload as penalties. With a
    soft capacity the surplus slack absorbs the overload and nothing is returned.
    """

    if not hard or not lock_slot_targets:
        return {}, ()
    block_landing = {blk: lnd for lnd, blks in landing_blocks.items() for blk in blks}
    locked_count: dict[tuple[str, tuple[int, str]], int] = defaultdict(int)
    for (_machine, slot), blk in lock_slot_targets.items():
        landing = block_landing.get(blk) if blk is not None else None
        if landing is not None:
            locked_count[(landing, slot)] += 1
    raised: dict[tuple[str, tuple[int, str]], int] = {}
    messages: list[str] = []
    for (landing, slot), count in sorted(locked_count.items()):
        capacity = max(int(bundle.landing_capacity[landing]), 0)
        if count > capacity:
            raised[(landing, slot)] = count
            messages.append(
                f"landing {landing} slot (day {slot[0]}, shift {slot[1]}): {count} locked "
                f"machines exceed its capacity {capacity}; capacity raised to the locked count "
                "for this slot (no other machine may work the landing)"
            )
    return raised, tuple(messages)
