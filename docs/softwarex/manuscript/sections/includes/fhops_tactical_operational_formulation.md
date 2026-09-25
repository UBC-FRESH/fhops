FHOPS' TOPM-inspired tactical--operational solver is formulated on an aggregate period grid and chooses harvest areas by planning unit, harvest system, and period while carrying products through transport, facility consumption, inventory, outside purchases, and optional infrastructure/fleet modules. The equations below mirror the implemented Pyomo model in `fhops.model.milp.tactical_operational.build_tactical_operational_model` and the validated contract in `fhops.planning.tactical_operational.models.TacticalOperationalScenario`.

**Problem statement.**
Given planning units, period calendars, product yields, harvest-system options, facility demand envelopes, transport arcs, external supply, and optional road/silviculture/fleet modules, choose harvest quantities and downstream flows that satisfy demand and feasibility constraints at minimum discounted delivered cost, or maximize discounted profit/NPV when product values are supplied.

**Sets and indices.**

- $b \in \mathcal{B}$: planning units/blocks.
- $o \in \mathcal{O}$: eligible block $\times$ system $\times$ period harvest options.
- $t \in \mathcal{T}$: ordered tactical--operational periods.
- $p \in \mathcal{P}$: products/species-grade classes.
- $a \in \mathcal{A}$: product transport arcs.
- $u \in \mathcal{U}$: external supply options, indexed by source/destination/product/period.
- $(f,p,t) \in \mathcal{F}$: facility/product/period balance keys.
- $r \in \mathcal{R}$: optional road projects.
- $q \in \mathcal{Q}$: optional silviculture transitions.
- $e \in \mathcal{E}$: optional fleet acquisition options.

**Parameters.**

- $A_b$: operable area of planning unit $b$ (ha).
- $L_o,U_o$: minimum/maximum active area for option $o$ (ha).
- $Y_{b,p}$: product yield for block $b$ and product $p$ (m$^3$/ha).
- $K_o$: optional total production capacity for option $o$ (m$^3$/period).
- $K^{fleet}_{s,t}$: base fleet capacity for system $s$ in period $t$ (m$^3$).
- $F_o,c_o$: fixed cost and variable cost per m$^3$ for option $o$.
- $c_a,c_u$: transport cost per m$^3$ on arc $a$ and delivered purchase cost per m$^3$ for supply $u$.
- $D^{min}_{f,p,t},D^{target}_{f,p,t},D^{max}_{f,p,t}$: facility demand envelope (m$^3$).
- $v_{f,p,t}$: optional delivered product value per m$^3$ for profit objectives.
- $d_t$: discount factor for period $t$.
- $I^0_{f,p}$: opening facility inventory (m$^3$).
- $C_a,C_r$: transport arc and active-road capacity (m$^3$/period).
- $B_r,M_r$: road build cost and maintenance cost per active period.
- $c_q$: silviculture cost per ha for transition $q$.
- $N^{max}_e,K_e,C^{fleet}_e$: maximum units, added capacity per period, and purchase cost for fleet option $e$.

**Decision variables.**

- $H_o \ge 0$: area harvested under option $o$ (ha).
- $Z_o \in \{0,1\}$: activation indicator for option $o$.
- $V_{o,p} \ge 0$: product volume produced by option $o$ (m$^3$).
- $F_a \ge 0$: product flow on transport arc $a$ (m$^3$).
- $P_u \ge 0$: external purchase quantity for supply option $u$ (m$^3$).
- $C_{f,p,t} \ge 0$: facility consumption/demand fulfillment (m$^3$).
- $I_{f,p,t} \ge 0$: closing facility inventory (m$^3$).
- $R^B_{r,t},R^A_{r,t} \in \{0,1\}$: road build and available indicators when roads are enabled.
- $Q_{q,t} \ge 0$: silviculture activity area scheduled for transition $q$ in period $t$.
- $N_e \in \mathbb{Z}_{\ge 0}$: units purchased for fleet option $e$.

**Harvest quantity modes.**

All modes enforce the physical upper bound:

$$
H_o \le U_o Z_o \qquad \forall o\in\mathcal{O}.
$$

Semi-continuous mode (the default) additionally enforces option-specific minimum active area:

$$
L_o Z_o \le H_o \qquad \forall o\in\mathcal{O}.
$$

Continuous mode omits that lower bound. Whole-block mode forces full operable area when active:

$$
H_o = A_{b(o)} Z_o \qquad \forall o\in\mathcal{O}.
$$

**Core constraints.**

Product conversion and option productivity:

$$
V_{o,p}=Y_{b(o),p}H_o \qquad \forall o,p,
$$

$$
\sum_p Y_{b(o),p}H_o \le K_o Z_o \qquad \forall o \text{ with } K_o \text{ declared}.
$$

Block area balance:

$$
\sum_{o:b(o)=b} H_o \le A_b \qquad \forall b\in\mathcal{B}.
$$

Fleet capacity with optional acquisition:

$$
\sum_{o:s(o)=s,t(o)=t}\sum_p Y_{b(o),p}H_o
\le K^{fleet}_{s,t} + \sum_{e:s(e)=s,\ \tau(e)\le t<\tau(e)+L_e} K_e N_e
\qquad \forall s,t,
$$

where $\tau(e)$ is the purchase period sequence and $L_e$ the economic life in periods. Purchases are bounded by $0\le N_e\le N^{max}_e$.

