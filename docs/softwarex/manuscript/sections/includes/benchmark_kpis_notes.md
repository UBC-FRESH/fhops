The KPI roll-up highlights three solver behaviours we plan to discuss in the manuscript:

- **MiniToy**: ILS beats the SA baselines on objective (23 vs. 15.5) with ~3x faster runtime by focusing on the last-mile improvements. Tabu is competitive on runtime but falls short on assignments.
- **Med42**: The large production penalty showcases why we need heuristics beyond SA—only ILS hits the negative objective targets expected from contraction penalties. The mobilisation preset surfaces the landing-limited behaviour we outline in the narrative.
- **Synthetic tier**: All solvers converge to the same objective, but Tabu demonstrates the runtime floor (0.05 s) while SA presets show how mobilisation shakes affect runtime.

These shared tables let us cite numbers in both the manuscript and the `howto/benchmarks` doc without copy/paste drift.
