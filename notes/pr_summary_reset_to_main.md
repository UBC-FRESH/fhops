**Title**

Reset heuristics + datasets while chasing SoftwareX manuscript; prep for MILP reformulation

**Summary**

This branch started as “finish the SoftwareX manuscript assets,” but it quickly turned into a deeper cleanup of heuristics, CLI tooling, and the med42 dataset once it became clear the existing heuristics and examples weren’t behaving as advertised. At this point the work has sprawled; I’d like to merge it back into `main` as a coherent reset, then spin a fresh branch focused solely on implementing the MILP reformulation plan.

**Narrative**

- The original intent was narrow: generate and polish the SoftwareX manuscript assets (benchmarks, playback, tuning tables) on top of the existing heuristics and example datasets.
- While trying to line up manuscript KPIs with the code, it became obvious that the heuristic solvers (SA/ILS/Tabu) weren’t working robustly:
  - SA could “finish” blocks on paper without truly respecting the “finish-the-block-before-switching” business rule.
  - Tabu’s stall logic behaved like a hard early stop instead of a restart/perturb diversification step.
- To make this debuggable, we implemented a CLI **watch mode**:
  - A live Rich dashboard for `solve-heur`, `solve-ils`, `solve-tabu`, and the benchmark/tuning commands.
  - Snapshots now carry richer telemetry (current/best/rolling objective, Δbest, temperature, acceptance rates, workers_busy/total, restarts), so it’s possible to see in real time when a heuristic is thrashing, stalling, or converging.
  - We added smoke tests and basic teardown handling so `--watch` behaves consistently and doesn’t trash the terminal.
- Once the heuristics were observable, it became clear the **med42 and related test datasets were miscalibrated**:
  - The original med42 was either massively over-capacitated (all blocks trivially finished) or under-capacitated in ways that made the objective degenerate.
  - Work on Lahrsen/ADV6N7/TN‑261 regressions led to a full regeneration of `examples/med42`:
    - One four‑machine ground-based system.
    - Blocks with Lahrsen-range stem sizes, densities, and volumes per hectare.
    - Realistic regression-based m³/PMH for each machine × block.
    - A workload/capacity balance where some blocks *must* be left unfinished, so heuristics actually have to prioritise.
  - The SoftwareX benchmark and playback fixtures were updated to reflect the new, more defensible med42.
- Along the way, we fixed and hardened a number of small but important pieces:
  - SA’s internal objective and telemetry (block-completion policy, temperature scaling, acceptance accounting).
  - Tabu’s restart logic and watch telemetry.
  - Watch-dashboard typing and ruff/mypy/Sphinx cleanliness.

At this point, the SoftwareX workstream, heuristic debugging, dataset regeneration, and early MILP planning are all tangled in one branch. The safest move is to merge this “reset” back to `main` so the improved heuristics and datasets become the new baseline, then branch cleanly for the MILP work.

**Key Changes (high level)**

- **Heuristics & CLI**
  - Enforced “finish-the-block-before-switching” in SA and wired penalties for leftover volume.
  - Added and refined `--watch` mode for SA/ILS/Tabu and the benchmark/tuning CLIs, with richer snapshot telemetry and sane Ctrl+C teardown.
  - Improved SA/Tabu restart/temperature logic and linked them cleanly into the telemetry/watch stack.

- **Datasets & assets**
  - Regenerated `examples/med42`:
    - Blocks drawn from Lahrsen-range stand metrics with realistic areas and volumes.
    - Machine productivities derived from Lahrsen feller-buncher, ADV6N7 skidder, Berry processor, and TN‑261 loader regressions (no ad‑hoc scaling).
    - Workload tuned so a single four-machine crew can’t finish all blocks in 42 days, giving heuristics real trade-offs.
  - Refreshed med42-related SoftwareX assets (benchmarks, tuning, playback) and updated READMEs/change log entries accordingly.

- **Planning & references**
  - Added `notes/mip_formulation_plan.md`:
    - Summarises the relevant MILP literature (Bredström 2010, Frisk 2016, Shabaev 2020, Arora 2023, Epstein et al. Chapter 18).
    - Lays out a concrete, nested task plan for:
      - An operational MILP benchmark mirroring FHOPS’s machine–block–time model.
      - A tactical team/area/period MILP wrapper.
      - Potential decomposition/column-generation experiments.
  - Logged the new fhop references in `notes/reference_log.md` with “when to use” annotations so we know which wheels to copy instead of reinventing them later.

**Why merge now**

- This branch has grown into a mix of:
  - SoftwareX manuscript plumbing.
  - Heuristic correctness fixes.
  - Dataset regeneration.
  - Early MILP design work.
- The heuristics and example datasets are now in a much better state and should be the baseline for any future work (including SoftwareX and MILP).
- Continuing to hang more work off this branch will make future review and bisecting painful.

Merging back to `main` here gives us a clean, tested starting point. From there, I plan to open a new, tightly scoped branch focused on the **MILP reformulation plan** (implementing the operational MILP benchmark first, then layering in tactical and decomposition pieces as per `notes/mip_formulation_plan.md`).
