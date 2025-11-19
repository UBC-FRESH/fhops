Harvest System Registry
=======================

FHOPS ships with a typed registry describing commonly-used harvest systems. Each system lists the
ordered jobs, required machine roles, and precedence relationships; solver components and data
contracts rely on this metadata to enforce sequencing constraints.

Data Model
----------

Harvest systems live under :mod:`fhops.scheduling.systems.models` and are represented by two
dataclasses:

``SystemJob``
    Defined by ``name``, ``machine_role``, and a list of prerequisite job names.
``HarvestSystem``
    Holds ``system_id``, ordered ``jobs``, and optional ``environment`` / ``notes`` metadata.

The helper :func:`fhops.scheduling.systems.models.default_system_registry` returns the built-in
collection summarised below.

Default Systems
---------------

.. list-table::
   :header-rows: 1
   :widths: 18 18 12 52

   * - System ID
     - Environment
     - Machine Roles (ordered)
     - Notes
   * - ``ground_fb_skid``
     - ground-based
     - feller-buncher → grapple skidder → roadside processor → loader
     - Mechanised felling followed by grapple skidding to roadside processing and loading.
   * - ``ground_fb_loader_liveheel``
     - ground-based
     - feller-buncher → grapple skidder → roadside processor → loader
     - Same chain as ``ground_fb_skid`` but the loader job is pinned to the Barko 450 live-heel preset (TN-46) for interior operations.
   * - ``ground_hand_shovel``
     - ground-based
     - hand faller → shovel logger → roadside processor → loader
     - Hand falling with shovel logging as primary transport.
   * - ``ground_fb_shovel``
     - ground-based
     - feller-buncher → shovel logger → roadside processor → loader
     - Mix of mechanised felling and shovel logging before roadside processing.
   * - ``ctl``
     - cut-to-length
     - single-grip harvester → forwarder → loader
     - Harvester processes at stump and forwarder hauls shortwood to trucks.
   * - ``steep_tethered``
     - steep-slope mechanised
     - tethered harvester → tethered shovel/skidder → roadside processor → loader
     - Winch-assist equipment across the full sequence.
   * - ``cable_standing``
     - cable-standing skyline
     - hand/mech faller → skyline yarder → landing processor/hand buck → loader
     - Standing skyline with chokers feeding landing processing.
   * - ``cable_running``
     - cable-running skyline
     - hand/mech faller → grapple yarder → landing processor/hand buck → loader
     - Grapple yarder variant with landing finishing.
   * - ``helicopter``
     - helicopter
     - hand faller → helicopter longline → hand buck/processor → loader/water
     - Helicopter longline with on-landing processing or direct-to-water transfer.

Using the Registry
------------------

- Scenario contract: blocks may specify ``harvest_system_id``; the scenario definition can embed a
  ``harvest_systems`` map to override or extend the defaults (see
  :mod:`fhops.scenario.contract.models`).
- Synthetic generator: :func:`fhops.scenario.synthetic.generate_with_systems` assigns systems
  round-robin to blocks and creates matching machine role inventories.
- Solvers: sequencing constraints in the MIP and heuristics consume the registry to enforce job
  ordering and machine-role feasibility. Violations surface through KPI outputs and CLI summaries.

Extending Systems
-----------------

To define custom systems, construct :class:`HarvestSystem` instances and supply them via the scenario
contract. When adding optional or parallel tasks, document the intended precedence explicitly and
consider updating this reference alongside any new data files.

Forwarder Productivity Models
-----------------------------

Cut-to-length systems rely on the forwarder helper stack (``fhops.productivity.forwarder_bc``) when
``fhops dataset estimate-productivity`` or ``fhops dataset estimate-forwarder-productivity`` is invoked.
Pick the regression that matches the stand context:

* ``ghaffariyan-small`` / ``ghaffariyan-large`` – ALPACA plantation thinning data (14 t and 20 t
  forwarders). Requires ``--extraction-distance`` plus either ``--slope-class`` or
  ``--slope-factor``. Use these when analysing Australian-style commercial thinning or when you
  need quick distance/slope sensitivity without payload inputs.
* ``kellogg-sawlog`` / ``kellogg-pulpwood`` / ``kellogg-mixed`` – FMG 910 regression from
  Kellogg & Bettinger (1994) for western Oregon CTL operations. Supply ``--volume-per-load``,
  ``--distance-out``, ``--travel-in-unit``, and ``--distance-in``. Ideal for moderate (≤350 m)
  extraction distances and when you must distinguish sawlog vs. pulp payloads.
