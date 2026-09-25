.. AUTO-GENERATED from fhops_tactical_operational_formulation.md -- do not edit directly.

FHOPS’ TOPM-inspired tactical–operational solver is formulated on an
aggregate period grid and chooses harvest areas by planning unit,
harvest system, and period while carrying products through transport,
facility consumption, inventory, outside purchases, and optional
infrastructure/fleet modules. The equations below mirror the implemented
Pyomo model in
``fhops.model.milp.tactical_operational.build_tactical_operational_model``
and the validated contract in
``fhops.planning.tactical_operational.models.TacticalOperationalScenario``.

**Problem statement.** Given planning units, period calendars, product
yields, harvest-system options, facility demand envelopes, transport
arcs, external supply, and optional road/silviculture/fleet modules,
choose harvest quantities and downstream flows that satisfy demand and
feasibility constraints at minimum discounted delivered cost, or
maximize discounted profit/NPV when product values are supplied.

**Sets and indices.**

- :math:`b \in \mathcal{B}`: planning units/blocks.
- :math:`o \in \mathcal{O}`: eligible block :math:`\times` system
  :math:`\times` period harvest options.
- :math:`t \in \mathcal{T}`: ordered tactical–operational periods.
- :math:`p \in \mathcal{P}`: products/species-grade classes.
- :math:`a \in \mathcal{A}`: product transport arcs.
- :math:`u \in \mathcal{U}`: external supply options, indexed by
  source/destination/product/period.
- :math:`(f,p,t) \in \mathcal{F}`: facility/product/period balance keys.
- :math:`r \in \mathcal{R}`: optional road projects.
- :math:`q \in \mathcal{Q}`: optional silviculture transitions.
- :math:`e \in \mathcal{E}`: optional fleet acquisition options.

**Parameters.**

- :math:`A_b`: operable area of planning unit :math:`b` (ha).
- :math:`L_o,U_o`: minimum/maximum active area for option :math:`o`
  (ha).
- :math:`Y_{b,p}`: product yield for block :math:`b` and product
  :math:`p` (m\ :math:`^3`/ha).
- :math:`K_o`: optional total production capacity for option :math:`o`
  (m\ :math:`^3`/period).
- :math:`K^{fleet}_{s,t}`: base fleet capacity for system :math:`s` in
  period :math:`t` (m\ :math:`^3`).
- :math:`F_o,c_o`: fixed cost and variable cost per m\ :math:`^3` for
  option :math:`o`.
- :math:`c_a,c_u`: transport cost per m\ :math:`^3` on arc :math:`a` and
  delivered purchase cost per m\ :math:`^3` for supply :math:`u`.
- :math:`D^{min}_{f,p,t},D^{target}_{f,p,t},D^{max}_{f,p,t}`: facility
  demand envelope (m\ :math:`^3`).
- :math:`v_{f,p,t}`: optional delivered product value per m\ :math:`^3`
  for profit objectives.
- :math:`d_t`: discount factor for period :math:`t`.
- :math:`I^0_{f,p}`: opening facility inventory (m\ :math:`^3`).
- :math:`C_a,C_r`: transport arc and active-road capacity
  (m\ :math:`^3`/period).
- :math:`B_r,M_r`: road build cost and maintenance cost per active
  period.
- :math:`c_q`: silviculture cost per ha for transition :math:`q`.
- :math:`N^{max}_e,K_e,C^{fleet}_e`: maximum units, added capacity per
  period, and purchase cost for fleet option :math:`e`.

**Decision variables.**

- :math:`H_o \ge 0`: area harvested under option :math:`o` (ha).
- :math:`Z_o \in \{0,1\}`: activation indicator for option :math:`o`.
- :math:`V_{o,p} \ge 0`: product volume produced by option :math:`o`
  (m\ :math:`^3`).
- :math:`F_a \ge 0`: product flow on transport arc :math:`a`
  (m\ :math:`^3`).
- :math:`P_u \ge 0`: external purchase quantity for supply option
  :math:`u` (m\ :math:`^3`).
- :math:`C_{f,p,t} \ge 0`: facility consumption/demand fulfillment
  (m\ :math:`^3`).
