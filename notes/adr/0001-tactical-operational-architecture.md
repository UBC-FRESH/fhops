# ADR 0001 — Tactical–Operational Planning Architecture

Date: 2026-09-24  
Status: Proposed for maintainer review  
Parent issue: #36  
Child issue: #37  
Phase branch: `feature/phase6-tactical-operational-expansion`  
Child branch: `issue-37-phase-6.0-workflow-architecture`

## Context

FHOPS currently provides a validated operational scheduler on a day × shift grid. Its public
contract (`Scenario`, schema `1.0.0`) is intentionally centered on blocks, machines, landings,
calendars, harvest systems, production rates, mobilisation, and shift-level assignment. The target
expansion is TOPM-like tactical–operational planning: multi-year, multi-period decisions spanning
harvest quantities, harvest systems, products, mills, transport, inventories, purchases, roads,
silviculture, fleet investment, and discounted economics.

The historical TOPM and later FORCE/Robak OperMAX lineage demonstrate the value of this integrated
scope, but those systems were implemented as closed, case-specific planning shells. The Jaffray et
al. (2026) review adds modern design requirements: parameterize site specificity, document scope and
assumptions, expose validation and feasibility checks, support re-planning, publish reproducible
artifacts, and keep tools auditable.

## Decision

FHOPS will use a **two-level planning architecture**:

1. Preserve the current shift-indexed operational model as the detailed scheduling layer for
   approximately 1–16 week horizons.
2. Add a separate aggregate tactical–operational model for approximately 1–5 year horizons using
   configurable periods (four-week periods, months, or seasons).
3. Couple the models through a business/anticipation horizon and generalized rolling state rather
   than building one monolithic five-year shift-indexed MILP.

The tactical–operational layer will use a new contract, tentatively `TacticalOperationalScenario`,
with explicit `planning_level` and `schema_version` dispatch. The existing operational `Scenario`
and schema `1.0.0` remain supported and unchanged for current users.

## Architectural boundaries

- **Operational layer:** individual machines, block sequencing, staged volume, loader batching,
  mobilisation, shift/day calendars, deterministic/stochastic playback.
- **Tactical–operational layer:** planning-unit area/volume, system alternatives, period timing,
  product yields, transport arcs, facilities, inventories, purchases, roads, silviculture, fleet
  capacity/investment, and objective accounting.
- **Integration layer:** tactical commitments compiled into operational scenarios; operational
  realization state returned to subsequent aggregate solves.
- **Strategic layer:** long-horizon estate sustainability, adjacency/green-up, and landscape policy
  models remain outside Phase 6 unless a later issue explicitly adds them.

## Contract decisions

1. Use long-form, dimension-flexible tables for products, periods, yields, facilities, flows, and
   optional modules; avoid hard-coded TOPM-era matrix layouts.
2. Use explicit unit-bearing field names (`area_ha`, `volume_m3`, `capacity_m3_per_period`,
   `cost_per_m3`, `discount_rate_per_year`) and a scenario currency/base-year declaration.
3. Support three harvest-quantity modes:
   - continuous partial area/volume;
   - semi-continuous `0` or `[minimum, maximum]` quantities;
   - whole-block/all-or-nothing.
4. Implement semi-continuous semantics with tightly bounded activation binaries by default; use
   native solver semi-continuous domains only as an optional backend optimization.
5. Keep optional roads, silviculture, and fleet-investment modules independently toggleable so the
   core harvest → product flow → mill inventory model can ship first.
6. Represent scenario variants as base + sparse overlays with provenance and content hashes; defer
   any browser GUI until the contract is stable.

## Solver and objective decisions

The first aggregate objective will be `min_discounted_delivered_cost`. Discounted profit/NPV and
goal-programming profiles follow once product values and policy targets are represented. Every solve
must emit an objective decomposition and reconciliation tables so users can audit harvest,
transport, purchase, inventory, road, silviculture, and fleet cost components independently.

The tactical MILP will be built with sparse variable generation and physical/tight bounds. Existing
HiGHS and optional Gurobi driver infrastructure will be reused. Decomposition methods (Benders,
Dantzig–Wolfe, fix-and-optimize, rolling variants) are deferred until profiling identifies a real
bottleneck.

## Rolling integration decisions

The existing `fhops.planning.rolling` machinery remains the orchestration foundation, but its state
object must expand beyond machine locks to include:

- machine last location and availability;
- block area/volume remaining by role and product;
- roadside and facility inventories;
- road project state;
- fleet acquisitions/retirements;
- outstanding purchase/delivery commitments; and
- incurred/carry-forward costs.

The near-term business horizon remains detailed (day/shift), while the anticipation horizon remains
aggregate (four-week/month/season).

## Alternatives considered

1. **Extend the existing `Scenario` with optional supply-chain fields.** Rejected: it would create a
   fragile mega-schema and blur operational guarantees.
2. **Stretch the current day × shift tensor to five years.** Rejected: model size and cognitive
   complexity would grow without improving tactical decisions.
3. **Build one monolithic MILP containing every feature.** Rejected: poor solve behavior, poor
   auditability, and difficult module isolation.
4. **GUI-first TOPM/OperMAX clone.** Rejected for Phase 6: FHOPS first needs stable contracts,
   reproducible overlays, validation, and machine-readable reports.
5. **Full strategic forest-estate model.** Deferred: strategic constraints are a separate planning
   level and should not block tactical–operational delivery.

## Consequences

Positive:

- current operational users are insulated from the expansion;
- aggregate planning remains tractable and auditable;
- modules can be implemented and tested independently;
- tactical commitments can be validated by the mature operational playback/KPI stack;
- scenario comparison becomes reproducible rather than GUI-session dependent.

Costs/tradeoffs:

- two contracts and two model bundles must be maintained;
- tactical decisions require explicit handoff/feedback contracts;
- unit and naming discipline must be enforced early;
- some TOPM-era solver-specific semi-continuous behavior will not be reproduced literally.

## Acceptance gates

This ADR is accepted when maintainers approve:

1. the two-level architecture and contract boundary;
2. the period hierarchy and unit discipline;
3. the initial harvest + product-flow + facility-inventory scope;
4. the decision to defer GUI authoring and strategic estate constraints; and
5. the `topm-mini` executable specification as the Phase 6 acceptance baseline.