* ``adv6n10-shortwood`` – FPInnovations ADV6N10 shortwood model for boreal multi-product sorting.
  Requires ``--payload-per-trip``, ``--mean-log-length``, ``--travel-speed``, ``--trail-length``, and
  ``--products-per-trail``. Use this when you have explicit payload/log-length targets or need to
  quantify the productivity penalty of sorting several products per trail.
* ``eriksson-final-felling`` / ``eriksson-thinning`` – Eriksson & Lindroos (2014) Swedish follow-up
  dataset covering >700 CTL forwarders. Provide ``--mean-extraction-distance`` (m),
  ``--mean-stem-size`` (m³), and ``--load-capacity`` (m³). The final-felling variant reflects larger
  stems and long forwarding distances; the thinning variant should be used when stem sizes stay below
  ~0.2 m³. These regressions omit explicit slope factors, so treat steep ground as an open action item
  until BC-specific multipliers are published.
* ``laitila-vaatainen-brushwood`` – Ponsse Buffalo Dual harwarder regression from Laitila &
  Väätäinen (2020). Supply ``--harvested-trees-per-ha``, ``--avg-tree-volume-dm3``, and
  ``--forwarding-distance``. Optional knobs ``--harwarder-payload`` (default 7.1 m³) and
  ``--grapple-load-unloading`` (default 0.29 m³) match the study’s payload assumptions. This helper
  is best suited for whole-tree/brushwood clean-up, light salvage, or plantation corridor clearing
  where a single machine fells, accumulates, and shuttles material to the roadside.

The commands surface identical arguments under both the dedicated forwarder CLI and the general
``estimate-productivity --machine-role forwarder`` path, so the same guidance applies to synthetic
generators, scenario QA, and KPI workflows.

Roadside Processor Productivity Models
--------------------------------------

``fhops.dataset estimate-productivity --machine-role roadside_processor`` now supports two
regressions:

* ``--processor-model berry2019`` *(default)* – Berry (2019) Kinleith NZ processor study keyed to
  piece size, tree form, and crew/utilisation multipliers. ``fhops dataset berry-log-grades`` (or
  ``--processor-show-grade-stats``) dumps the digitised Appendix 13 emmeans table so you can see the
  per-grade mean ±2σ cycle times we extracted from the thesis image. Treat those values as qualitative
  cues only—they came from a screenshot, not a raw table.
  * ``--processor-piece-size-m3`` – average piece size per stem (m³). Delay-free productivity is
    computed via ``34.7 × piece_size + 11.3``.
  * ``--processor-tree-form`` – 0 (good), 1 (poor), 2 (bad). Tree-form penalties follow Berry’s
    observed processing-time uplift (category 1 = +56 % time ⇒ productivity ×0.64, category 2 = +84 %
    ⇒ ×0.54).
  * ``--processor-crew-multiplier`` – optional operator adjustment (crew A ≈ +16 % ⇒ 1.16, crew C
    ≈ −25 % ⇒ 0.75, etc.).
  * ``--processor-delay-multiplier`` – utilisation factor (default 0.91 reflects delays <10 min logged
    in the study). Adjust it if your PMH/SMH ratio differs.
  * ``--processor-carrier`` – ``purpose_built`` (default) or ``excavator``. Excavator carriers apply the
    utilisation/productivity penalty observed by Magagnotti et al. (2017) and surface the higher fuel
    consumption + yarder-wait behaviour noted by Nakagawa (2010) / Bertone & Manzone (2025).
* ``--processor-model labelle2016`` – Labelle et al. (2016) sugar maple study (New Brunswick) grouped by tree form quality (acceptable vs. unacceptable). Outputs are PMH₀.
  * ``--processor-dbh-cm`` – diameter at breast height (cm).
  * ``--processor-labelle2016-form`` – ``acceptable`` or ``unacceptable`` form class (matches the NHRI tree-form groupings).
  * ``--processor-delay-multiplier`` – optional utilisation scaling.
* ``--processor-model labelle2017`` – Labelle et al. (2017) excavator-based CTL processor regressions (New Brunswick hardwoods). Includes two cubic polynomials and two power-law fits.
  * ``--processor-dbh-cm`` – diameter at breast height (cm).
  * ``--processor-labelle2017-variant`` – ``poly1``, ``poly2``, ``power1``, or ``power2`` (mirrors Appendix 8 table). Use the polynomial variants for large sample sizes (338/365 trees) or the power-law variants when matching the smaller subsets (42/55 trees).
* ``--processor-model labelle2018`` – Labelle et al. (2018) Bavarian beech/spruce study (Ponsse Bear + H8) with separate regressions for rubber-tired (rw) vs. tracked (ct) processors.
  * ``--processor-dbh-cm`` – diameter at breast height (cm).
  * ``--processor-labelle2018-variant`` – ``rw_poly1``, ``rw_poly2``, ``ct_poly1``, or ``ct_poly2`` (Appendix 8 Table). Outputs are PMH₀; apply utilisation as needed.
