Productivity Catalog Gaps
=========================

Arnvik Appendix 8 scope
-----------------------

The Appendix 8 tables that power ``data/productivity/arnvik_forwarder.json`` only list
single-grip harvesters, feller-bunchers, and harwarders (per the thesis framing). Forwarder
and grapple-skidder regressions are absent, so the parsed JSON should be treated strictly as a
harvester/harwarder validation set. For primary-transport roles we must fall back to the
external references already logged in ``notes/reference`` (Ghaffariyan et al. 2019, Kellogg &
Bettinger 1994, Allman et al. 2021, etc.).

Implications
------------

* Continue using the Appendix 8 extracts for harwarder QA only; do **not** attempt to infer
  forwarder performance or grapple-skidder coefficients from the current dump.
* Build the forwarder helper stack (`fhops.productivity.forwarder_bc`) on top of the
  published AFORA/ALPACA equations and Kellogg regressions, with BC caveats called out in the
  dataset plan.
* Document any future FPInnovations payload/slope confirmations in this file so the planning
  crew can see when the primary-transport gap is genuinely closed.

Forwarder equation stack (BC roll-out)
--------------------------------------

Sources in hand
^^^^^^^^^^^^^^^

* **Ghaffariyan et al. 2019 (AFORA/ALPACA)** – ``notes/reference/sb_202_2019_2.txt`` captures
  Equations 2 (14 t) and 3 (20 t) that predict m³/PMH₀ from extraction distance. We already added
  the slope multipliers (flat = 1.0, 10–20 % = 0.75, >20 % = 0.15) to the CLI.
* **Kellogg & Bettinger 1994** – ``fhops.productivity.kellogg_bettinger1994`` exposes the western
  Oregon FMG 910 regression (sawlog/pulpwood/mixed offsets) covering multi-product CTL thinning.
* **Allman et al. 2021** – ``notes/reference/forests-13-00305-v2.txt`` includes the tethered
  harvester-forwarder Monte Carlo payload-vs-slope/distance regressions we plan to translate into
  slope penalty/payload-cap helpers once FPInnovations validates the coastal BC analogues.

Caveats and pending confirmations
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* The AFORA/ALPACA equations are calibrated on Australian pine/eucalypt thinnings with gentle
  terrain; document this in `notes/dataset_inspection_plan.md` and warn users that >20 % slope
  behaviour is extrapolated via the simplistic ×0.15 multiplier until FPInnovations publishes a BC
  dataset.
* The Kellogg regression assumes west-side Oregon extraction distances (<350 m) and a specific
  forwarder configuration (FMG 910). We need payload tables from FPInnovations or the ALPACA
  dataset to confirm whether the linear distance coefficients hold for heavier BC stems.
* FPInnovations payload/slope confirmations (ongoing). Once we have those, add them here along with
  any new helper references so the `forwarder_bc` module can toggle between “Scandinavian/Australia
  baseline” and “BC validated” sets.
