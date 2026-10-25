FHOPS' optional log-hauling layer implements the two-phase operational decomposition of Ghotb (2023): a monthly daily-flow mixed-integer program (Phase I) and a one-day continuous-time truck/loader scheduling mixed-integer program (Phase II), with a simulated-annealing solution approach (Phase III) for large days. The equations below mirror `fhops.hauling.flow`, `fhops.hauling.schedule`, and `fhops.hauling.heuristic`, and the validated contract in `fhops.hauling.contract.HaulingConfig`.

**Problem statement.**
Given blocks, log sorts, contractors, a heterogeneous truck fleet, a central depot, sort yards, loader locations, supply, demand, and travel times, choose daily sorted/unsorted flows and yard inventories (Phase I), then assign every truckload to a compatible truck and contractor and schedule trucks and loaders with continuous time, synchronization, and overtime (Phase II). Exact scheduling is limited to small and medium days; Phase III searches route permutations with an SPT decoder for larger days.

## Phase I: monthly daily flows

**Sets and indices.**

- $b \in \mathcal{B}$: blocks.
- $y \in \mathcal{Y}$: sort yards.
- $s \in \mathcal{S}$: log sorts.
- $r \in \mathcal{R}$: truck types.
- $o \in \mathcal{O}$: contractors.
- $t \in \mathcal{T}$: days in the hauling horizon.

**Parameters.**

- $TT_{byr}$: round-trip travel time including loading and unloading (hours).
- $TC_r$: transport cost per truck-hour.
- $SW_{bs},SC_{bs}$: sorted/unsorted supply (m$^3$).
- $Q_r$: truck capacity (m$^3$).
- $\alpha_{bo},\beta_{ro}$: contractor serves block, contractor owns truck type.
- $\gamma_r,\epsilon_r$: truck type may carry sorted/unsorted.
- $N_{ro}$: number of trucks of type $r$ owned by contractor $o$.
- $\phi_o$: preferred daily truckloads.
- $D_{yst}$: demand (m$^3$).
- $SC_y,CW_y,CC_y,CY_y$: unsorted storage, sorted processing, unsorted processing, and total processing capacities.
- $T^{max}$: regular daily driving minutes.
- $P$: roadside-inventory penalty per m$^3$.

**Decision variables.**

- $vw_{bysort},vc_{bysort} \ge 0$: sorted/unsorted volume moved.
- $nw_{bysort} \in \mathbb{Z}_{\ge 0}$: sorted truckloads (one sort per load).
- $nc_{byort} \in \mathbb{Z}_{\ge 0}$: unsorted truckloads (may mix sorts).
- $ibw_{bs},ibc_{bs} \ge 0$: roadside inventory at the horizon end.
- $iw_{yst},ic_{yst} \ge 0$: water and unsorted yard inventory.
- $pv_{yst} \ge 0$: unsorted volume processed.
- $u_o \ge 0$: maximum daily workload deviation.

**Objectives.**

$$
\min Z_1 = \sum_{t,b,y,r,o}\left(\sum_s nw_{bysort}+nc_{byort}\right)TC_rTT_{byr}
+ \sum_{b,s}P(ibw_{bs}+ibc_{bs}),
$$

$$
\min Z_2 = \sum_o u_o.
$$

**Core constraints.**

Supply balance:

$$
\sum_{t,y,r,o} vw_{bysort}+ibw_{bs}=SW_{bs}\quad\forall b,s,
\qquad
\sum_{t,y,r,o} vc_{bysort}+ibc_{bs}=SC_{bs}\quad\forall b,s.
$$

Compatibility is enforced by omitting infeasible variables. A sorted load carries one sort; an unsorted load may mix sorts:

$$
(nw_{bysort}-1)Q_r \le vw_{bysort}\le nw_{bysort}Q_r,
$$

$$
(nc_{byort}-1)Q_r \le \sum_s vc_{bysort}\le nc_{byort}Q_r.
$$