* ``--processor-model labelle2019_dbh`` – Labelle et al. (2019) Bavarian hardwood case study
  (TimberPro 620-E + LogMax 7000C) using DBH polynomials per species/treatment. These regressions
  output delay-free PMH₀ productivity for large-diameter, hardwood-dominated stands (rare in BC but
  useful when deploying FHOPS abroad).
  * ``--processor-dbh-cm`` – diameter at breast height (cm).
  * ``--processor-species`` – ``spruce`` or ``beech`` (matching the reference plots).
  * ``--processor-treatment`` – ``clear_cut`` or ``selective_cut`` (group selection). Use
    ``--processor-delay-multiplier`` if you need to impose a local utilisation ratio.
* ``--processor-model labelle2019_volume`` – same Bavarian dataset, but keyed to recovered tree volume
  (m³/stem). Accepts the same species/treatment flags plus:
  * ``--processor-volume-m3`` – recovered volume per stem (m³). The helper applies the
    ``a + b·V₆ − c·V₆²`` polynomials published in Appendix 8/9 and still reports PMH₀ outputs.
  * Continue using ``--processor-delay-multiplier`` for utilisation assumptions; CLI output reminds
    users that this model is intended for hardwood-dominated export scenarios rather than BC norms.
* ``--processor-model adv5n6`` – FPInnovations Advantage Vol. 5 No. 6 coastal BC processor study
  (Madill 3800 with Waratah HTH624). Use ``--processor-stem-source`` (``loader_forwarded`` or
  ``grapple_yarded``) plus ``--processor-processing-mode`` (``cold``, ``hot``, or ``low_volume``) to
  match the published cold-deck loader-forwarded scenario vs. the grapple-yarded hot/cold decks.
  Outputs provide both PMH and SMH productivity along with the $/m³ cost figure from the report, so
  analysts can keep BC roadside presets tied to local landing data. Cost figures shown in the CLI are
  escalated to 2024 CAD using Statistics Canada CPI (Table 18-10-0005-01) so they’re comparable with
  newer references.
* ``--processor-model hypro775`` – HYPRO 775 tractor-mounted double-grip processor preset sourced from Castro
  Pérez (2020) and Zurita Vintimilla (2021). No additional predictors are needed; the helper reports mean cycle time
  (~45 s), gross/net trees per hour, delay-free m³/PMH (~21.4), fuel use (≈21 L/h or 0.78 L/m³), and ergonomic notes
  (≈85 dB(A), heavy-work cardiovascular load). Use this when modelling tractor-mounted landing processors in
  small-diameter thinnings or low-investment deployments.
* ``--processor-model spinelli2010`` – Spinelli, Hartsough & Magagnotti’s Italian CTL productivity standards
  (Forest Products Journal 60(3):226–235). Choose between harvest (in-stand) and landing-processing modes via
  ``--processor-spinelli-operation`` and supply the tree volume (``--processor-piece-size-m3``), carrier power
  (``--processor-machine-power-kw``), slope (``--processor-slope-percent``), stand type, carrier/head/species flags,
  and (for harvest) the removals/residuals per hectare. The helper applies the published accessory (14.7/29.6 %)
  and delay (50/21/44 %) ratios automatically and prints the per-element cycle times so you can see how slope,
  carrier choice, and species mix influence delay-free PMH outputs.
* ``--processor-model visser2015`` – Visser & Tolan (2015) NZ cable-yarder landings (Cat 330DL +
  Waratah HTH626) comparing 5/9/12/15 log sorts. The helper interpolates the published piece-size
  curves (1–3 m³ stems) and reports both the delay-free m³/PMH and the delta versus the 5-sort baseline.
  * ``--processor-piece-size-m3`` – mean stem volume per piece (must fall within the 1–3 m³ study
    range).
  * ``--processor-log-sorts`` – number of log sorts to cut (``5``, ``9``, ``12``, ``15``). CLI output
    includes the gross-value and value-per-PMH figures from the paper (2.0 m³ reference, 2014 USD).
  * ``--processor-delay-multiplier`` – optional utilisation scaling (default 0.91). The CLI applies
    this multiplier to the Visser delay-free values so you can simulate longer shifts or landing
    congestion.
* ``--processor-model tn103`` – FERIC TN-103 Caterpillar DL221 evaluation in coastal old growth.
  Pick ``--processor-tn103-scenario`` (``area_a_feller_bunched``, ``area_b_handfelled``,
  ``combined_observed``, or ``combined_high_util``) to reflect how well windrows are prepared and
  whether the 73 % utilisation improvement has been implemented. The helper reports trees/PMH,
  m³/PMH, and the published $/m³ and $/tree costs; CLI output also notes windrow prep guidance so
  analysts can match conditions to their landing prep.
