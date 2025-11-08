# Harvest System & Sequencing Plan

Date: 2025-11-07
Status: Draft — supports mobilisation and constraint upgrades.

## Objectives
- Encode harvest system definitions (ordered job sequences, machine-worker assignments, environments).
- Enforce sequencing constraints in the MIP and heuristics based on system requirements.
- Surface system information in scenario contract, synthetic datasets, and docs.

## Planned Tasks
- [ ] Define harvest system registry structure under `scheduling/systems` (jobs, machines, prerequisites) based on Jaffray (2025) system taxonomy (ground-based, CTL, steep-slope tethered, cable variants, helicopter).
  - [x] Seed default registry in `scheduling/systems/models.py::default_system_registry()` covering BC systems.
- [ ] Extend scenario contract to assign blocks to systems and map workers to machine-job pairs.
- [ ] Implement sequencing constraints in Pyomo (precedence, resource availability).
- [ ] Teach heuristics to respect sequencing and system-specific constraints.
- [ ] Update evaluation to check compliance and report violations.

### Immediate next steps
- [x] Draft constraint stub under `optimization/mip/constraints/system_sequencing.py` capturing precedence placeholders.
- [x] Outline data model sketch for `scheduling/systems` (system id, ordered jobs, machine roles).
- [x] Extend scenario contract with optional system linkage once registry stabilises.
- [ ] Retrofit synthetic generator to emit multi-system scenarios for testing sequencing logic.
- [ ] Seed default system registry entries:
    - Ground-based (feller-buncher → grapple skidder → roadside processor → loader/trucks)
    - Ground-based (hand fall → shovel logger → roadside processor → loader/trucks)
    - Cut-to-Length (harvester/forwarder sequence, direct-to-truck shortwood)
    - Steep-slope mechanised (tethered harvester → tethered shovel/skidder → processor → loader)
    - Cable standing skyline (hand/mech fall → skyline yarder → landing processor/hand buck → loader)
    - Cable running skyline (hand/mech fall → grapple yarder → landing processor/hand buck → loader)
    - Helicopter logging (hand fall → helicopter longline → landing/hand buck; optional direct-to-water).

## Tests
- [ ] Scenarios covering different systems (ground-based, cable, heli) with expected job orderings.
- [ ] Regression tests verifying sequencing is enforced in solver outputs.

## Documentation
- [ ] System registry reference in Sphinx.
- [ ] Tutorials showing how to configure and analyse system-specific schedules.

## Open Questions
- How to represent systems with optional/parallel tasks?
- Do we need environment-specific default parameters (e.g., slope limits) baked into the registry?