- :math:`I_{f,p,t} \ge 0`: closing facility inventory (m\ :math:`^3`).
- :math:`R^B_{r,t},R^A_{r,t} \in \{0,1\}`: road build and available
  indicators when roads are enabled.
- :math:`Q_{q,t} \ge 0`: silviculture activity area scheduled for
  transition :math:`q` in period :math:`t`.
- :math:`N_e \in \mathbb{Z}_{\ge 0}`: units purchased for fleet option
  :math:`e`.

**Harvest quantity modes.**

All modes enforce the physical upper bound:

.. math::


   H_o \le U_o Z_o \qquad \forall o\in\mathcal{O}.

Semi-continuous mode (the default) additionally enforces option-specific
minimum active area:

.. math::


   L_o Z_o \le H_o \qquad \forall o\in\mathcal{O}.

Continuous mode omits that lower bound. Whole-block mode forces full
operable area when active:

.. math::


   H_o = A_{b(o)} Z_o \qquad \forall o\in\mathcal{O}.

**Core constraints.**

Product conversion and option productivity:

.. math::


   V_{o,p}=Y_{b(o),p}H_o \qquad \forall o,p,

.. math::


   \sum_p Y_{b(o),p}H_o \le K_o Z_o \qquad \forall o \text{ with } K_o \text{ declared}.

Block area balance:

.. math::


   \sum_{o:b(o)=b} H_o \le A_b \qquad \forall b\in\mathcal{B}.

Fleet capacity with optional acquisition:

.. math::


   \sum_{o:s(o)=s,t(o)=t}\sum_p Y_{b(o),p}H_o
   \le K^{fleet}_{s,t} + \sum_{e:s(e)=s,\ \tau(e)\le t<\tau(e)+L_e} K_e N_e
   \qquad \forall s,t,

where :math:`\tau(e)` is the purchase period sequence and :math:`L_e`
the economic life in periods. Purchases are bounded by
:math:`0\le N_e\le N^{max}_e`.

Flow supply and arc capacity:

.. math::


   \sum_{a\in out(b,p,t)}F_a \le \sum_{o:b(o)=b,t(o)=t}V_{o,p}
   \qquad \forall b,p,t,

.. math::


   F_a \le C_a \qquad \forall a\in\mathcal{A}\text{ with declared capacity}.

External purchase bounds:

.. math::


   P^{min}_u \le P_u \le P^{max}_u \qquad \forall u\in\mathcal{U}.

Facility consumption bounds and target mode:

.. math::


   C_{f,p,t} \ge D^{min}_{f,p,t},\qquad
   C_{f,p,t} \le D^{max}_{f,p,t}\text{ when declared},

.. math::


   C_{f,p,t}=D^{target}_{f,p,t}\text{ when target basis is selected and a target exists}.

Facility inventory balance:

.. math::


   I_{f,p,t}=I_{f,p,t-1}+\sum_{a\in in(f,p,t)}F_a+\sum_{u\in in(f,p,t)}P_u-C_{f,p,t}
   \qquad \forall (f,p,t),

with :math:`I_{f,p,0}=I^0_{f,p}`.

**Optional road module.**

Road build timing, one-time build, availability, dependencies, block
access, and active capacity are represented as:

.. math::


   R^A_{r,t}=\sum_{t'\le t}R^B_{r,t'},\qquad
   \sum_t R^B_{r,t}\le 1,

.. math::


   R^A_{r,t}\le R^A_{\rho(r),t}\quad\text{for dependency }\rho,

.. math::


   Z_o \le \sum_{r\in access(b(o))}R^A_{r,t(o)},

.. math::


   \sum_{o:t(o)=t,\ access(b(o))\ne\varnothing}\sum_pY_{b(o),p}H_o
   \le \sum_r C_rR^A_{r,t}.

Road costs enter the objective as
:math:`\sum_{r,t}d_t(B_rR^B_{r,t}+M_rR^A_{r,t})`.

**Optional silviculture module.**

For each required transition :math:`q` triggered by block/system
harvest:

.. math::


   \sum_{t\ge earliest(q)}Q_{q,t}=\sum_{o:b(o)=b(q),s(o)=s(q)}H_o.

Transition area carries discounted cost
:math:`\sum_{q,t}d_t c_q Q_{q,t}`.