* ``--processor-model tr87`` – FERIC TR-87 roadside CTL case study (two Timberjack TJ90 processors
  plus LL229 loader). Use ``--processor-tr87-scenario`` to choose day shift, night shift, the observed
  combined average, or the “wait-for-wood removed” system scenario (240 m³/shift target). Outputs list
  trees per PMH, m³/PMH/SMH, utilisation, and the $2.67/m³ processing cost so you can benchmark historic
  TJ90 fleets or sanity-check inland roadside plans.
* ``--processor-model tr106`` – FERIC TR-106 lodgepole pine shelterwood study near Williams Lake. Pick
  ``--processor-tr106-scenario`` (Case 1187 Oct–Nov vs. Feb, or the Steyr KP40 carriers on Cat 225 /
  Link-Belt L-2800 / Cat EL180) to see the published PMH vs. net-PMH productivity, stems per hour, cycle
  minutes, utilisation, and CPI-scaled cost metadata. Handy when you need an interior partial-cut preset
  to complement the coastal TR-87 helper.
* ``--processor-model tn166`` – FERIC TN-166 stroke-processor study (Denis D3000 telescopic boom) from
  interior BC. Choose ``--processor-tn166-scenario`` (``grapple_yarded``, ``right_of_way``, or
  ``mixed_shift``) to flip between the detailed timing splits or the overall shift-level average. The
  helper reports PMH/SMH productivity, stems per hour, and the published $/m³ + $/stem values. Pick
  this preset when you need an interior stroke-processor baseline rather than the hardwood-focused
  Labelle regressions. Costs are also escalated to 2024 CAD via the same Statistics Canada CPI series.
* `fhops dataset unbc-hoe-chucking` – reference command that prints the UNBC (Renzie 2006) Table 33
  hoe-chucking shift summary (time, volume, productivity, observed/weighted $/m³ for group selection,
  group retention, and clearcut treatments). Useful when budgeting manual hoe-chucking support around
  landing processors in cedar–hemlock partial cuts.
