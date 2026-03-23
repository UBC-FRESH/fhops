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
  :math:`d \in \mathcal{D}` and shift label :math:`\sigma`.
- :math:`\mathcal{R}_b`: ordered machine roles required by the harvest
  system assigned to block :math:`b`.
- :math:`\mathcal{L}`: landings.
- :math:`\mathcal{P}^{\text{inv}} \subseteq \{(r,b): r \in \mathcal{R}_b\}`:
  role-block pairs with upstream prerequisites.
- :math:`\mathcal{P}^{\text{act}} \subseteq \mathcal{P}^{\text{inv}}`:
  role-block pairs that require positive head-start buffer activation.
- :math:`\mathcal{P}^{\text{load}} \subseteq \{(r,b): r \in \mathcal{R}_b\}`:
  loader role-block pairs.

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
  may activate on block :math:`b`.
- :math:`Q_{r,b}`: role production capacity upper bound per shift (used
  for activation linearization).
- :math:`q^{\text{batch}}_{r,b}`: loader batch size for loader role
  :math:`r` on block :math:`b`.
- :math:`\mathcal{T}_b \subseteq \mathcal{R}_b`: terminal roles for
  block :math:`b` (roles credited in block completion objective terms).

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
   - \omega^{\text{trans}}\!\sum_{m,b',b,s} y_{m,b',b,s}.
   \end{aligned}

If a block has no terminal-role metadata, the implementation falls back
to machine-level production sums for the production reward term.

**Constraints.**

Machine assignment feasibility:

.. math::


   \sum_{b\in\mathcal{B}} x_{m,b,s} \le A_{m,s}
   \qquad \forall m\in\mathcal{M},\; s\in\mathcal{S}.

Role compatibility (machines can only work roles allowed by the block’s
assigned harvest system):

.. math::


   x_{m,b,s}=0 \quad \text{if role}(m)\notin\mathcal{R}_b.

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
   0, & s \text{ is first shift}\\
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
   \qquad \forall (r,b)\in\mathcal{P}^{\text{act}}, s,

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

Landing daily assignment capacity with surplus slack:

.. math::


   \sum_{b:\,\ell(b)=\ell}\sum_{m\in\mathcal{M}}\sum_{\sigma:(d,\sigma)\in\mathcal{S}} x_{m,b,(d,\sigma)}
   \le C_{\ell} + S_{\ell,d}
   \qquad \forall \ell\in\mathcal{L},\; d\in\mathcal{D}.

Domain restrictions:

.. math::


   x, y, g \in \{0,1\},\quad n \in \mathbb{Z}_{\ge 0},\quad p,z,I^{\text{start}},I,u,L,S \ge 0.

**Implementation mapping (equation blocks to code).**

- Machine capacity and availability: ``model.machine_capacity``
  (``machine_capacity_rule``)
- Role compatibility: ``model.role_compatibility``
  (``role_compatibility_rule``)
- Production-assignment coupling: ``model.production_cap``
  (``prod_cap_rule``)
- Block windows: ``model.block_windows`` (``window_rule``)
- Role aggregation: ``model.role_prod_balance``
  (``role_prod_balance_rule``)
- Transition linkage: ``model.transition_prev``,
  ``model.transition_curr``, ``model.transition_link``
- Inventory dynamics and guards: ``model.inventory_start_eq``,
  ``model.inventory_balance``, ``model.inventory_guard``
- Head-start activation: ``model.activation_prod``,
  ``model.head_start``, ``model.role_active_upper``,
  ``model.role_active_lower``
- Loader batching: ``model.loader_batch``, ``model.loader_partial_cap``
- Block balance with leftovers: ``model.block_balance``
  (``block_balance_rule``) + ``model.leftover``
- Landing capacity with slack: ``model.landing_capacity``
  (``landing_capacity_rule``) + ``model.landing_surplus``
- Objective assembly: ``model.objective`` and objective-term
  construction around ``prod_weight``, ``landing_weight``,
  ``mobilisation_weight``, ``transition_weight``
- Data/parameter normalization: ``build_operational_bundle(...)`` in
  ``fhops.model.milp.data``

This formulation is the canonical mathematical reference for FHOPS
operational MILP documentation and thesis-level reporting.
