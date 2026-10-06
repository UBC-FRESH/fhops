.. AUTO-GENERATED from fhops_operational_formulation.md -- do not edit directly.

FHOPS’ deterministic operational solver is formulated on a day-shift
grid and maximizes weighted delivered production while penalizing
leftovers, landing over-capacity slack, and machine movement costs. The
equations below mirror the implemented Pyomo model in
``fhops.model.milp.operational.build_operational_model`` and the bundle
normalization in ``fhops.model.milp.data.build_operational_bundle``.

**Problem statement.** Given harvest blocks, machine roles, shift
calendars, block windows, landing capacities, and harvest-system role
prerequisites, choose machine-block assignments and per-shift production
quantities to maximize weighted production subject to feasibility and
sequencing constraints.

**Sets and indices.**

- :math:`m \in \mathcal{M}`: machines.
- :math:`b \in \mathcal{B}`: blocks.
- :math:`s=(d,\sigma) \in \mathcal{S}`: shift slots indexed by day
  :math:`d \in \mathcal{D}` and shift label :math:`\sigma`, ordered by
  day and, within a day, by the scenario’s shift order;
  :math:`\operatorname{prev}(s)` is the preceding slot (the previous
  shift of the same day when there is one) and :math:`s'\prec s` means
  slot :math:`s'` precedes :math:`s`.
- :math:`\mathcal{B}^{\text{seq}} \subseteq \mathcal{B}`: blocks with an
  explicit harvest system (``harvest_system_id``); blocks in
  :math:`\mathcal{B}\setminus\mathcal{B}^{\text{seq}}` carry no
  sequencing obligations.
- :math:`\mathcal{R}_b`: ordered machine roles required by the harvest
  system assigned to block :math:`b\in\mathcal{B}^{\text{seq}}`
  (:math:`\mathcal{R}_b=\emptyset` otherwise).
- :math:`\mathcal{L}`: landings.
- :math:`\mathcal{P}^{\text{inv}} \subseteq \{(r,b): r \in \mathcal{R}_b\}`:
  role-block pairs with upstream prerequisites.
- :math:`\mathcal{P}^{\text{act}} \subseteq \mathcal{P}^{\text{inv}}`:
  role-block pairs that require positive head-start buffer activation.
- :math:`\mathcal{P}^{\text{hs}} \subseteq \mathcal{P}^{\text{act}}`:
  pairs with a head start of :math:`\beta_{r,b}>0` shifts
  (``role_headstart_shifts``); loader pairs without a head start are in
  :math:`\mathcal{P}^{\text{act}}\setminus\mathcal{P}^{\text{hs}}`.
- :math:`\mathcal{P}^{\text{load}} \subseteq \{(r,b): r \in \mathcal{R}_b\}`:
  loader role-block pairs.
- :math:`s_1 \in \mathcal{S}`: first shift slot of the horizon.
- :math:`\mathcal{M}^{0} \subseteq \mathcal{M}`: machines with a known
  initial block :math:`b^{0}_m` (optional initial state; empty by
  default).
- :math:`\mathcal{K}`: locked assignments
  :math:`k=(m_k,b_k,d_k,\sigma_k)`, where :math:`\sigma_k` is a shift
  label or empty (whole day);
  :math:`\mathcal{S}_k = \{s=(d_k,\sigma) \in \mathcal{S} : \sigma_k \text{ empty or } \sigma=\sigma_k\}`
  (empty by default).

**Parameters.**

- :math:`\bar{p}_{mb}`: production rate for machine :math:`m` on block
  :math:`b` (units per shift).
- :math:`W_b`: required total block production volume.
- :math:`A_{m,s} \in \{0,1\}`: machine availability for shift :math:`s`.
- :math:`\mathbf{1}^{\text{window}}_{b,d} \in \{0,1\}`: block window
  indicator (1 if day :math:`d` is within block :math:`b` window).
