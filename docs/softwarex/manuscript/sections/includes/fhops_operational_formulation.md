FHOPS' deterministic operational solver is formulated on a day-shift grid and maximizes weighted delivered production while penalizing leftovers, landing over-capacity slack, and machine movement costs. The equations below mirror the implemented Pyomo model in `fhops.model.milp.operational.build_operational_model` and the bundle normalization in `fhops.model.milp.data.build_operational_bundle`.

**Problem statement.**
Given harvest blocks, machine roles, shift calendars, block windows, landing capacities, and harvest-system role prerequisites, choose machine-block assignments and per-shift production quantities to maximize weighted production subject to feasibility and sequencing constraints.

**Sets and indices.**

- $m \in \mathcal{M}$: machines.
- $b \in \mathcal{B}$: blocks.
- $s=(d,\sigma) \in \mathcal{S}$: shift slots indexed by day $d \in \mathcal{D}$ and shift label $\sigma$.
- $\mathcal{R}_b$: ordered machine roles required by the harvest system assigned to block $b$.
- $\mathcal{L}$: landings.
- $\mathcal{P}^{\text{inv}} \subseteq \{(r,b): r \in \mathcal{R}_b\}$: role-block pairs with upstream prerequisites.
- $\mathcal{P}^{\text{act}} \subseteq \mathcal{P}^{\text{inv}}$: role-block pairs that require positive head-start buffer activation.
- $\mathcal{P}^{\text{load}} \subseteq \{(r,b): r \in \mathcal{R}_b\}$: loader role-block pairs.
- $s_1 \in \mathcal{S}$: first shift slot of the horizon.
- $\mathcal{M}^{0} \subseteq \mathcal{M}$: machines with a known initial block $b^{0}_m$ (optional initial state; empty by default).
- $\mathcal{P}^{\text{rem}} \subseteq \{(r,b): r \in \mathcal{R}_b\}$: role-block pairs with a carried-in remaining-output cap (optional initial state; empty by default).
- $\mathcal{K}$: locked assignments $k=(m_k,b_k,d_k,\sigma_k)$, where $\sigma_k$ is a shift label or empty (whole day); $\mathcal{S}_k = \{s=(d_k,\sigma) \in \mathcal{S} : \sigma_k \text{ empty or } \sigma=\sigma_k\}$ (empty by default).

**Parameters.**