Workload deviation:

$$
\left|\sum_{b,y,r}\left(nc_{byort}+\sum_s nw_{bysort}\right)-\phi_o\right|\le u_o
\quad\forall o,t.
$$

Yard inventory:

$$
ic_{yst}=ic_{ys,t-1}+\sum_{b,o,r}vc_{bysort}-pv_{yst},
$$

$$
iw_{yst}=iw_{ys,t-1}+\sum_{b,o,r}vw_{bysort}+pv_{yst}-D_{yst}.
$$

Yard capacities:

$$
\sum_s ic_{yst}\le SC_y,\qquad
\sum_{b,o,r,s}vw_{bysort}\le CW_y,
$$

$$
\sum_s pv_{yst}\le CC_y,\qquad
\sum_{b,o,r,s}vw_{bysort}+\sum_s pv_{yst}\le CY_y.
$$

Fleet capacity:

$$
\sum_{b,y,s}nw_{bysort}TT_{byr}+\sum_{b,y}nc_{byort}TT_{byr}
\le N_{ro}T^{max}\quad\forall o,r,t.
$$

**Goal programming.**

Solve the cost-only model for $Goal_1$. Use the contractor's supplied $\phi_o$ or derive it from the cost plan; set $Goal_2=0$. Minimize normalized positive deviations:

$$
\min\; w_1\frac{dev^+_1}{\max(|Goal_1|,1)}
+ w_2\frac{dev^+_2}{\max(\sum_o\phi_o,1)},
$$

$$
Z_1-dev^+_1\le Goal_1,\qquad Z_2-dev^+_2\le Goal_2,\qquad dev^+_1,dev^+_2\ge 0.
$$

## Phase II: daily truck and loader scheduling

**Sets and indices.**

- $l \in \mathcal{L}$: individual truckloads from Phase I.
- $v \in \mathcal{V}$: enabled trucks; $k(v)$ is the truck type, $o(v)$ the contractor.
- $p \in \mathcal{P}^L$: pickup loaders; $d \in \mathcal{D}^L$: delivery loaders.
- $i,j \in \mathcal{L}$: load pairs.

**Parameters.**

- $b(l),y(l)$: pickup block and delivery yard.
- $Q_l$: load volume (nominal truck capacity).
- $S_l$: loading/unloading service time at the assigned loader.
- $T_{b,y}$: loaded block-to-yard travel.
- $T_{y,b}$: empty yard-to-next-block travel.
- $T^{depot}_{b},T^{depot}_{y}$: depot legs.
- $FC_k,VC_k,OC_k$: fixed, variable per regular minute, and overtime per minute.
- $T^{reg},T^{ot}$: regular and maximum overtime minutes.

**Decision variables.**

- $z_{vl}\in\{0,1\}$: truck $v$ carries load $l$.
- $start_{vl},end_{vl},order_{vij}\in\{0,1\}$: route start, end, and precedence.
- $used_v\in\{0,1\}$: truck dispatched.
- $routepos_{vl}\ge 0$: MTZ position.
- $pick_{lp},del_{ld}\in\{0,1\}$: loader assignment.
- $pb_{ijp},db_{ijd}\in\{0,1\}$: loader precedence.
- $a^p_{vl},a^d_{vl}\ge 0$: truck arrival at pickup/delivery.
- $s^p_l,s^d_l\ge 0$: service start.
- $f^p_l,f^d_l\ge 0$: service finish.
- $ret_v,reg_v,ot_v\ge 0$: return, regular, and overtime minutes.

**Objective.**

$$
\min \sum_v FC_{k(v)}used_v+\sum_v VC_{k(v)}reg_v+\sum_v OC_{k(v)}ot_v.
$$

**Core constraints.**

Each load is assigned exactly once to a compatible truck:

$$
\sum_{v:o(v)=o(l),k(v)=k(l)}z_{vl}=1\quad\forall l.
$$

Route start/end and flow balance:

$$
\sum_l start_{vl}=used_v,\qquad \sum_l end_{vl}=used_v,
$$

$$
z_{vl}=start_{vl}+\sum_i order_{vil}
=end_{vl}+\sum_j order_{vlj}\quad\forall v,l.
$$

MTZ subtour elimination:

$$
routepos_{vj}\ge routepos_{vi}+1-M(1-order_{vij}).
$$

Each pickup/delivery load has one loader; a single binary per pair encodes the loader order and the no-overlap constraints enforce one direction:

$$
\sum_p pick_{lp}=1,\qquad \sum_d del_{ld}=1.
$$

Loader no-overlap (pickup shown; delivery analogous):

$$
s^p_i+S_i\le s^p_j+M(1-pb_{ijp})+M(2-pick_{ip}-pick_{jp}),
$$

$$
s^p_j+S_j\le s^p_i+M\,pb_{ijp}+M(2-pick_{ip}-pick_{jp}).
$$

Truck timing and synchronization:

$$
a^p_{vl}\ge T^{depot}_{b(l)}-M(1-start_{vl}),
$$

$$
a^p_{vj}\ge f^d_{vi}+T_{y(i),b(j)}-M(1-order_{vij}),
$$

$$
a^p_{vl}\le s^p_l+M(1-z_{vl}),
$$

$$
f^p_l=s^p_l+\sum_p pick_{lp}S_p,
$$

$$
a^d_{vl}\ge f^p_l+T_{b(l),y(l)}-M(1-z_{vl}),
$$

$$
a^d_{vl}\le s^d_l+M(1-z_{vl}),
$$

$$
f^d_l=s^d_l+\sum_d del_{ld}S_d.
$$

Return time and overtime:

$$
ret_v\ge f^d_l+T^{depot}_{y(l)}-M(1-end_{vl}),
\qquad
ret_v=reg_v+ot_v,
$$

$$
reg_v\le T^{reg},\qquad ot_v\le T^{ot}.
$$

The exact model treats the daily horizon as hard. The time-relaxation constant is $M=2T^{horizon}$, not the horizon itself; a horizon-sized $M$ can cut off feasible predecessors near the end of the day.

## Phase III: simulated annealing

A solution is a permutation of loads per truck. The decoder assigns each load to the fastest loader at its location, computes a no-wait forward pass for projected pickup/delivery arrivals, sorts each loader's loads by those arrivals (shortest processing time), and recomputes the earliest schedule for the resulting routes and loader orders.

Neighbourhoods are swap, reversion, and insertion. Insertion may move a load to another compatible truck. A worse solution is accepted with probability

$$
\Pr(\text{accept})=\exp\left(-\frac{\Delta}{T}\right),
$$

and the temperature cools geometrically, $T\leftarrow\alpha T$. The thesis Taguchi calibration selects $T_0=300$, $T_{min}=0.0005T_0$, $\alpha=0.95$, and 90 moves per temperature. These are configurable defaults.

The SA cost adds a soft penalty for minutes above $T^{reg}+T^{ot}$; the exact Phase II model keeps that limit hard. On the example day-1 case, Phase II and Phase III both reach the same objective, which is the parity check used in the test suite.

## Implementation notes and corrections

- Compatibility is enforced by index restriction, not a big-M.
- The absolute workload deviation is linearised with two inequalities.
- Goal deviations are non-negative continuous variables; the thesis and paper disagree on integrality.
- The thesis's one-direction loader-precedence equality would force a lexicographic order. It is omitted; a single precedence binary already encodes the two directions and the no-overlap constraints select one.
- The thesis's synchronization equations sum over all machines at a node; the implementation links the assigned truck and loader through a common service start and per-machine arrival times.
- The exact model requires one central depot and a depot leg for every used block/yard and truck type. Missing legs are named errors.
- The SA decoder assigns all loads at a location to the fastest loader; the exact MIP can search loader assignment.