* ``--processor-automatic-bucking`` – Optional switch for *Berry*/*Labelle* helpers that applies the
  +12.4 % delay-free productivity multiplier from Labelle & Huß (2018, Silva Fennica 52(3):9947) and
  prints the associated €3.3/m³ revenue delta (2018 EUR) for traceability. The flag is ignored for the
  table-driven FPInnovations presets because those studies didn’t use the on-board bucking optimizer.

CLI output reports the base delay-free productivity, the applied multipliers, and the utilisation-adjusted
m³/PMH so costing workflows can decide which value to pass downstream. Remember that the Labelle models
were calibrated outside BC—treat them as hardwood export presets and rely on the Berry helper for mixed
or conifer-dominated BC blocks.

Loader-Forwarder Productivity Models
------------------------------------

``fhops.dataset estimate-productivity --machine-role loader`` now supports three literature-backed presets:

* ``--loader-model tn261`` (default) – the Vancouver Island loader-forwarder study (FERIC TN-261, 1994).
  Provide:

  * ``--loader-piece-size-m3`` – mean stem volume per turn (m³).
  * ``--loader-distance-m`` – external distance from deck to the farthest stem (m).
  * ``--loader-slope-percent`` – approximate slope (%) along the forwarding direction. Positive values
    represent adverse (uphill) travel; negative values represent favourable (downhill) travel.
  * ``--loader-bunched/--loader-hand-felled`` – indicates whether stems are mechanically bunched/aligned or
    hand-felled/scattered (hand-felled defaults to a 0.90 multiplier).
  * ``--loader-delay-multiplier`` – optional utilisation factor (default 1.0 because TN-261 detailed timing was
    delay-free).

  The helper uses a log-linear fit (piece-size exponent ≈0.41, distance exponent ≈−0.60) with gentle slope
  adjustments (≈3 % penalty per +10 % uphill, ≈1.5 % bump per −10 % downhill, clamped between 0.6 and 1.15).
  CLI output reports the delay-free vs. utilisation-adjusted productivity along with the applied multipliers so
  scenario costing flows can pick the appropriate value.

* ``--loader-model adv2n26`` – the Kosicki (2001) clambunk/hoe-forwarding trial (FPInnovations ADV-2 No. 26)
  with a Trans-Gesco TG88, John Deere 892D-LC loader-forwarder, and Link-Belt landing loader. You can use the
  study defaults or override them with:

  * ``--loader-travel-empty-m`` – travel empty distance (m) used in Equation 1 (default 236 m).
  * ``--loader-stems-per-cycle`` – stems per cycle (default 19.7).
  * ``--loader-stem-volume-m3`` – average stem volume per piece (default 1.52 m³/stem; payload is derived from
    stems × volume unless you supply a custom payload via the helper).
  * ``--loader-utilisation`` – PMH/SMH ratio (default 0.77 from the shift-level study).
  * ``--loader-in-cycle-delay-minutes`` – optional override for in-cycle delay minutes (<10 min delays); omit it
    to use the published 5 % ratio from Figure 9.

  CLI output shows the delay-free vs. total cycle minutes, payload per turn, and both m³/PMH and m³/SMH so you
  can pair the loader helper with the TG88 clambunk costs. This model is especially handy for “hot logging”
  corridors where a loader-forwarder supports a clambunk or skyline operation. The ADV2N26 study also documented
  soil disturbance: 20.4% of the harvested area was covered by unbladed trails (0.54 ha first-class at 6.2 m mean
  width with 91% exposed mineral soil, 0.87 ha second-class at 4.7 m / 39%, 0.49 ha third-class at 4.0 m / 14%).
  FHOPS prints these stats as a reminder when you select ``adv2n26`` so you can mirror the disturbance footprint
  in planning or compliance reports.
* ``--loader-model adv5n1`` – the Madill 3800 loader-forwarder regression from ADV-5 No. 1 (Figure 9). The
  slope-class regressions (0–10 %, 11–30 %) were manually digitised from the report so you can recover the
  original linear fits:

  * ``--loader-distance-m`` – forwarding distance (m) for the regression.
  * ``--loader-slope-class`` – ``0_10`` (baseline) or ``11_30`` (adds the 18 % penalty discussed in the text).
  * ``--loader-payload-m3`` – payload per cycle (default 2.77 m³/cycle).
  * ``--loader-utilisation`` – utilisation multiplier (default 0.93 per the ADV5N1 shift-level study).

  CLI output reports the linear coefficients (intercept/slope), cycle time (minutes), delay-free m³/PMH, and
  utilisation-adjusted m³/SMH so corridor costing flows can adopt the ADV5N1 defaults immediately.
* ``--loader-model barko450`` – FERIC TN-46 Barko 450 live-heel loader preset for interior roadside decks. No
  predictors are required; instead pick ``--loader-barko-scenario`` (``ground_skid_block`` for the grapple-skid trial
  or ``cable_yard_block`` for the Washington 78 yarder decks) to show the published ≈658 m³/shift averages,
  availability (96 %), utilisation (79 %), and the ~17 % truck-wait/move penalty. Supplying ``--loader-utilisation``
  rescales the Barko production and $/m³ outputs so you can model different truck-supply assumptions. This preset
  now draws its $257.26/shift (1986 CAD) cost baseline directly from the TR‑73/TN‑64/TN‑51 roadside sort studies;
  run with ``--show-costs`` to see the CPI-inflated owning/operating/repair breakdown that feeds the costing CLI.
* ``--loader-model kizha2020`` – Loader utilisation/delay reference from Kizha et al. (2020) northern California
  biomass landings (Thunderbird 840W supporting a Madill yarder). Use ``--loader-hot-cold-mode`` (``hot`` = integrated
  sawlog/biomass loading, ``cold`` = decoupled biomass-only loading) to see how utilisation collapses when the roll-off
  truck fleet is undersized. CLI output reports the 55 % vs. 7 % utilisation, the dominant delay contributors, and the
  $/PMH penalty attributable to waiting so you can size truck fleets/landing space before committing to a hot or cold
  biomass workflow.

Loader harvest-system overrides
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Referencing a harvest-system template (``--harvest-system-id`` or ``--dataset``/``--block-id``) now auto-fills
loader inputs the same way shovel, skyline, and helicopter presets work. The registry currently includes:

* ``ground_fb_skid`` – feller-buncher → grapple-skidder sequences automatically select the TN-261 helper with
  1.05 m³ piece size, 115 m forwarding distance, 8 % adverse slope, bunching enabled, and a 0.95 delay multiplier.
* ``ground_fb_loader_liveheel`` – same chain as ``ground_fb_skid`` but the loader job switches to the Barko 450 preset
  with ``--loader-barko-scenario ground_skid_block`` so interior live-heel loader ops inherit the TN-46 utilisation
  warning (96 % availability, 79 % utilisation, 17 % truck waits) automatically.
* ``ground_fb_shovel`` – coastal shovel-logging corridors pick the ADV5N1 helper (0–10 % slope class) with a 90 m
  forwarding distance plus the published payload/utilisation defaults (2.77 m³/cycle, 0.93 PMH/SMH).
* ``steep_tethered`` – tethered hot-logging layouts wire in the ADV2N26 clambunk regression with 320 m travel-empty
  distance, 18 stems per cycle, 1.35 m³ stem volume, and a 0.77 utilisation factor.

Overrides use the same keys as the CLI flags (``loader_model``, ``loader_piece_size_m3``, ``loader_distance_m``,
``loader_slope_percent``, ``loader_bunched``, ``loader_travel_empty_m``, ``loader_slope_class``, etc.). When one of
these presets applies, ``fhops.dataset`` prints a dimmed notice and telemetry captures the originating harvest system
so downstream costing/solver workflows retain provenance.

Coordinating with forwarder / skidder models
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Loader helpers should inherit the same assumptions as the upstream primary-transport phase so cost rollups stay
consistent:

* **Ground-based ghost trails (TN-261 + TN-285).** The TN-261 loader-forwarder study was paired with ghost-trail
  spacing and pre-bunched decks described in FPInnovations TN-285. If you call the TN-261 helper outside the
  harvest-system presets, mirror the same trail pattern you fed to the grapple-skidder helper
  (``TrailSpacingPattern.SINGLE_GHOST_18M`` corresponds to TN-285’s 18 m ghost trail layout). That keeps loader
  forwarding distance aligned with the average skid-trail spacing and prevents double counting of trail penalties.
* **Clambunk + hoe-forwarding chains (ADV2N26 + PNW-RP-430).** The ADV2N26 helper represents the Trans-Gesco TG88 /
  JD 892D-LC tandem documented again in Lambert & Howard’s PNW Research Paper 430. When modelling “hot logging”
  corridors where the clambunk hands off to a loader-forwarder, use the same stems-per-cycle and payload splits for
  both the clambunk helper and ADV2N26 loader helper so the landing payload is conserved. PNW-RP-430 also lists
  travel-speed penalties for steep trail networks; use those multipliers to adjust the ADV2N26 travel-empty distance
  before computing loader productivity.
* **Shovel-fed landings (ADV5N1).** ADV5N1 assumes the landing loader is fed by shovel logging or short skyline
  corridors. If the prior phase used the shovel logger helper, carry the same payload-per-swing and utilisation
  targets into the loader defaults so only one phase absorbs the congestion penalty.

These references are called out in ``notes/reference_log.md`` (entries for TN285.PDF and pnw_rp430.pdf) so analysts
can trace the provenance when tuning harvest systems.

Grapple Skidder Productivity Models
-----------------------------------

Ground-based full-tree systems can now call the Han et al. (2018) regressions via
``fhops.dataset estimate-productivity --machine-role grapple_skidder``:

* ``han2018-lop-scatter`` – delay-free cycle time for Tigercat 615C skidding delimbed logs in
  lop-and-scatter salvage. Requires ``--skidder-pieces-per-cycle`` (logs/turn),
  ``--skidder-piece-volume`` (m³/log), ``--skidder-empty-distance`` (m), and
  ``--skidder-loaded-distance`` (m). Payload is derived automatically and converted into m³/PMH0.
* ``han2018-whole-tree`` – same machine/stand, but moving whole trees to roadside decks. Replace the
  log count with trees per turn (same CLI flag) and supply average tree volume.

Both helpers report cycle time, payload per turn, and predicted productivity so analysts can adjust
the distance or payload assumptions directly.

Trail spacing and decking multipliers (from FPInnovations TN285 and ADV4N21) can be applied via
``--skidder-trail-pattern`` (``narrow_13_15m`` | ``single_ghost_18m`` | ``double_ghost_27m``) and
``--skidder-decking-condition`` (``constrained_decking`` | ``prepared_decking``). The defaults follow
TN285’s finding that 13–15 m trail spacing drove 20–40% higher extraction costs (≈25% productivity
penalty) while double-ghost 27–30 m layouts serve as the baseline. ADV4N21 reported decking-time
reductions from 1.33 to 0.60 min/cycle after clearing the landing; we translate that ~16% cycle-time
penalty into the ``constrained_decking`` multiplier. Analysts can stack these with an optional
``--skidder-productivity-multiplier`` when site-specific data is available.

Travel-speed assumptions now support GNSS data via ``--skidder-speed-profile``:

* ``legacy`` (default) – use the Han et al. (2018) regression coefficients for empty/loaded travel.
* ``gnss_skidder`` – replace the distance terms with the GNSS median speeds observed for cable skidders in Zurita &
  Borz (2025) (≈4.1 km/h empty, 3.9 km/h loaded).
* ``gnss_farm_tractor`` – same GNSS dataset but using the farm-tractor skidders (≈5.1 km/h empty, 3.6 km/h loaded).

CLI output notes which profile was used, and harvest-system templates can override the profile the same way they do
for trail/decking multipliers.

Harvest-system templates can now supply these overrides automatically: pass
``--harvest-system-id <system_id>`` (default registry or your scenario’s definitions) or
``--dataset <scenario-path> --block-id <block>`` to pull the block’s harvest system and apply its
``productivity_overrides`` for the grapple skidder job. The command prints when such defaults are
applied so you can verify which template influenced the result.

Grapple Yarder Productivity Models
----------------------------------

Cable-running systems can now call the grapple yarder regressions bundled in
``fhops.dataset estimate-productivity --machine-role grapple_yarder``:

* ``sr54`` – MacDonald (1988) SR-54 regression for a Washington 118A grapple yarder on mechanically
  bunched wood. Requires ``--grapple-turn-volume-m3`` and ``--grapple-yard-distance-m`` and includes
  the minor delay allowance from Table 10.
* ``tr75-bunched`` – Peterson (1987) TR-75 Madill 084 regression for mechanically bunched second
  growth. Uses the same CLI inputs; the helper applies the published outhaul/inhaul coefficients plus
  a fixed hook/unhook allowance.
* ``tr75-handfelled`` – Madill 084 handling hand-felled timber (TR-75 hand-felled regression). Use
  this when you need to reflect lower payload control or hand-bunched turns.

Every helper prints the assumed turn volume, yarding distance, and resulting m³/PMH. The
``cable_running`` harvest system autopopulates these inputs when you pass
``--harvest-system-id cable_running`` (or reference a dataset block using that system), selecting the
``tr75-bunched`` model with representative payload/distance values and printing a confirmation when
the defaults are applied.

Shovel Logger (Hoe-Chucker) Productivity
----------------------------------------

Primary-transport hoe chuckers are modeled through the Sessions & Boston (2006) serpentine model:

* ``shovel_logger`` role uses ``estimate_shovel_logger_productivity_sessions2006`` with inputs mirroring
  the paper (passes between roads, swing length, strip length, volume per hectare, swing times/payloads,
  and walking speeds). Invoke via ``fhops.dataset estimate-productivity --machine-role shovel_logger``.
* Key flags: ``--shovel-passes`` (number of swings), ``--shovel-swing-length``, ``--shovel-strip-length``,
  ``--shovel-volume-per-ha``, and the swing/velocity parameters. Defaults follow Table 1 of the paper
  (16.15 m swing, 375 m³/ha, 20–30 s swing times, 0.7 kph travel speeds, 50 productive minutes/hour).
* FPInnovations TN-261 data introduced slope/bunching multipliers: use ``--shovel-slope-class`` to apply
  downhill (×1.1), level (×1.0), or uphill (×0.9) adjustments, and ``--shovel-bunching`` to pick between
  feller-bunched (×1.0) or hand-scattered (×0.6) stems. Stack an optional ``--shovel-productivity-multiplier``
  for site-specific tweaks.

The helper reports cycle minutes, payload per cycle, and m³/PMH0 so you can test alternate swing counts or
strip lengths. Hook it into harvest-system templates by assigning the ``shovel_logger`` job and, if needed,
adding ``productivity_overrides`` for site-specific swing counts. Templates such as ``ground_hand_shovel`` and
``ground_fb_shovel`` already ship with overrides so the CLI automatically pulls their parameters when you pass
``--harvest-system-id`` or ``--dataset/--block-id``.

Skyline Productivity Models
---------------------------

Use ``fhops.dataset estimate-skyline-productivity`` when the block’s harvest system references
``skyline_yarder`` jobs. The command now accepts ``--harvest-system-id``, ``--dataset``, and ``--block-id`` so
defaults from the registry (e.g., ``cable_standing`` or ``cable_running``) or the current scenario flow directly
into the regressions. Available models:

* ``lee-uphill`` / ``lee-downhill`` – HAM300 case study (Lee et al. 2018, South Korea). Uphill only needs
  ``--slope-distance-m`` (calibrated 5–130 m); downhill also needs ``--lateral-distance-m`` (0–25 m) and
  ``--large-end-diameter-cm`` (~34 cm). The CLI emits a warning because these are short-span non-BC studies.
* ``tr125-single-span`` / ``tr125-multi-span`` – FPInnovations TR-125 standing skyline (Skylead C40 with Mini-Maki).
  Provide slope distance (10–420 m) and lateral distance (0–50 m). Payload defaults to 1.6 m³ (≈3.4 logs × 0.47 m³/log)
  but can be overridden; the CLI also prints the underlying cycle minutes so you can see the intermediate-support penalty.
* ``tr127-block1`` … ``tr127-block6`` – FPInnovations TR-127 block-specific tower-yarders. Blocks 1 & 3 require two
  lateral inputs (``--lateral-distance-m`` plus ``--lateral-distance-2-m``); Blocks 5 & 6 require ``--num-logs``.
  Range checks match the publication and the table output shows cycle minutes alongside m³/PMH.
* ``mcneel-running`` – McNeel (2000) Madill 046 longline running skyline. Requires horizontal span
  (``--horizontal-distance-m`` or reuses ``--slope-distance-m``), deflection (``--vertical-distance-m``), lateral distance,
  and optional ``--pieces-per-cycle`` / ``--piece-volume-m3`` plus ``--running-yarder-variant`` (Yarder A/B). Selecting
  ``--harvest-system-id cable_running`` pre-populates those inputs automatically.
* ``aubuchon-standing`` – Hensel et al. (1979) Wyssen standing skyline (Aubuchon 1982 Appendix A Eq. 15). Provide
  ``--logs-per-turn``, ``--average-log-volume-m3``, ``--crew-size``, slope, and lateral distance. Calibrated for 45–75 %
  corridors with 3.5–6 logs/turn; the CLI warns that it is a WA/ID dataset.
* ``aubuchon-kramer`` – Kramer (1978) standing skyline with carriage-height and chord-slope predictors. Supply
  ``--carriage-height-m`` and ``--chordslope-percent`` in addition to the Wyssen-style inputs; ``--harvest-system-id
  cable_standing`` applies 3.8 logs/turn, 0.45 m³/log, and −15 % chord slope defaults for coastal chokers.
* ``aubuchon-kellogg`` – Kellogg (1976) tower-yarder regression (Oregon) with lead-angle and choker-count predictors.
  Provide ``--lead-angle-deg`` and ``--chokers`` with the usual log/volume inputs; payloads are converted to cubic feet
  internally to match the source, and the CLI warns that it’s not BC data.

Helicopter longline work still lives under ``fhops.dataset estimate-productivity --machine-role helicopter_longline``.
Those helpers wrap FPInnovations Advantage/TR studies (Lama, K-Max, Bell 214B, S-64E) with ``--helicopter-model``,
``--helicopter-flight-distance-m``, payload/load-factor overrides, and per-cycle delay minutes. Selecting
``--harvest-system-id helicopter`` auto-loads a Bell 214B preset for quick estimates.

Every skyline model prints the assumed payload and m³/PMH0 result; the McNeel and Aubuchon helpers also show
delay-free cycle minutes so you can see the impact of deflection, carriage height, lead angle, or extra chokers.
Telemetry rows capture all skyline predictors (horizontal/vertical distance, pieces, piece volume, carriage height,
chord slope, lead angle, chokers, running-yarder variant) so harvest-system overrides are traceable.

CTL Harvester Productivity Models
---------------------------------

``fhops.productivity.harvester_ctl`` hosts the shortwood harvester regressions. The inaugural entry is
the ADV6N10 single-grip model:

* ``adv6n10`` – Gingras & Favreau (2005) boreal multi-product study. Use when operators sort several
  products per pass and need visibility into harvester-side penalties. Required CLI flags:
  ``--ctl-stem-volume`` (m³/stem), ``--ctl-products-count`` (number of products sorted per cycle),
  ``--ctl-stems-per-cycle``, and ``--ctl-mean-log-length`` (m). Invoke via
  ``fhops dataset estimate-productivity --machine-role ctl_harvester`` to see the ADV6N10 result.
* ``adv5n30`` – Meek (2004) ADV5N30 Alberta white-spruce thinning. Provides removal-level
  productivity (30/50/70 %) plus an optional ``--ctl-brushed`` flag (adds the observed 21 % boost
  when brush crews pre-clear). Supply ``--ctl-removal-fraction`` (0–1 within the 0.30–0.70 window)
  to interpolate between the published removal levels.
* ``tn292`` – Bulley (1999) TN292 Alberta thinning (Kenmatt/Brinkman). Models harvester
  productivity versus tree size and stand density. Requires ``--ctl-stem-volume`` (m³/stem),
  ``--ctl-density`` (trees/ha), and ``--ctl-density-basis`` (``pre`` or ``post`` harvest) to match the
  published regressions.
* ``kellogg1994`` – Kellogg & Bettinger (1994) western Oregon CTL thinning case (Timberjack 2518
  harvester). Supply ``--ctl-dbh-cm`` (study range 10–50 cm). The helper outputs delay-free m³/PMH
  so you can compare harvester productivity directly with the paired Kellogg forwarder models.
