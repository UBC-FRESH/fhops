FHOPS' deterministic operational solver is formulated on a day-shift grid and maximizes weighted delivered production while penalizing leftovers, landing over-capacity slack, and machine movement costs. The equations below mirror the implemented Pyomo model in `fhops.model.milp.operational.build_operational_model` and the bundle normalization in `fhops.model.milp.data.build_operational_bundle`.

**Problem statement.**
Given harvest blocks, machine roles, shift calendars, block windows, landing capacities, and harvest-system role prerequisites, choose machine-block assignments and per-shift production quantities to maximize weighted production subject to feasibility and sequencing constraints.

**Sets and indices.**

- $m \in \mathcal{M}$: machines.
- $b \in \mathcal{B}$: blocks.
- $s=(d,\sigma) \in \mathcal{S}$: shift slots indexed by day $d \in \mathcal{D}$ and shift label $\sigma$, ordered by day and, within a day, by the scenario's shift order; $\operatorname{prev}(s)$ is the preceding slot (the previous shift of the same day when there is one) and $s'\prec s$ means slot $s'$ precedes $s$.
- $\mathcal{B}^{\text{seq}} \subseteq \mathcal{B}$: blocks with an explicit harvest system (`harvest_system_id`); blocks in $\mathcal{B}\setminus\mathcal{B}^{\text{seq}}$ carry no sequencing obligations.
- $\mathcal{R}_b$: ordered machine roles required by the harvest system assigned to block $b\in\mathcal{B}^{\text{seq}}$ ($\mathcal{R}_b=\emptyset$ otherwise).
- $\mathcal{L}$: landings.
- $\mathcal{P}^{\text{inv}} \subseteq \{(r,b): r \in \mathcal{R}_b\}$: role-block pairs with upstream prerequisites.
- $\mathcal{P}^{\text{stg}} = \{(u,b): u \in \mathcal{U}_{r,b} \text{ for some } (r,b)\in\mathcal{P}^{\text{inv}}\}$: upstream role-block pairs whose output is staged for downstream roles; $\mathcal{N}_{u,b} = \{r: u\in\mathcal{U}_{r,b}\}$ are the downstream roles of $u$ on block $b$.
- $\mathcal{P}^{\text{hs}} \subseteq \mathcal{P}^{\text{inv}}$: pairs with a head start of $\beta_{r,b}>0$ shifts (`role_headstart_shifts`).
- $\mathcal{P}^{\text{load}} \subseteq \{(r,b): r \in \mathcal{R}_b\}$: loader role-block pairs; $\mathcal{P}^{\text{thr}} = \{(r,b)\in\mathcal{P}^{\text{load}}\cap\mathcal{P}^{\text{inv}}: q^{\text{batch}}_{b}>0,\ W_b>0\}$: loaders subject to the truckload threshold.
- $\mathcal{P}^{\text{act}} = \mathcal{P}^{\text{hs}} \cup \mathcal{P}^{\text{thr}}$: role-block pairs whose production is gated by an activation binary.
- $\mathcal{P}^{\text{cap}} \subseteq \{(r,b): r \in \mathcal{R}_b\setminus\mathcal{T}_b\}$: non-terminal pairs with a per-slot remaining-volume cap; it contains every non-terminal pair of systems with a role feeding several roles or with several terminal roles, and, in the other systems, the pairs whose carried-in state violates $R_{r,b} + \sum_{v\in\pi_{r,b}} \bar{I}_{v,b} \le W_b$ ($\pi_{r,b}$: $r$ and the non-terminal roles on its path to the terminal role). The cap is implied by the other constraints for all remaining pairs, and $\mathcal{P}^{\text{cap}}=\emptyset$ without an initial state in linear and joining systems.
- $\mathcal{S}^{\text{tail}}_b \subseteq \mathcal{S}$, $b$ with a loader in $\mathcal{P}^{\text{thr}}$ and $W_b > q^{\text{batch}}_b$: slots in which the remaining block volume can have fallen to one truckload, i.e. $\bar{D}_{b,s} > W_b - q^{\text{batch}}_b$, where $\bar{D}_{b,s} = \min\{W_b, \sum_{s'\prec s}\sum_{t\in\mathcal{T}_b}\sum_{m\in\mathcal{M}(t)} A_{m,s'}\mathbf{1}^{\text{window}}_{b,d(s')}\bar{p}_{mb}\}$ bounds the terminal output delivered before $s$.
- $s_1 \in \mathcal{S}$: first shift slot of the horizon.
- $\mathcal{M}^{0} \subseteq \mathcal{M}$: machines with a known initial block $b^{0}_m$ (optional initial state; empty by default); machines in $\mathcal{M}\setminus\mathcal{M}^{0}$ start *unplaced*.
- $\mathcal{K}$: locked assignments $k=(m_k,b_k,d_k,\sigma_k)$, where $\sigma_k$ is a shift label or empty (whole day); $\mathcal{S}_k = \{s=(d_k,\sigma) \in \mathcal{S} : \sigma_k \text{ empty or } \sigma=\sigma_k\}$ (empty by default). $\mathcal{K}_{b,s} = \{m_k: k\in\mathcal{K},\ b_k=b,\ s\in\mathcal{S}_k,\ \chi_k A_{m_k,s}=1\}$ are the machines locked to block $b$ in slot $s$.

**Parameters.**

- $\bar{p}_{mb}$: production rate for machine $m$ on block $b$ (units per shift).
- $W_b$: required total block production volume.
- $A_{m,s} \in \{0,1\}$: machine availability for shift $s$: $A_{m,s}=0$ when the machine's day or shift calendar marks it unavailable or when $s$ falls in a timeline blackout window, 1 otherwise. Blackouts are fleet-wide: on every day of a blackout window every machine is unavailable in every slot of that day (all slots of $\mathcal{S}$ on the day and the machine's own shift-calendar shifts), also when only some machines have shift-calendar entries.
- $\mathbf{1}^{\text{window}}_{b,d} \in \{0,1\}$: block window indicator (1 if day $d$ is within block $b$ window).
- $\omega^{\text{prod}},\omega^{\text{mob}},\omega^{\text{trans}},\omega^{\text{land}}$: objective weights.
- $\delta_{m,b',b} \ge 0$: mobilization cost when machine $m$ moves from block $b'$ to block $b \ne b'$; $c_{m,b',b} = \omega^{\text{mob}}\delta_{m,b',b} + \omega^{\text{trans}}$ is the weighted cost of the move.
- $C_{\ell}$: assignment capacity of landing $\ell$, the number of machines that may work its blocks concurrently in one shift slot (`Landing.daily_capacity`); $K_{\ell} = |\mathcal{M}| - C_{\ell}$ bounds the machines beyond capacity in a slot.
- $\ell(b)$: landing associated with block $b$.
- $\mathcal{U}_{r,b}$: upstream roles that must feed role $r$ on block $b$.
- $B_{r,b}$: head-start buffer volume that every upstream role of $r$ must have staged before $r$ may produce on block $b$: $B_{r,b}=\beta_{r,b}\sum_{u\in\mathcal{U}_{r,b}}\sum_{m\in\mathcal{M}(u)}\bar{p}_{mb}$ for a head start of $\beta_{r,b}$ shifts (`role_headstart_shifts`, 0 by default). When no machine of an upstream role has a positive rate on $b$, the role's own capacity is used instead, $B_{r,b}=\beta_{r,b}\,Q_{r,b}$. For a join the buffer, computed from the summed rates of all upstream roles, is required of each upstream role (head-start constraint below), so a slower upstream role needs more than $\beta_{r,b}$ shifts to stage it.
- $Q_{r,b}=\sum_{m\in\mathcal{M}(r)}\bar{p}_{mb}$: role production capacity per shift (1 when the role has no machine with a positive rate on $b$; used for the activation linearization).
- $q^{\text{batch}}_{b}$: truckload (loader batch) volume of block $b$'s harvest system (`loader_batch_volume_m3`, 30 m³ by default).
- $\mathcal{T}_b \subseteq \mathcal{R}_b$: terminal roles for block $b$ (roles credited in block completion objective terms).
- $\bar{I}_{u,b} \ge 0$: initial staged volume output by role $u$ on block $b$ and not yet consumed downstream (optional initial state `staged_inventory`; 0 by default).
- $R^{0}_{r,b} \ge 0$: carried-in remaining volume role $r$ may still output on block $b$ (optional initial state `role_remaining`; $W_b$ by default).
- $R_{r,b} = \min(R^{0}_{r,b}, W_b)$: remaining volume role $r$ may output on block $b$ (every role handles the same wood, so no role can output more than the block still holds).
- $b^{0}_m$: block machine $m\in\mathcal{M}^{0}$ occupied in its last worked slot before the horizon.

**Decision variables.**

- $x_{m,b,s} \in \{0,1\}$: 1 if machine $m$ is assigned to block $b$ in shift $s$.
- $p_{m,b,s} \ge 0$: production by machine $m$ on block $b$ in shift $s$.
- $z_{r,b,s} \ge 0$: aggregated role-level production for role $r$ on block $b$ in shift $s$.
- $y_{m,b',b,s} \ge 0$, $b' \ne b$: machine $m$ moves in slot $s$ from its *position* $b'$ (the block of its last worked slot before $s$, or $b^{0}_m$) to block $b$, which it works in $s$.
- $\eta_{m,b,s} \ge 0$: machine $m$ keeps position $b$ through slot $s$ (it is idle or works $b$ again).
- $\phi_{m,b,s} \ge 0$, $m\notin\mathcal{M}^{0}$: the first worked slot of machine $m$ is $s$, on block $b$; $\nu_{m,s} \ge 0$, $m\notin\mathcal{M}^{0}$: machine $m$ has not worked up to and including $s$ (both $\equiv 0$ for $m\in\mathcal{M}^{0}$).
- $\pi_{m,b,s} = \eta_{m,b,s} + \sum_{b'\ne b} y_{m,b',b,s} + \phi_{m,b,s}$: machine $m$ holds position $b$ after slot $s$ (notation); $\pi_{m,b,\operatorname{prev}(s_1)} := \mathbf{1}[m\in\mathcal{M}^{0},\, b=b^{0}_m]$ and $\nu_{m,\operatorname{prev}(s_1)} := \mathbf{1}[m\notin\mathcal{M}^{0}]$.
- $I^{\text{start}}_{u,b,s} \ge 0$, $(u,b)\in\mathcal{P}^{\text{stg}}$: output of upstream role $u$ on block $b$ staged for its downstream roles at the start of shift $s$.
- $I_{u,b,s} \ge 0$: the same staged volume at the end of shift $s$.
- $g_{r,b,s} \in \{0,1\}$, $(r,b)\in\mathcal{P}^{\text{act}}$: role activation indicator; it gates production only.
- $h_{r,b,s} \in \{0,1\}$, $(r,b)\in\mathcal{P}^{\text{hs}}$: 1 only if every upstream role of $r$ on block $b$ has output its whole carried-in remaining volume before slot $s$ (the buffer can no longer grow and is waived).
- $\lambda_{b,s} \in \{0,1\}$, $s\in\mathcal{S}^{\text{tail}}_b$: 1 only once the remaining volume of block $b$ is at most one truckload (selects the active term of the loader threshold).
- $D_{b,s} = \sum_{t\in\mathcal{T}_b}\sum_{s'\preceq s} z_{t,b,s'}$: terminal output delivered on block $b$ up to and including slot $s$ (notation for a cumulative sum; $D_{b,\operatorname{prev}(s_1)} := 0$).
- $L_b \ge 0$: leftover unmet block volume slack.
- $S_{\ell,s,k} \in [0,1]$, $k = 1,\dots,K_{\ell}$: unit landing surplus slack for the $k$-th machine beyond capacity on landing $\ell$ in slot $s$ (only when $\omega^{\text{land}} > 0$).

**Objective.**

FHOPS maximizes weighted terminal production and subtracts penalty terms:

$$
\begin{aligned}
\max\; &\omega^{\text{prod}}\!\sum_{b\in\mathcal{B}}\sum_{r\in\mathcal{T}_b}\sum_{s\in\mathcal{S}} z_{r,b,s}
- \omega^{\text{prod}}\!\sum_{b\in\mathcal{B}} L_b \\
&- \omega^{\text{land}}\!\sum_{\ell\in\mathcal{L}}\sum_{s\in\mathcal{S}}\sum_{k=1}^{K_{\ell}} k\, S_{\ell,s,k} \\
&- \sum_{m\in\mathcal{M}}\sum_{s\in\mathcal{S}}\sum_{b'\ne b}
\left(\omega^{\text{mob}}\,\delta_{m,b',b} + \omega^{\text{trans}}\right) y_{m,b',b,s}.
\end{aligned}
$$

The last line charges every move of a machine: working a block other than its position, including the move from $b^{0}_m$ into the machine's first worked slot. Staying on a block costs nothing, and a machine without initial block ($m\notin\mathcal{M}^{0}$) moves for free into its first worked slot.

For blocks without terminal roles ($\mathcal{T}_b=\emptyset$, in particular blocks outside $\mathcal{B}^{\text{seq}}$) the production reward and the block balance use the machine-level sum $\sum_{m}\sum_{s} p_{m,b,s}$ in place of $\sum_{r\in\mathcal{T}_b}\sum_s z_{r,b,s}$.

**Earliness tie-break (optional; default in rolling-horizon windows).** OBJ does not depend on when work is done inside the horizon, so plans that shift production between slots tie. In a rolling-horizon window, a tied optimum may defer work past the lock span and lock idle days. With the earliness option, a second stage maximizes the production-weighted earliness

$$
E=\sum_{s\in\mathcal{S}} w_s \sum_{m\in\mathcal{M}}\sum_{b\in\mathcal{B}} p_{m,b,s},
\qquad w_s=\frac{|\mathcal{S}|-k_s}{|\mathcal{S}|},
$$

where $k_s\in\{0,\dots,|\mathcal{S}|-1\}$ is the position of slot $s$ in the slot order. This stage keeps every constraint above and adds $\text{OBJ}\ge z_1-\tau$, where $z_1$ is the OBJ value of the stage-1 solution and $\tau=10^{-6}\max(1,|z_1|)$. Stage 2 is warm-started from the stage-1 solution, so its returned plan has $\text{OBJ}\ge z_1-\tau$. If stage 1 is optimal, the returned plan is therefore optimal for OBJ within $\tau$, which is 100 times tighter than HiGHS's default relative MIP gap ($10^{-4}$). The reported objective is OBJ; $E$ is reported separately. A single weighted objective $\text{OBJ}+\varepsilon E$ is not used, for two reasons. First, production is continuous and the data are arbitrary reals, so no data-independent $\varepsilon>0$ is guaranteed to stay below the smallest positive OBJ difference between plans: for any $\varepsilon$ there are data for which the weighted optimum is not OBJ-optimal. Second, an $\varepsilon$ small enough to be harmless in practice ($\varepsilon E\ll 10^{-4}|z_1|$) is below the solver's relative gap, so the solver would stop before it acts on the tie-break. The cost is a second solve. Rolling-horizon MILP windows enable the option by default, except windows whose lock span covers the whole window. Standalone solves (`fhops solve-mip-operational`, `solve_operational_milp`) do not enable it by default, because the published single-horizon optimum and its solve time stay unchanged; `--earliness` or `earliness=True` turns it on.

**Constraints.**

Machine assignment feasibility:

$$
\sum_{b\in\mathcal{B}} x_{m,b,s} \le A_{m,s}
\qquad \forall m\in\mathcal{M},\; s\in\mathcal{S}.
$$

Role compatibility (machines can only work roles allowed by the block's assigned harvest system):

$$
x_{m,b,s}=0 \quad \text{if } b\in\mathcal{B}^{\text{seq}} \text{ and role}(m)\notin\mathcal{R}_b.
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

Machine positions and moves (each machine's position is a unit flow through one layer per slot; idle slots keep the position):

$$
\pi_{m,b,\operatorname{prev}(s)} = \eta_{m,b,s} + \sum_{b''\ne b} y_{m,b,b'',s}
\qquad \forall m\in\mathcal{M},\; b\in\mathcal{B},\; s\in\mathcal{S},
$$

$$
\nu_{m,\operatorname{prev}(s)} = \nu_{m,s} + \sum_{b\in\mathcal{B}} \phi_{m,b,s}
\qquad \forall m\in\mathcal{M}\setminus\mathcal{M}^{0},\; s\in\mathcal{S},
$$

$$
\sum_{b'\ne b} y_{m,b',b,s} + \phi_{m,b,s} \;\le\; x_{m,b,s} \;\le\; \pi_{m,b,s}
\qquad \forall m\in\mathcal{M},\; b\in\mathcal{B},\; s\in\mathcal{S}.
$$

A position changes only into a worked block, and working block $b$ puts the whole unit of flow at $b$. For binary $x$, every path of a decomposition of the flow therefore follows the machine's true position sequence, so $y_{m,b',b,s}=1$ exactly when machine $m$ works $b$ in slot $s$ and its last worked block before $s$ (or $b^{0}_m$) is $b'\ne b$, also when idle slots lie in between; all other $y$ are 0. The move term of the objective is thus exact and equals the mobilization and transition accounting of the heuristics and of the playback KPIs. The implementation builds the network only for machines that can incur a positive move cost and only for the slots in which the machine can work (other slots keep its position), starting arcs only at positions reachable before the slot; when all move costs $c_{m,b',b}$ of a machine are equal, the arcs $y_{m,b',b,s}$ are replaced by arcs to and from one hub node per slot, an equivalent network with $O(|\mathcal{B}|)$ instead of $O(|\mathcal{B}|^2)$ arcs.

Staged inventory start and balance per upstream role (each downstream role consumes its own output from the staged output of **every** upstream role, so a role with several upstream roles can only process what each of them has staged):

$$
I^{\text{start}}_{u,b,s}=
\begin{cases}
\bar{I}_{u,b}, & s = s_1\\
I_{u,b,\operatorname{prev}(s)}, & \text{otherwise}
\end{cases}
\qquad \forall (u,b)\in\mathcal{P}^{\text{stg}}, s,
$$

$$
I_{u,b,s}=I^{\text{start}}_{u,b,s}+z_{u,b,s}-\sum_{r\in\mathcal{N}_{u,b}} z_{r,b,s}
\qquad \forall (u,b)\in\mathcal{P}^{\text{stg}}, s,
$$

$$
\sum_{r\in\mathcal{N}_{u,b}} z_{r,b,s} \le I^{\text{start}}_{u,b,s}
\qquad \forall (u,b)\in\mathcal{P}^{\text{stg}}, s.
$$

For a linear chain ($|\mathcal{U}_{r,b}|=|\mathcal{N}_{u,b}|=1$) these are the v1.0.0 inventory equations of the downstream role. The downstream roles of a fork ($|\mathcal{N}_{u,b}|>1$) split the staged output of $u$: each unit is consumed by one of them. A join ($|\mathcal{U}_{r,b}|>1$) consumes each unit of its output from the pool of every upstream role. Hence, without carried-in staged volume, a fork that joins again (a diamond $u\to\{r_1,r_2\}\to t$) delivers at most half of the output of $u$, i.e. at most $W_b/2$.

Activation (production gating):

$$
z_{r,b,s} \le Q_{r,b}\,g_{r,b,s},
\qquad
g_{r,b,s} \le \sum_{m\in\mathcal{M}(r)} x_{m,b,s},
\qquad
\sum_{m\in\mathcal{M}(r)\setminus\mathcal{K}_{b,s}} x_{m,b,s} \le |\mathcal{M}(r)\setminus\mathcal{K}_{b,s}|\, g_{r,b,s}
\qquad \forall (r,b)\in\mathcal{P}^{\text{act}}, s.
$$

An assigned unlocked machine activates its role; a machine locked to the block may stay idle ($x=1$, $p=0$) without activating it, so a lock never forces production that the staged volumes cannot support.

Head start (with $I_{u,b,\operatorname{prev}(s_1)} := \bar{I}_{u,b}$):

$$
I_{u,b,\operatorname{prev}(s)} \ge B_{r,b}\,\left(g_{r,b,s}-h_{r,b,s}\right)
\qquad \forall (r,b)\in\mathcal{P}^{\text{hs}},\; u\in\mathcal{U}_{r,b},\; s,
$$

$$
\sum_{s'\prec s} z_{u,b,s'} \ge R^{0}_{u,b}\,h_{r,b,s}
\qquad \forall (r,b)\in\mathcal{P}^{\text{hs}},\; u\in\mathcal{U}_{r,b},\; s.
$$

Loader truckload threshold: a producing loader needs one truckload, or the whole remaining block volume when it is smaller, staged by every upstream role at the start of the slot,

$$
I_{u,b,\operatorname{prev}(s)} \ge \min\!\left(q^{\text{batch}}_{b},\; W_b - D_{b,\operatorname{prev}(s)}\right) g_{r,b,s}
\qquad \forall (r,b)\in\mathcal{P}^{\text{thr}},\; u\in\mathcal{U}_{r,b},\; s,
$$

linearized exactly as follows (all coefficients are data; $W_b - D_{b,\operatorname{prev}(s)} \in [0, W_b]$):

$$
\begin{aligned}
&I_{u,b,\operatorname{prev}(s)} \ge q^{\text{batch}}_{b}\, g_{r,b,s}
&& \text{if } W_b > q^{\text{batch}}_b,\ s\notin\mathcal{S}^{\text{tail}}_b,\\
&I_{u,b,\operatorname{prev}(s)} + D_{b,\operatorname{prev}(s)} \ge W_b\, g_{r,b,s}
&& \text{if } W_b \le q^{\text{batch}}_b,\\
&I_{u,b,\operatorname{prev}(s)} \ge q^{\text{batch}}_{b}\,(g_{r,b,s}-\lambda_{b,s}),\quad
I_{u,b,\operatorname{prev}(s)} + D_{b,\operatorname{prev}(s)} \ge q^{\text{batch}}_{b}\, g_{r,b,s} + (W_b - q^{\text{batch}}_{b})\,\lambda_{b,s}
&& \text{if } s\in\mathcal{S}^{\text{tail}}_b,
\end{aligned}
$$

$$
D_{b,\operatorname{prev}(s)} \ge (W_b - q^{\text{batch}}_{b})\,\lambda_{b,s},
\qquad
\lambda_{b,s} \ge \lambda_{b,\operatorname{prev}(s)}
\qquad \forall s\in\mathcal{S}^{\text{tail}}_b \ (\operatorname{prev}(s)\in\mathcal{S}^{\text{tail}}_b \text{ for the second}).
$$

$\lambda_{b,s}=1$ is only possible once at most one truckload remains; it then relaxes the threshold to the remaining volume. Outside $\mathcal{S}^{\text{tail}}_b$ the remaining volume provably exceeds a truckload, so no binary is needed there.

Block completion balance with leftover slack:

$$
\sum_{r\in\mathcal{T}_b}\sum_{s\in\mathcal{S}} z_{r,b,s} + L_b = W_b
\qquad \forall b\in\mathcal{B}.
$$

Remaining role output (no role can handle more wood than the block still holds):

$$
\sum_{s\in\mathcal{S}} z_{r,b,s} \le R_{r,b}
\qquad \forall b\in\mathcal{B}^{\text{seq}},\; r\in\mathcal{R}_b,
\qquad
z_{r,b,s} + D_{b,s} \le W_b
\qquad \forall (r,b)\in\mathcal{P}^{\text{cap}},\; s.
$$

Locked assignments (a lock without a shift label pins every available shift of its day; a lock with a shift label pins only that slot):

$$
x_{m_k,b,s} = \chi_k\,A_{m_k,s}\,\mathbf{1}[b=b_k]
\qquad \forall k\in\mathcal{K},\; s\in\mathcal{S}_k,\; b\in\mathcal{B},
$$

where $\chi_k=0$ when the lock contradicts the model (day outside the block window, or a machine whose role is not in the block's harvest system) and $\chi_k=1$ otherwise. Such locks are rejected by scenario validation; a lock that still reaches the model pins the machine to idle and is reported as a warning instead of making the model infeasible. A second lock on an already locked machine slot is ignored with a warning.
Landing capacity per shift slot, the machines working a landing's blocks concurrently:

$$
\sum_{b:\,\ell(b)=\ell}\sum_{m\in\mathcal{M}} x_{m,b,s}
\le
\begin{cases}
\max\{C_{\ell},\, N^{\text{lock}}_{\ell,s}\} & \text{if } \omega^{\text{land}} = 0,\\
C_{\ell} + \sum_{k=1}^{K_{\ell}} S_{\ell,s,k} & \text{if } \omega^{\text{land}} > 0,
\end{cases}
\qquad \forall \ell\in\mathcal{L},\; s\in\mathcal{S},
$$

where $N^{\text{lock}}_{\ell,s} = \sum_{b:\,\ell(b)=\ell}|\mathcal{K}_{b,s}|$ is the number of machines locked to the landing's blocks in slot $s$. With $\omega^{\text{land}}=0$ the capacity is hard; a slot in which locks alone exceed it keeps the locked machines, admits no other machine, and is reported as a warning (the heuristics charge the same unavoidable overload). With $\omega^{\text{land}}>0$ the marginal price $k\,\omega^{\text{land}}$ of the slack pieces increases, so an optimal solution uses $S_{\ell,s,1},\dots,S_{\ell,s,e}$ for $e$ machines beyond capacity and pays $\omega^{\text{land}}\,e(e+1)/2$: the $k$-th machine beyond capacity in a slot costs $k\,\omega^{\text{land}}$, as in the heuristics' evaluation.

Domain restrictions:

$$
x, g, h, \lambda \in \{0,1\},\quad p,z,y,\eta,\phi,\nu,I^{\text{start}},I,L \ge 0,\quad S \in [0,1].
$$

**Initial state defaults.** Without `Scenario.initial_state` and `Scenario.locked_assignments` ($\bar{I}\equiv 0$; $R^{0}_{r,b}= R_{r,b}= W_b$; $\mathcal{M}^{0}=\mathcal{K}=\emptyset$) the initial-state and lock terms vanish.

**Changes from FHOPS v1.0.0 (1.0.1).** The following corrections make every MILP plan physically feasible and replayable by the playback sequencing tracker without violations: (i) the remaining-output cap applies to every role with $R_{r,b}=\min(R^{0}_{r,b},W_b)$ ($W_b$ by default), complemented by the per-slot cap $z_{r,b,s}+D_{b,s}\le W_b$ where the flow balances do not imply it (v1.0.0 let upstream roles output more volume than the block holds and used that volume to meet head-start and loader thresholds); (ii) the head-start constraint is waived through $h_{r,b,s}$ once every upstream role has output its carried-in remaining volume, so blocks smaller than a buffer can still be finished; (iii) the loader threshold is $\min(q^{\text{batch}}_b, W_b - D_{b,\operatorname{prev}(s)})$, the volume still to deliver at the start of the slot (v1.0.0 always required a full truckload), so the last partial truckload of a block can be loaded; (iv) staged inventories are kept per upstream role, $I_{u,b,s}$ (v1.0.0 kept one inventory per downstream role fed by the sum of its upstream roles' outputs, so a role with several upstream roles could process wood that only one of them had handled); (v) the activation binary $g_{r,b,s}$ gates production only and machines locked to a block may stay idle, so locks (new in 1.0.1) never make the model infeasible; contradictory locks are pinned to idle and reported; (vi) blocks without a harvest system ($\mathcal{B}\setminus\mathcal{B}^{\text{seq}}$) have no role obligations, as documented in the data contract (v1.0.0 applied the registry's default system to them); (vii) timeline blackouts, which v1.0.0 enforced only in the heuristics, set $A_{m,s}=0$ in every slot of a blackout day for every machine; (viii) landing capacity counts the machines on a landing per shift slot and is hard when $\omega^{\text{land}}=0$, as in the heuristics (v1.0.0 counted machine-shifts per day, $\sum_{\sigma} x_{m,b,(d,\sigma)} \le C_{\ell} + S_{\ell,d}$, with a slack that was free at the default $\omega^{\text{land}}=0$, so the capacity did not bind; on single-shift scenarios the per-slot and per-day counts coincide); (ix) a move is charged when a machine works a block other than its position, its last worked block or $b^{0}_m$, through the position network above: staying on a block costs nothing (v1.0.0 also charged $\omega^{\text{trans}}$ for consecutive slots on the same block), and a move across idle slots, or from $b^{0}_m$ into a first worked slot after $s_1$, is charged (v1.0.0 linked only consecutive slots through binaries $y_{m,b',b,s}\ge x_{m,b',\operatorname{prev}(s)}+x_{m,b,s}-1$, so idling one slot avoided the move cost that the heuristics and the KPIs charge); (x) the loader batching variables of v1.0.0 ($z_{r,b,s}=q^{\text{batch}}_{b}n_{r,b,s}+u_{r,b,s}$ with $n_{r,b,s}\in\mathbb{Z}_{\ge0}$, $0\le u_{r,b,s}\le q^{\text{batch}}_{b}$) were removed because every $z_{r,b,s}\ge 0$ satisfies them; the truckload rule is the loader threshold above. Playback, the heuristics, and the rolling-horizon carry-forward apply the same rules: staged output is available from the next shift slot, buffers and truckload thresholds are staged volume at the start of the slot, and production is capped by $R_{r,b}$ and by the volume the block still holds. For linear harvest systems without loaders, without locks, and with no (or a consistent) initial state, (iii)–(v) leave the equations unchanged apart from indexing the staged inventory by the upstream instead of the downstream role.

**Implementation mapping (equation blocks to code).**

- Machine capacity and availability: `model.machine_capacity` (`machine_capacity_rule`; $A_{m,s}$ from the calendars and `bundle.blackout_slots`, built by `build_blackout_slots(...)` and shared with the heuristics)
- Role compatibility: `model.role_compatibility` (`role_compatibility_rule`; skipped for `bundle.unsequenced_blocks`)
- Production-assignment coupling: `model.production_cap` (`prod_cap_rule`)
- Block windows: `model.block_windows` (`window_rule`)
- Role aggregation: `model.role_prod_balance` (`role_prod_balance_rule`)
- Machine positions and moves: `model.position_balance` ($\eta$ = `model.stay`, $y$ = `model.y` or the hub arcs `model.depart`/`model.arrive` with `model.hub_balance` for machines with equal move costs), `model.unplaced_balance` ($\phi$ = `model.first`, $\nu$ = `model.unplaced`), `model.move_requires_work`, `model.work_sets_position`
- Inventory dynamics and guards: `model.inventory_start_eq` (indexed by upstream role-block pairs `model.InventoryPairs`; first slot uses $\bar{I}_{u,b}$ from `bundle.initial_staged_inventory`), `model.inventory_balance`, `model.inventory_guard`
- Activation and head start: `model.activation_prod`, `model.role_active_upper` (locked machines excluded), `model.role_active_lower`, `model.head_start` (one row per upstream role); buffer waiver `model.upstream_done_link` (cumulative output `model.role_cumulative_eq`); $B_{r,b}$ from `headstart_buffer_volumes(...)` in `fhops.model.milp.data`
- Loader threshold: `model.loader_threshold`, `model.loader_threshold_tail`, `model.loader_tail_reached`, `model.loader_tail_monotone` ($\lambda$ = `model.loader_tail`; $D_{b,s}$ from `model.role_cumulative` of the terminal roles)
- Block balance with leftovers: `model.block_balance` (`block_balance_rule`) + `model.leftover`
- Remaining role output: `model.role_remaining_cap` (from `bundle.initial_role_remaining`, capped at $W_b$), per-slot cap `model.role_slot_remaining`
- Locked assignments: `model.locked_assignment` (from `bundle.locked_assignments`, resolved by `resolve_locked_slots(...)` in `fhops.model.milp.data`; warnings in the solve result)
- Landing capacity per shift slot: `model.landing_capacity` (`landing_capacity_rule`, indexed by landing and slot; locked overloads from `_landing_slot_capacities`) + `model.landing_surplus` (unit pieces `model.LandingSurplusIndex`, only when $\omega^{\text{land}}>0$)
- Objective assembly: `model.objective` and objective-term construction around `prod_weight`, `landing_weight`, `mobilisation_weight`, `transition_weight` (move costs $c_{m,b',b}$; $b^{0}_m$ from `bundle.initial_machine_block`)
- Earliness tie-break: `earliness_expression(...)` in `fhops.model.milp.operational` ($E$); second stage `_solve_earliness_stage(...)` in `fhops.model.milp.driver` (`model.earliness_floor`, `model.earliness_objective`; `solve_operational_milp(..., earliness=True)`, result key `earliness`)
- Data/parameter normalization: `build_operational_bundle(...)` in `fhops.model.milp.data` (flattens `Scenario.initial_state` and `Scenario.locked_assignments` into the bundle)

This formulation is the canonical mathematical reference for FHOPS operational MILP documentation and thesis-level reporting.