**Objective profiles.**

Default minimum discounted delivered cost:

.. math::


   \min\; \sum_o d_{t(o)}(F_oZ_o+c_o\sum_pY_{b(o),p}H_o)
   +\sum_a d_{t(a)}c_aF_a
   +\sum_u d_{t(u)}c_uP_u
   +\text{road, silviculture, and fleet costs}.

When demand rows include value per m\ :math:`^3`,
``max_discounted_profit`` maximizes

.. math::


   \sum_{f,p,t}d_tv_{f,p,t}C_{f,p,t}-\text{Cost}.

``max_npv`` additionally adds declared final-period terminal inventory
value:

.. math::


   \sum_{f,p}d_{t_{final}}v^{terminal}_{f,p}I_{f,p,t_{final}}.

**Implementation mapping (equation blocks to code).**

+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Equation/constraint block                       | Pyomo component / helper                 | Data provenance                                    |
+=================================================+==========================================+====================================================+
| Harvest upper bound                             | ``model.harvest_upper``                  | ``HarvestSystemOption.max_area_ha`` and block      |
|                                                 |                                          | operable area                                      |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Semi-continuous minimum cut                     | ``model.harvest_lower``                  | ``HarvestSystemOption.min_area_ha``                |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Whole-block mode                                | ``model.whole_block``                    | ``PlanningUnit.operable_area_ha``                  |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Productivity cap                                | ``model.productivity_cap``               | ``HarvestSystemOption.productivity_m3_per_period`` |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Product conversion                              | ``model.product_conversion``             | ``PlanningUnit.product_yields_m3_per_ha``          |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Block area balance                              | ``model.block_area``                     | ``PlanningUnit.operable_area_ha``                  |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Fleet capacity and acquisition                  | ``model.fleet_capacity``,                | ``FleetCapacity`` and ``FleetOption``              |
|                                                 | ``model.fleet_units``,                   |                                                    |
|                                                 | ``model.fleet_option_upper``             |                                                    |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Flow supply                                     | ``model.flow_supply``                    | ``TransportArc`` and ``product_volume``            |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Arc capacity                                    | ``model.arc_capacity``                   | ``TransportArc.capacity_m3``                       |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Purchase bounds                                 | ``model.purchase_lower``,                | ``ExternalSupply``                                 |
|                                                 | ``model.purchase_upper``                 |                                                    |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Consumption bounds/targets                      | ``model.consumption_lower``,             | ``FacilityDemand``                                 |
|                                                 | ``model.consumption_target``,            |                                                    |
|                                                 | ``model.consumption_upper``              |                                                    |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Inventory balance                               | ``model.inventory_balance``              | ``InitialInventory``, flows, purchases,            |
|                                                 |                                          | consumption                                        |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Road                                            | ``model.road_build``,                    | ``RoadProject``, ``RoadDependency``,               |
| build/availability/dependencies/access/capacity | ``model.road_available``,                | ``BlockRoadAccess``                                |
|                                                 | ``model.road_build_timing``,             |                                                    |
|                                                 | ``model.road_availability``,             |                                                    |
|                                                 | ``model.road_build_once``,               |                                                    |
|                                                 | ``model.road_dependencies``,             |                                                    |
|                                                 | ``model.road_access``,                   |                                                    |
|                                                 | ``model.road_capacity``                  |                                                    |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Silviculture fulfillment                        | ``model.silviculture_area``,             | ``SilvicultureTransition``                         |
|                                                 | ``model.silviculture_fulfillment``       |                                                    |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Objective profiles                              | ``model.objective``                      | ``Economics.objective_profile``, costs, values,    |
|                                                 |                                          | discount factors                                   |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+
| Bundle replay and telemetry                     | ``tactical_bundle_to_dict(...)``,        | ``fhops.model.milp.tactical_operational``          |
|                                                 | ``tactical_bundle_from_dict(...)``,      |                                                    |
|                                                 | ``solve_tactical_operational_milp(...)`` |                                                    |
+-------------------------------------------------+------------------------------------------+----------------------------------------------------+

This formulation is the canonical mathematical reference for the FHOPS
tactical–operational MILP. Generated TeX/RST outputs are derived
artifacts and should not be edited directly.