- $\bar{p}_{mb}$: production rate for machine $m$ on block $b$ (units per shift).
- $W_b$: required total block production volume.
- $A_{m,s} \in \{0,1\}$: machine availability for shift $s$.
- $\mathbf{1}^{\text{window}}_{b,d} \in \{0,1\}$: block window indicator (1 if day $d$ is within block $b$ window).
- $\omega^{\text{prod}},\omega^{\text{mob}},\omega^{\text{trans}},\omega^{\text{land}}$: objective weights.
- $\delta_{m,b',b}$: mobilization cost when machine $m$ transitions from block $b'$ to block $b$.
- $C_{\ell}$: daily assignment capacity for landing $\ell$.
- $\ell(b)$: landing associated with block $b$.
- $\mathcal{U}_{r,b}$: upstream roles that must feed role $r$ on block $b$.
- $B_{r,b}$: required staged buffer volume before role $r$ may activate on block $b$.
- $Q_{r,b}$: role production capacity upper bound per shift (used for activation linearization).
- $q^{\text{batch}}_{r,b}$: loader batch size for loader role $r$ on block $b$.
- $\mathcal{T}_b \subseteq \mathcal{R}_b$: terminal roles for block $b$ (roles credited in block completion objective terms).
- $\bar{I}_{u,b} \ge 0$: initial staged volume output by role $u$ on block $b$ and not yet consumed downstream (optional initial state; 0 by default).
- $I^{0}_{r,b} = \min_{u\in\mathcal{U}_{r,b}} \bar{I}_{u,b}$: initial input inventory available to downstream role $r$ on block $b$ (0 by default).
- $R_{r,b} \ge 0$: remaining volume role $r$ may still output on block $b$, for $(r,b)\in\mathcal{P}^{\text{rem}}$.
- $b^{0}_m$: block machine $m\in\mathcal{M}^{0}$ occupied in its last worked slot before the horizon.

**Decision variables.**

- $x_{m,b,s} \in \{0,1\}$: 1 if machine $m$ is assigned to block $b$ in shift $s$.
- $p_{m,b,s} \ge 0$: production by machine $m$ on block $b$ in shift $s$.
- $z_{r,b,s} \ge 0$: aggregated role-level production for role $r$ on block $b$ in shift $s$.
- $y_{m,b',b,s} \in \{0,1\}$: transition indicator for machine $m$ from previous-shift block $b'$ to current block $b$ (defined for non-initial shifts).
- $I^{\text{start}}_{r,b,s} \ge 0$: staged inventory available at start of shift $s$ for role $r$ on block $b$.
- $I_{r,b,s} \ge 0$: staged inventory at end of shift $s$ for role $r$ on block $b$.
- $g_{r,b,s} \in \{0,1\}$: role activation indicator for buffered downstream roles.
- $n_{r,b,s} \in \mathbb{Z}_{\ge 0}$: loader batch count for loader role-block pair $(r,b)$.
- $u_{r,b,s} \ge 0$: loader partial remainder volume.
- $L_b \ge 0$: leftover unmet block volume slack.
- $S_{\ell,d} \ge 0$: landing daily surplus slack.

**Objective.**

FHOPS maximizes weighted terminal production and subtracts penalty terms:

$$
\begin{aligned}
\max\; &\omega^{\text{prod}}\!\sum_{b\in\mathcal{B}}\sum_{r\in\mathcal{T}_b}\sum_{s\in\mathcal{S}} z_{r,b,s}
- \omega^{\text{prod}}\!\sum_{b\in\mathcal{B}} L_b \\
&- \omega^{\text{land}}\!\sum_{\ell\in\mathcal{L}}\sum_{d\in\mathcal{D}} S_{\ell,d} \\
&- \omega^{\text{mob}}\!\sum_{m,b',b,s} \delta_{m,b',b}\, y_{m,b',b,s}
- \omega^{\text{trans}}\!\sum_{m,b',b,s} y_{m,b',b,s} \\
&- \sum_{m\in\mathcal{M}^{0}}\sum_{b\in\mathcal{B}\setminus\{b^{0}_m\}}
\left(\omega^{\text{mob}}\,\delta_{m,b^{0}_m,b} + \omega^{\text{trans}}\right) x_{m,b,s_1}.
\end{aligned}
$$

The last line is the boundary transition from each machine's initial block into the first slot. It is linear in $x$ because $b^{0}_m$ is data; with no initial state ($\mathcal{M}^{0}=\emptyset$) it vanishes and the objective is the v1.0.0 objective.

If a block has no terminal-role metadata, the implementation falls back to machine-level production sums for the production reward term.

**Constraints.**

Machine assignment feasibility:

$$
\sum_{b\in\mathcal{B}} x_{m,b,s} \le A_{m,s}
\qquad \forall m\in\mathcal{M},\; s\in\mathcal{S}.
$$

Role compatibility (machines can only work roles allowed by the block's assigned harvest system):

$$
x_{m,b,s}=0 \quad \text{if role}(m)\notin\mathcal{R}_b.
$$

Production upper bound per assignment:

$$
p_{m,b,s} \le \bar{p}_{mb}\,x_{m,b,s}
\qquad \forall m,b,s.
$$

Block window enforcement:

$$
x_{m,b,s}=0 \quad \text{if } \mathbf{1}^{\text{window}}_{b,d}=0 \text{ for } s=(d,\sigma).
$$

Role-production aggregation:

$$
z_{r,b,s} = \sum_{m\in\mathcal{M}(r)} p_{m,b,s}
\qquad \forall (r,b), s.
$$

Transition linking (for non-initial shifts only):

$$
y_{m,b',b,s} \le x_{m,b',\operatorname{prev}(s)},
\qquad
y_{m,b',b,s} \le x_{m,b,s},
$$
$$
y_{m,b',b,s} \ge x_{m,b',\operatorname{prev}(s)} + x_{m,b,s} - 1.
$$

Role inventory start and balance for prerequisite-driven downstream roles:

$$
I^{\text{start}}_{r,b,s}=
\begin{cases}
I^{0}_{r,b}, & s = s_1\\
I_{r,b,\operatorname{prev}(s)}, & \text{otherwise}
\end{cases}
\qquad \forall (r,b)\in\mathcal{P}^{\text{inv}}, s,
$$

$$
I_{r,b,s}=I^{\text{start}}_{r,b,s}+\sum_{u\in\mathcal{U}_{r,b}} z_{u,b,s}-z_{r,b,s}
\qquad \forall (r,b)\in\mathcal{P}^{\text{inv}}, s,
$$

$$
z_{r,b,s} \le I^{\text{start}}_{r,b,s}
\qquad \forall (r,b)\in\mathcal{P}^{\text{inv}}, s.
$$

Head-start activation for buffered downstream roles:

$$
z_{r,b,s} \le Q_{r,b}\,g_{r,b,s}
\qquad \forall (r,b)\in\mathcal{P}^{\text{act}}, s,
$$

$$
I_{r,b,\operatorname{prev}(s)} \ge B_{r,b}\,g_{r,b,s}
\qquad \forall (r,b)\in\mathcal{P}^{\text{act}}, s,
\qquad \text{with } I_{r,b,\operatorname{prev}(s_1)} := I^{0}_{r,b},
$$

$$
\sum_{m\in\mathcal{M}(r)} x_{m,b,s} \le |\mathcal{M}(r)|\, g_{r,b,s},
\qquad
g_{r,b,s} \le \sum_{m\in\mathcal{M}(r)} x_{m,b,s}
\qquad \forall (r,b)\in\mathcal{P}^{\text{act}}, s.
$$

Loader batching:

$$
z_{r,b,s}=q^{\text{batch}}_{r,b}\,n_{r,b,s}+u_{r,b,s}
\qquad \forall (r,b)\in\mathcal{P}^{\text{load}}, s,
$$

$$
0 \le u_{r,b,s} \le q^{\text{batch}}_{r,b}
\qquad \forall (r,b)\in\mathcal{P}^{\text{load}}, s.
$$

Block completion balance with leftover slack:

$$
\sum_{r\in\mathcal{T}_b}\sum_{s\in\mathcal{S}} z_{r,b,s} + L_b = W_b
\qquad \forall b\in\mathcal{B}.
$$

Carried-in remaining role output (only for pairs supplied by the initial state):

$$
\sum_{s\in\mathcal{S}} z_{r,b,s} \le R_{r,b}
\qquad \forall (r,b)\in\mathcal{P}^{\text{rem}}.
$$

Locked assignments (a lock without a shift label pins every available shift of its day; a lock with a shift label pins only that slot):

$$
x_{m_k,b,s} = A_{m_k,s}\,\mathbf{1}[b=b_k]
\qquad \forall k\in\mathcal{K},\; s\in\mathcal{S}_k,\; b\in\mathcal{B}.
$$

Landing daily assignment capacity with surplus slack:

$$
\sum_{b:\,\ell(b)=\ell}\sum_{m\in\mathcal{M}}\sum_{\sigma:(d,\sigma)\in\mathcal{S}} x_{m,b,(d,\sigma)}
\le C_{\ell} + S_{\ell,d}
\qquad \forall \ell\in\mathcal{L},\; d\in\mathcal{D}.
$$

Domain restrictions:

$$
x, y, g \in \{0,1\},\quad n \in \mathbb{Z}_{\ge 0},\quad p,z,I^{\text{start}},I,u,L,S \ge 0.
$$

**Initial state defaults.** Without `Scenario.initial_state` and `Scenario.locked_assignments` ($\bar{I}\equiv 0$, hence $I^{0}\equiv 0$; $\mathcal{M}^{0}=\mathcal{P}^{\text{rem}}=\mathcal{K}=\emptyset$) every equation above reduces exactly to the FHOPS v1.0.0 formulation.

**Implementation mapping (equation blocks to code).**

- Machine capacity and availability: `model.machine_capacity` (`machine_capacity_rule`)
- Role compatibility: `model.role_compatibility` (`role_compatibility_rule`)
- Production-assignment coupling: `model.production_cap` (`prod_cap_rule`)
- Block windows: `model.block_windows` (`window_rule`)
- Role aggregation: `model.role_prod_balance` (`role_prod_balance_rule`)
- Transition linkage: `model.transition_prev`, `model.transition_curr`, `model.transition_link`
- Inventory dynamics and guards: `model.inventory_start_eq` (first slot uses $I^{0}_{r,b}$ from `bundle.initial_staged_inventory`), `model.inventory_balance`, `model.inventory_guard`
- Head-start activation: `model.activation_prod`, `model.head_start`, `model.role_active_upper`, `model.role_active_lower`
- Loader batching: `model.loader_batch`, `model.loader_partial_cap`
- Block balance with leftovers: `model.block_balance` (`block_balance_rule`) + `model.leftover`
- Carried-in remaining role output: `model.role_remaining_cap` (from `bundle.initial_role_remaining`)
- Locked assignments: `model.locked_assignment` (from `bundle.locked_assignments`)
- Landing capacity with slack: `model.landing_capacity` (`landing_capacity_rule`) + `model.landing_surplus`
- Objective assembly: `model.objective` and objective-term construction around `prod_weight`, `landing_weight`, `mobilisation_weight`, `transition_weight`, including the first-slot boundary term from `bundle.initial_machine_block`
- Data/parameter normalization: `build_operational_bundle(...)` in `fhops.model.milp.data` (flattens `Scenario.initial_state` and `Scenario.locked_assignments` into the bundle)

This formulation is the canonical mathematical reference for FHOPS operational MILP documentation and thesis-level reporting.
