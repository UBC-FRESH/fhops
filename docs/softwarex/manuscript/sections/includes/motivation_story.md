# FHOPS motivation narrative (source of truth)

Forest harvest-planning software still leans on bespoke, closed toolchains that make it hard for regulators, Indigenous governments, and researchers to audit models or extend them for emerging policy questions. Rosalia Jaffray’s MASc literature review catalogues the recurring pain points: one-off solver integrations, weak telemetry, limited robustness testing, and siloed datasets that rarely ship with reproducible scripts. FHOPS exists to close those gaps for B.C. operations and comparable jurisdictions.

The SoftwareX paper will highlight three gaps we actively address:

1. **Open, reusable tooling.** FHOPS publishes its data contract, CLI, and solver implementations under MIT so other teams can ingest the same scenarios, swap heuristics, and contribute modules without vendor lock-in. The scenario schema mirrors what forestry engineers already use in practice (blocks, machines, landings, shifts), but the implementation is scriptable and version-controlled.
2. **Integrated workflow + automation.** Instead of the ad hoc “optimizer + spreadsheet” pattern flagged in the review, FHOPS provides deterministic solvers (Pyomo+HiGHS), SA/ILS/Tabu heuristics, a turnkey tuning harness, and telemetry/playback tooling that runs from `make assets`. Every figure/table in the manuscript will be regenerated from the same scripts users run locally.
3. **Robust evaluation + extensibility.** FHOPS layers stochastic playback, stress testing, and cost models over the base scheduler so we can quantify solution stability before fielding new policies. Those evaluation hooks also set up Rosalia’s thesis Chapter 2: she retains the full BC case studies (two–three tenures) and uses FHOPS as the engine, while this SoftwareX paper focuses on the platform itself.

> Reuse plan: exporter script will render this Markdown into `sections/includes/motivation_story.tex` for the manuscript and `docs/overview_shared_motivation.rst` for Sphinx so the same paragraphs stay synchronized.