- :math:`\omega^{\text{prod}},\omega^{\text{mob}},\omega^{\text{trans}},\omega^{\text{land}}`:
  objective weights.
- :math:`\delta_{m,b',b}`: mobilization cost when machine :math:`m`
  transitions from block :math:`b'` to block :math:`b`.
- :math:`C_{\ell}`: daily assignment capacity for landing :math:`\ell`.
- :math:`\ell(b)`: landing associated with block :math:`b`.
- :math:`\mathcal{U}_{r,b}`: upstream roles that must feed role
  :math:`r` on block :math:`b`.
- :math:`B_{r,b}`: required staged buffer volume before role :math:`r`
  may activate on block :math:`b`:
  :math:`B_{r,b}=\beta_{r,b}\sum_{u\in\mathcal{U}_{r,b}}\sum_{m\in\mathcal{M}(u)}\bar{p}_{mb}`
  for a head start of :math:`\beta_{r,b}` shifts
  (``role_headstart_shifts``, 0 by default); loader roles use
  :math:`\max\{\beta_{r,b}\sum_{u\in\mathcal{U}_{r,b}}\sum_{m\in\mathcal{M}(u)}\bar{p}_{mb},\; \min(q^{\text{batch}}_{r,b}, R_{r,b})\}`
  (one truckload staged, or the whole remaining block volume when it is
  smaller).
- :math:`Q_{r,b}`: role production capacity upper bound per shift (used
  for activation linearization).
- :math:`q^{\text{batch}}_{r,b}`: loader batch size for loader role
  :math:`r` on block :math:`b`.
- :math:`\mathcal{T}_b \subseteq \mathcal{R}_b`: terminal roles for
  block :math:`b` (roles credited in block completion objective terms).
- :math:`\bar{I}_{u,b} \ge 0`: initial staged volume output by role
  :math:`u` on block :math:`b` and not yet consumed downstream (optional
  initial state; 0 by default).
- :math:`I^{0}_{r,b} = \min_{u\in\mathcal{U}_{r,b}} \bar{I}_{u,b}`:
  initial input inventory available to downstream role :math:`r` on
  block :math:`b` (0 by default).
- :math:`R_{r,b} \ge 0`: remaining volume role :math:`r` may still
  output on block :math:`b`: the carried-in value when the optional
  initial state supplies one, otherwise :math:`W_b` (every role handles
  the same wood).
- :math:`b^{0}_m`: block machine :math:`m\in\mathcal{M}^{0}` occupied in
  its last worked slot before the horizon.

**Decision variables.**

- :math:`x_{m,b,s} \in \{0,1\}`: 1 if machine :math:`m` is assigned to
  block :math:`b` in shift :math:`s`.
- :math:`p_{m,b,s} \ge 0`: production by machine :math:`m` on block
  :math:`b` in shift :math:`s`.
- :math:`z_{r,b,s} \ge 0`: aggregated role-level production for role
  :math:`r` on block :math:`b` in shift :math:`s`.
- :math:`y_{m,b',b,s} \in \{0,1\}`: transition indicator for machine
  :math:`m` from previous-shift block :math:`b'` to current block
  :math:`b` (defined for non-initial shifts).
- :math:`I^{\text{start}}_{r,b,s} \ge 0`: staged inventory available at
  start of shift :math:`s` for role :math:`r` on block :math:`b`.
- :math:`I_{r,b,s} \ge 0`: staged inventory at end of shift :math:`s`
  for role :math:`r` on block :math:`b`.
- :math:`g_{r,b,s} \in \{0,1\}`: role activation indicator for buffered
  downstream roles.
- :math:`h_{r,b,s} \in \{0,1\}`,
  :math:`(r,b)\in\mathcal{P}^{\text{hs}}`: 1 only if every upstream role
  of :math:`r` on block :math:`b` has output its whole remaining volume
  before slot :math:`s` (the buffer can no longer grow and is waived).
