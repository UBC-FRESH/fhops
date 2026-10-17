# ADR 0003: the SA search may change its random stream for performance

Status: accepted on 2026-10-17 (G. Paradis).
Date: 2026-10-17
Related: P10 (issue #166), P9 (issue #165)

## Context

The `cross_exchange` operator shuffled a materialised list of every assignment pair. For the
large84 example (909 assignments) that is a 412 686-element list shuffled once per call, which was
32 percent of the solver's runtime. Any change to how the pairs are sampled changes the random
stream, which changes every SA result and the pinned regression fixtures.

## Decision

The SA random stream is not frozen. Operators may sample candidates in a way that changes the
stream when this gives a material speedup, provided that:

- the change is recorded in an ADR and the changelog;
- the pinned SA baselines are regenerated with `scripts/regenerate_sa_baselines.py`, so the tests
  pin the current behaviour;
- the operator keeps its contract (same move type, same feasibility checks).

`cross_exchange` now draws pairs at random up to a bounded budget (`tries = 500`) instead of
shuffling the whole pair list.

## Consequences

- large84 gains about 1.7x at equal iterations (3.4 to 5.7 evaluations/s); med42 about 1.15x.
- The pinned operator-parity test (pre-#151 shuffle) no longer covers `cross_exchange`.
- The CJFR manuscript is unaffected: its SA results were produced on FHOPS 1.0.1, a separate line.
- Future SA work (for example, an incremental repair) may change the stream on the same terms.