Flow supply and arc capacity:

$$
\sum_{a\in out(b,p,t)}F_a \le \sum_{o:b(o)=b,t(o)=t}V_{o,p}
\qquad \forall b,p,t,
$$

$$
F_a \le C_a \qquad \forall a\in\mathcal{A}\text{ with declared capacity}.
$$

External purchase bounds:

$$
P^{min}_u \le P_u \le P^{max}_u \qquad \forall u\in\mathcal{U}.
$$

Facility consumption bounds and target mode:

$$
C_{f,p,t} \ge D^{min}_{f,p,t},\qquad
C_{f,p,t} \le D^{max}_{f,p,t}\text{ when declared},
$$

$$
C_{f,p,t}=D^{target}_{f,p,t}\text{ when target basis is selected and a target exists}.
$$

Facility inventory balance:

$$
I_{f,p,t}=I_{f,p,t-1}+\sum_{a\in in(f,p,t)}F_a+\sum_{u\in in(f,p,t)}P_u-C_{f,p,t}
\qquad \forall (f,p,t),
$$

with $I_{f,p,0}=I^0_{f,p}$.

**Optional road module.**

Road build timing, one-time build, availability, dependencies, block access, and active capacity are represented as:

$$
R^A_{r,t}=\sum_{t'\le t}R^B_{r,t'},\qquad
\sum_t R^B_{r,t}\le 1,
$$

$$
R^A_{r,t}\le R^A_{\rho(r),t}\quad\text{for dependency }\rho,
$$

$$
Z_o \le \sum_{r\in access(b(o))}R^A_{r,t(o)},
$$

$$
\sum_{o:t(o)=t,\ access(b(o))\ne\varnothing}\sum_pY_{b(o),p}H_o
\le \sum_r C_rR^A_{r,t}.
$$

Road costs enter the objective as $\sum_{r,t}d_t(B_rR^B_{r,t}+M_rR^A_{r,t})$.

**Optional silviculture module.**

For each required transition $q$ triggered by block/system harvest:

$$
\sum_{t\ge earliest(q)}Q_{q,t}=\sum_{o:b(o)=b(q),s(o)=s(q)}H_o.
$$

Transition area carries discounted cost $\sum_{q,t}d_t c_q Q_{q,t}$.

**Objective profiles.**

Default minimum discounted delivered cost:

$$
\min\; \sum_o d_{t(o)}(F_oZ_o+c_o\sum_pY_{b(o),p}H_o)
+\sum_a d_{t(a)}c_aF_a
+\sum_u d_{t(u)}c_uP_u
+\text{road, silviculture, and fleet costs}.
$$

When demand rows include value per m$^3$, `max_discounted_profit` maximizes

$$
\sum_{f,p,t}d_tv_{f,p,t}C_{f,p,t}-\text{Cost}.
$$

`max_npv` additionally adds declared final-period terminal inventory value:

$$
\sum_{f,p}d_{t_{final}}v^{terminal}_{f,p}I_{f,p,t_{final}}.
$$

**Implementation mapping (equation blocks to code).**

| Equation/constraint block | Pyomo component / helper | Data provenance |
|---|---|---|
| Harvest upper bound | `model.harvest_upper` | `HarvestSystemOption.max_area_ha` and block operable area |
| Semi-continuous minimum cut | `model.harvest_lower` | `HarvestSystemOption.min_area_ha` |
| Whole-block mode | `model.whole_block` | `PlanningUnit.operable_area_ha` |
| Productivity cap | `model.productivity_cap` | `HarvestSystemOption.productivity_m3_per_period` |
| Product conversion | `model.product_conversion` | `PlanningUnit.product_yields_m3_per_ha` |
| Block area balance | `model.block_area` | `PlanningUnit.operable_area_ha` |
| Fleet capacity and acquisition | `model.fleet_capacity`, `model.fleet_units`, `model.fleet_option_upper` | `FleetCapacity` and `FleetOption` |
| Flow supply | `model.flow_supply` | `TransportArc` and `product_volume` |
| Arc capacity | `model.arc_capacity` | `TransportArc.capacity_m3` |
| Purchase bounds | `model.purchase_lower`, `model.purchase_upper` | `ExternalSupply` |
| Consumption bounds/targets | `model.consumption_lower`, `model.consumption_target`, `model.consumption_upper` | `FacilityDemand` |
| Inventory balance | `model.inventory_balance` | `InitialInventory`, flows, purchases, consumption |
| Road build/availability/dependencies/access/capacity | `model.road_build`, `model.road_available`, `model.road_build_timing`, `model.road_availability`, `model.road_build_once`, `model.road_dependencies`, `model.road_access`, `model.road_capacity` | `RoadProject`, `RoadDependency`, `BlockRoadAccess` |
| Silviculture fulfillment | `model.silviculture_area`, `model.silviculture_fulfillment` | `SilvicultureTransition` |
| Objective profiles | `model.objective` | `Economics.objective_profile`, costs, values, discount factors |
| Bundle replay and telemetry | `tactical_bundle_to_dict(...)`, `tactical_bundle_from_dict(...)`, `solve_tactical_operational_milp(...)` | `fhops.model.milp.tactical_operational` |

This formulation is the canonical mathematical reference for the FHOPS tactical--operational MILP. Generated TeX/RST outputs are derived artifacts and should not be edited directly.