- :math:`n_{r,b,s} \in \mathbb{Z}_{\ge 0}`: loader batch count for
  loader role-block pair :math:`(r,b)`.
- :math:`u_{r,b,s} \ge 0`: loader partial remainder volume.
- :math:`L_b \ge 0`: leftover unmet block volume slack.
- :math:`S_{\ell,d} \ge 0`: landing daily surplus slack.

**Objective.**

FHOPS maximizes weighted terminal production and subtracts penalty
terms:

.. math::


   \begin{aligned}
   \max\; &\omega^{\text{prod}}\!\sum_{b\in\mathcal{B}}\sum_{r\in\mathcal{T}_b}\sum_{s\in\mathcal{S}} z_{r,b,s}
   - \omega^{\text{prod}}\!\sum_{b\in\mathcal{B}} L_b \\
   &- \omega^{\text{land}}\!\sum_{\ell\in\mathcal{L}}\sum_{d\in\mathcal{D}} S_{\ell,d} \\
   &- \omega^{\text{mob}}\!\sum_{m,b',b,s} \delta_{m,b',b}\, y_{m,b',b,s}
   - \omega^{\text{trans}}\!\sum_{m,b',b,s} y_{m,b',b,s} \\
   &- \sum_{m\in\mathcal{M}^{0}}\sum_{b\in\mathcal{B}\setminus\{b^{0}_m\}}
   \left(\omega^{\text{mob}}\,\delta_{m,b^{0}_m,b} + \omega^{\text{trans}}\right) x_{m,b,s_1}.
   \end{aligned}

The last line is the boundary transition from each machine’s initial
block into the first slot. It is linear in :math:`x` because
:math:`b^{0}_m` is data; with no initial state
(:math:`\mathcal{M}^{0}=\emptyset`) it vanishes and the objective is the
v1.0.0 objective.

For blocks without terminal roles (:math:`\mathcal{T}_b=\emptyset`, in
particular blocks outside :math:`\mathcal{B}^{\text{seq}}`) the
production reward and the block balance use the machine-level sum
:math:`\sum_{m}\sum_{s} p_{m,b,s}` in place of
:math:`\sum_{r\in\mathcal{T}_b}\sum_s z_{r,b,s}`.

**Constraints.**

Machine assignment feasibility:

.. math::


   \sum_{b\in\mathcal{B}} x_{m,b,s} \le A_{m,s}
   \qquad \forall m\in\mathcal{M},\; s\in\mathcal{S}.

Role compatibility (machines can only work roles allowed by the block’s
assigned harvest system):

.. math::


   x_{m,b,s}=0 \quad \text{if } b\in\mathcal{B}^{\text{seq}} \text{ and role}(m)\notin\mathcal{R}_b.

Production upper bound per assignment:

.. math::


   p_{m,b,s} \le \bar{p}_{mb}\,x_{m,b,s}
   \qquad \forall m,b,s.

Block window enforcement:

.. math::


   x_{m,b,s}=0 \quad \text{if } \mathbf{1}^{\text{window}}_{b,d}=0 \text{ for } s=(d,\sigma).

Role-production aggregation:

.. math::


   z_{r,b,s} = \sum_{m\in\mathcal{M}(r)} p_{m,b,s}
   \qquad \forall (r,b), s.

Transition linking (for non-initial shifts only):

.. math::


   y_{m,b',b,s} \le x_{m,b',\operatorname{prev}(s)},
   \qquad
   y_{m,b',b,s} \le x_{m,b,s},

.. math::


   y_{m,b',b,s} \ge x_{m,b',\operatorname{prev}(s)} + x_{m,b,s} - 1.

Role inventory start and balance for prerequisite-driven downstream
roles:

.. math::


   I^{\text{start}}_{r,b,s}=
   \begin{cases}
   I^{0}_{r,b}, & s = s_1\\
   I_{r,b,\operatorname{prev}(s)}, & \text{otherwise}
   \end{cases}
   \qquad \forall (r,b)\in\mathcal{P}^{\text{inv}}, s,

.. math::


   I_{r,b,s}=I^{\text{start}}_{r,b,s}+\sum_{u\in\mathcal{U}_{r,b}} z_{u,b,s}-z_{r,b,s}
   \qquad \forall (r,b)\in\mathcal{P}^{\text{inv}}, s,

.. math::


   z_{r,b,s} \le I^{\text{start}}_{r,b,s}
   \qquad \forall (r,b)\in\mathcal{P}^{\text{inv}}, s.

Head-start activation for buffered downstream roles:

.. math::


   z_{r,b,s} \le Q_{r,b}\,g_{r,b,s}
   \qquad \forall (r,b)\in\mathcal{P}^{\text{act}}, s,

.. math::


   I_{r,b,\operatorname{prev}(s)} \ge B_{r,b}\,g_{r,b,s}
   \qquad \forall (r,b)\in\mathcal{P}^{\text{act}}\setminus\mathcal{P}^{\text{hs}}, s,
   \qquad
   I_{r,b,\operatorname{prev}(s)} \ge B_{r,b}\,\left(g_{r,b,s}-h_{r,b,s}\right)
   \qquad \forall (r,b)\in\mathcal{P}^{\text{hs}}, s,

with :math:`I_{r,b,\operatorname{prev}(s_1)} := I^{0}_{r,b}`, and

.. math::


   \sum_{s'\prec s} z_{u,b,s'} \ge R_{u,b}\,h_{r,b,s}
   \qquad \forall (r,b)\in\mathcal{P}^{\text{hs}},\; u\in\mathcal{U}_{r,b},\; s,

.. math::


   \sum_{m\in\mathcal{M}(r)} x_{m,b,s} \le |\mathcal{M}(r)|\, g_{r,b,s},
   \qquad
   g_{r,b,s} \le \sum_{m\in\mathcal{M}(r)} x_{m,b,s}
   \qquad \forall (r,b)\in\mathcal{P}^{\text{act}}, s.

Loader batching:

.. math::


   z_{r,b,s}=q^{\text{batch}}_{r,b}\,n_{r,b,s}+u_{r,b,s}
   \qquad \forall (r,b)\in\mathcal{P}^{\text{load}}, s,

.. math::


   0 \le u_{r,b,s} \le q^{\text{batch}}_{r,b}
   \qquad \forall (r,b)\in\mathcal{P}^{\text{load}}, s.

Block completion balance with leftover slack:

.. math::


   \sum_{r\in\mathcal{T}_b}\sum_{s\in\mathcal{S}} z_{r,b,s} + L_b = W_b
   \qquad \forall b\in\mathcal{B}.

Remaining role output (no role can handle more wood than the block still
holds):

.. math::


   \sum_{s\in\mathcal{S}} z_{r,b,s} \le R_{r,b}
   \qquad \forall b\in\mathcal{B}^{\text{seq}},\; r\in\mathcal{R}_b.

Locked assignments (a lock without a shift label pins every available
shift of its day; a lock with a shift label pins only that slot):

.. math::


   x_{m_k,b,s} = A_{m_k,s}\,\mathbf{1}[b=b_k]
   \qquad \forall k\in\mathcal{K},\; s\in\mathcal{S}_k,\; b\in\mathcal{B}.

Landing daily assignment capacity with surplus slack:

.. math::


   \sum_{b:\,\ell(b)=\ell}\sum_{m\in\mathcal{M}}\sum_{\sigma:(d,\sigma)\in\mathcal{S}} x_{m,b,(d,\sigma)}
   \le C_{\ell} + S_{\ell,d}
   \qquad \forall \ell\in\mathcal{L},\; d\in\mathcal{D}.

Domain restrictions:

.. math::


   x, y, g, h \in \{0,1\},\quad n \in \mathbb{Z}_{\ge 0},\quad p,z,I^{\text{start}},I,u,L,S \ge 0.

**Initial state defaults.** Without ``Scenario.initial_state`` and
``Scenario.locked_assignments`` (:math:`\bar{I}\equiv 0`, hence
:math:`I^{0}\equiv 0`; :math:`R_{r,b}\equiv W_b`;
:math:`\mathcal{M}^{0}=\mathcal{K}=\emptyset`) the initial-state and
lock terms vanish.

**Changes from FHOPS v1.0.0 (1.0.1).** Three corrections make every MILP
plan physically feasible and replayable by the playback sequencing
tracker without violations: (i) the remaining-output cap now applies to
every role with :math:`R_{r,b}=W_b` by default (v1.0.0 let upstream
roles output more volume than the block holds and used that volume to
meet head-start and loader thresholds); (ii) the head-start constraint
of roles with a head start is waived through :math:`h_{r,b,s}` once
every upstream role has output its whole remaining volume, and the
loader threshold is :math:`\min(q^{\text{batch}}_{r,b}, R_{r,b})`, so
blocks smaller than a buffer or a truckload can still be finished
without the excess volume; (iii) blocks without a harvest system
(:math:`\mathcal{B}\setminus\mathcal{B}^{\text{seq}}`) have no role
obligations, as documented in the data contract (v1.0.0 applied the
registry’s default system to them). Playback, the heuristics, and the
rolling-horizon carry-forward apply the same rules: staged output is
available from the next shift slot, buffers are staged volume at the
start of the slot, and production is capped by :math:`R_{r,b}`.

**Implementation mapping (equation blocks to code).**

- Machine capacity and availability: ``model.machine_capacity``
  (``machine_capacity_rule``)
- Role compatibility: ``model.role_compatibility``
  (``role_compatibility_rule``; skipped for
  ``bundle.unsequenced_blocks``)
- Production-assignment coupling: ``model.production_cap``
  (``prod_cap_rule``)
- Block windows: ``model.block_windows`` (``window_rule``)
- Role aggregation: ``model.role_prod_balance``
  (``role_prod_balance_rule``)
- Transition linkage: ``model.transition_prev``,
  ``model.transition_curr``, ``model.transition_link``
- Inventory dynamics and guards: ``model.inventory_start_eq`` (first
  slot uses :math:`I^{0}_{r,b}` from
  ``bundle.initial_staged_inventory``), ``model.inventory_balance``,
  ``model.inventory_guard``
- Head-start activation: ``model.activation_prod``,
  ``model.head_start``, ``model.role_active_upper``,
  ``model.role_active_lower``; buffer waiver
  ``model.upstream_done_link`` (cumulative upstream output
  ``model.role_cumulative_eq``); :math:`B_{r,b}` from
  ``headstart_buffer_volumes(...)`` in ``fhops.model.milp.data``
- Loader batching: ``model.loader_batch``, ``model.loader_partial_cap``
- Block balance with leftovers: ``model.block_balance``
  (``block_balance_rule``) + ``model.leftover``
- Remaining role output: ``model.role_remaining_cap`` (from
  ``bundle.initial_role_remaining``, default :math:`W_b`)
- Locked assignments: ``model.locked_assignment`` (from
  ``bundle.locked_assignments``)
- Landing capacity with slack: ``model.landing_capacity``
  (``landing_capacity_rule``) + ``model.landing_surplus``
- Objective assembly: ``model.objective`` and objective-term
  construction around ``prod_weight``, ``landing_weight``,
  ``mobilisation_weight``, ``transition_weight``, including the
  first-slot boundary term from ``bundle.initial_machine_block``
- Data/parameter normalization: ``build_operational_bundle(...)`` in
  ``fhops.model.milp.data`` (flattens ``Scenario.initial_state`` and
  ``Scenario.locked_assignments`` into the bundle)

This formulation is the canonical mathematical reference for FHOPS
operational MILP documentation and thesis-level reporting.
