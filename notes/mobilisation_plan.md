# Mobilisation & Setup Cost Plan

Date: 2025-11-07
Status: Draft — pending modular reorganisation.

## Objectives
- Model machine movement and block setup costs informed by distance thresholds and per-machine walk costs.
- Integrate mobilisation costs into both MIP and heuristic solvers without regressing existing behaviour.
- Surface mobilisation configuration (distance thresholds, per-metre walk costs, setup fees) in the scenario contract and CLI.

## Planned Tasks
- [x] Extend scenario data contract with distance matrices or geometry hooks for blocks/landings. *(MobilisationConfig + BlockDistance scaffolded.)*
- [x] Define mobilisation parameters per machine/system (walk cost per metre, setup cost, threshold distance). *(MachineMobilisation added.)*
- [x] Implement mobilisation penalty terms in Pyomo (`optimization/mip/builder.py`). *(Setup-cost deduction wired into objective.)*
- [x] Add heuristic loss penalties mirroring the MIP logic. *(SA evaluator subtracts setup cost per assignment.)*
- [ ] Update evaluation metrics to report mobilisation spend.

## Tests
- [x] Fixture scenarios with known mobilisation costs (short vs long moves). *(See `tests/test_mobilisation.py`.)*
- [ ] Regression tests confirming solver outputs incorporate mobilisation charges.

## Documentation
- [ ] Sphinx how-to explaining mobilisation configuration and cost outcomes.
- [ ] CLI examples (`fhops solve-mip --mobilisation-config ...`).

## Open Questions
- Do we require explicit spatial coordinates or is a distance matrix sufficient?
- How to handle mobilisation downtime (time penalty) vs pure cost?
