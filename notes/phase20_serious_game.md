# Phase 20 plan: web serious game

Parent issue: #306
Branch: `feature/phase20-serious-game`
Status: planned

## Goal

Turn the operational web UI into a deterministic, instructor-run serious game.
Each level maps to an existing shift-level scenario. Teams choose bounded fleet
and scheduling posture controls, launch one SA run, and receive a 0–100 score
against a fully precomputed level parameter space.

## Levels

| Level | Scenario | Horizon | Blocks | Base machines | Fleet palette bounds |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | `tiny7` | 7 d | 2 | 9 | feller 1–2, skidder 1–3, processor 0–2, loader 1–2 |
| 2 | `small21` | 21 d | 6 | 9 | feller 1–2, skidder 1–4, processor 0–2, loader 1–2 |
| 3 | `med42` | 42 d | 12 | 9 | feller 1–3, skidder 1–6, processor 0–3, loader 1–3 |
| 4 | `large84` | 84 d | 48 | 18 | feller 1–4, skidder 1–8, processor 0–4, loader 1–4 |

Only machine types already present in the scenario palette are available. Added
machines copy the base role, rates, and costs; they do not invent a new machine
model.

## Team controls

1. **Fleet counts** for each palette role.
2. **Arrival posture**:
   - `hot`: all machines available on day 1.
   - `staged`: a second wave arrives on day 3.
   - `phased`: role waves on days 1, 3, and 5.
3. **Harvest pattern**:
   - `parallel`: all blocks open from day 1.
   - `sequential`: block release staggered across the first quarter of the horizon.
   - `finish-first`: early blocks get tighter release windows to encourage completion.
4. **Launch** one SA run. Breakdowns are deterministic and hidden; they are not
   a player control.

The controls constrain the scenario. The SA still chooses the actual
machine/block/day/shift assignments.

## Deterministic events

Each level has a fixed seeded event schedule represented as unavailable machine
day/shift slots. Every team sees the same hidden schedule. The event list is
server-side only; it is revealed in the post-level debrief, not before or during
the run.

## Scoring

- Each level fixes `ObjectiveWeights`; game runs cannot edit them.
- Precompute builds every feasible control combination and solves it with the
  operational MIP to optimality.
- `worst_level` is the minimum optimal objective over the feasible combinations;
  `best_level` is the maximum.
- The team's run is re-evaluated under the fixed weights:

```text
score = 100 * (team_objective - worst_level) / (best_level - worst_level)
```

- Scores are clamped to 0–100. The raw objective and component breakdown remain
  internal; the UI shows the normalized score and a component summary.
- A level is game-enabled only when precompute is complete for its full finite
  menu.

## Tournament state

- `TournamentSession`: instructor-created ID, level order, ruleset hash.
- `TeamSession`: opaque team code, ordered attempts, scores, total.
- `LevelAttempt`: choices, variant hash, run ID, raw/normalized score, status.
- One attempt per level. The server rejects replay, skip-ahead, or cross-level
  submission.
- State is local-only and persisted server-side. No public authentication claim.

## UI

A new **Game** workspace:

- lobby/team code entry;
- ordered level map with locked/completed states;
- level briefing and control palette;
- launch and live run progress;
- score card and leaderboard;
- post-level debrief with deterministic events and component summary.

## Precompute and artifacts

Planned artifacts:

- `examples/game/levels/*.yaml` — level manifests.
- `game_levels/<level>/precomputed.json` — menu hash, best/worst, completeness.
- `scripts/precompute_game_levels.py` — offline exact MIP sweep.
- `src/fhops/game/levels.py`, `variants.py`, `scoring.py`, `state.py`.
- `src/fhops/web/game.py` and `src/fhops/web/static/game.*`.
- `tests/game/`, `tests/web/test_game_api.py`.
- `docs/howto/serious_game.rst`.

## Acceptance

- Four levels are defined from existing scenarios.
- Every scored level has a complete exact precompute.
- Same choices produce identical variants, breakdowns, seeds, and scores.
- One-play/order rules are server-enforced and immutable.
- Optimal schedules and hidden events never reach the client.
- Score normalization is reproducible and clamped.
- Tests/docs pass; no operational claim.

## Risks

- Exact precompute can be expensive for Large84. Levels that cannot be fully
  precomputed are not game-enabled.
- The web service has no authentication; tournaments are local/instructor-run.
- A team's SA run is not guaranteed to find the MIP optimum, so 100 is a ceiling.
- The game measures scheduling decisions, not real-world productivity.

## Activation gate

This phase is planned, not active. Activating it requires maintainer approval.
