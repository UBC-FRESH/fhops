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
   * - ``ground_salvage_grapple``
     - ground-based salvage
     - feller-buncher → grapple skidder → roadside processor → loader
     - ADV1N5 burned-timber salvage defaults (buck/sort fire damage, double-ring debarkers, charcoal controls) threaded into the grapple-skidder chain.
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
  * - ``cable_standing_tr125_single``
    - cable-standing skyline
    - hand/mech faller → standing skyline (TR125 single span) → landing processor → loader
    - Skylead C40 single-span defaults (1.6 m³ payload, 25 m lateral). Use when you want the TR125 helper and `grapple_yarder_skyleadc40` cost role.
  * - ``cable_standing_tr125_strip``
    - cable-standing skyline (intermediate supports)
    - hand/mech faller → standing skyline (TR125 multi-span) → landing processor → loader
    - Strip-cut defaults pulling the TR119 strip-cut treatment multiplier and setting lateral distance to 40 m (TN-258 warning auto-fires).
   * - ``cable_salvage_grapple``
     - cable-running salvage
     - hand/mech faller → grapple yarder → landing processor → loader
     - ADV1N5 salvage workflows for steep burned slopes (parallel bunching, grapple yarding, charcoal-aware processing) bundled into a cable-running preset.
   * - ``cable_running``
     - cable-running skyline
     - hand/mech faller → grapple yarder → landing processor/hand buck → loader
     - Grapple yarder variant with landing finishing.
  * - ``cable_running_adv5n28_clearcut``
    - cable-running skyline
    - hand/mech faller → long-span skyline → landing processor/hand buck → loader
    - ADV5N28 clearcut conversion (Madill 071 + Pow'-R Block replacing helicopter yarding).
  * - ``cable_running_adv5n28_shelterwood``
    - cable-running skyline
    - hand/mech faller → long-span skyline → landing processor/hand buck → loader
    - ADV5N28 irregular shelterwood conversion threading riparian corridors with full suspension.
  * - ``cable_running_fncy12``
    - cable-running skyline (intermediate supports)
    - hand/mech faller → skyline yarder → landing processor/hand buck → loader
    - Thunderbird TMY45 + Mini-Mak II preset (FNCY12/TN258). Selecting this system preloads the ``fncy12-tmy45`` helper so TN-258 lateral-distance warnings and Cat D8/Timberjack support ratios flow automatically.
    - Cost reference: see the Skyline cost matrix below (``grapple_yarder_tmy45``).
  * - ``cable_micro_ecologger``
    - cable-short-span skyline
    - hand faller → RMS Ecologger skyline → hand buck/processor → loader
    - TN173 NB case study (2.9 logs/turn, 0.34 m³ pieces, four-person crew) for compact skyline corridors.
  * - ``cable_micro_gabriel``
    - cable-short-span skyline
    - hand faller → Gabriel truck yarder → hand buck/processor → loader
    - TN173 Stephenville prototype skid-pan yarder (0.16 m³ stems, road-portable) with chokers and manual processing.
  * - ``cable_micro_christie``
    - cable-short-span skyline
    - hand faller → Christie tower yarder → hand buck/processor → loader
    - TN173 Christie hot-yarding configuration (two-person crew, 0.49 m³ pieces) for patch cuts.
  * - ``cable_micro_teletransporteur``
    - cable-short-span skyline
    - hand faller → Télétransporteur carriage → hand buck/processor → loader
    - TN173 Télétransporteur downhill hot-yarding (0.21 m³ pieces, self-propelled carriage) for riparian buffers.
  * - ``cable_micro_timbermaster``
    - cable-short-span skyline
    - hand faller → Smith Timbermaster skyline → hand buck/processor → loader
    - TN173 Timbermaster downhill skyline (0.54 m³ pieces, trailer tower) for small shortwood corridors.
  * - ``cable_micro_hi_skid``
    - cable-short-span skyline
    - hand faller → Hi-Skid yard/load/haul (direct to dump)
    - FNG73 Hi-Skid short-yard truck (100 m reach, 12 m³ deck); use ``--model hi-skid`` and optionally ``--hi-skid-include-haul`` when this system is selected.
    - Cost reference: ``skyline_hi_skid`` entry in the Skyline cost matrix.
  * - ``cable_partial_tr127_block1``
    - cable-standing skyline partial cut
    - hand/mech faller → standing skyline (TR127 Block 1) → landing processor → loader
    - Provides the dual lateral-distance defaults (15 m + 6 m) and now applies the SR109 patch-cut penalty (volume ×0.846, cost ×1.10) via the built-in partial-cut profile.
  * - ``cable_partial_tr127_block5``
    - cable-standing skyline partial cut
    - hand/mech faller → standing skyline (TR127 Block 5) → landing processor → loader
    - Sets 16 m lateral, 3 logs/turn, 1.6 m³ payload, and wires in the SR109 green-tree penalty (volume ×0.715, cost ×1.10) so telemetry logs the added cost/range limits automatically.
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

Scenario Cross-Links
--------------------

The sample datasets shipped in ``examples/`` reference these system IDs directly. Use the following
map when you need to trace a block back to the registry table above:

.. list-table::
   :header-rows: 1
   :widths: 20 35 45

   * - Scenario
     - Where to inspect
     - Notes
   * - ``examples/synthetic/{small,medium,large}``
     - ``data/blocks.csv`` (``harvest_system_id`` column) and ``README.md``
     - Every synthetic bundle assigns an explicit system ID per block. The README describes the
       terrain/prescription mix; look up the IDs in the table above to recover the associated job/role chain.
   * - ``examples/med42`` / ``examples/large84``
     - ``README.md`` and ``data/blocks.csv`` (terrain/prescription hints)
     - These scenarios omit ``harvest_system_id`` in order to let researchers swap systems during experiments.
       The README files call out the typical ground/cable combinations used in regression tests; add a column to
       ``data/blocks.csv`` if you need deterministic system assignments.
   * - ``examples/minitoy``
     - README + CLI quickstart
     - The toy dataset keeps a single ground-based workflow; tie blocks to ``ground_fb_skid`` or
       ``ground_hand_shovel`` when testing sequencing logic.

For any other dataset, run ``rg --no-heading 'harvest_system_id' path/to/blocks.csv`` to confirm whether
the IDs are specified. When missing, edit ``blocks.csv`` or include a ``harvest_systems`` block inside
``scenario.yaml`` so future contributors know which registry entries to reference.

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
* ``adv1n12-shortwood`` – Advantage Vol. 1 No. 12 extraction-distance regression for the Valmet 646
  forwarder (formula stored in ``data/productivity/forwarder_skidder_adv1n12.json``). Provide
  ``--extraction-distance`` (m); the helper reports the decay curve (8.4438·e^(−0.004·d)) plus the
  usual PMH0 output. Use when road spacing dictates forwarding distances between roughly 150–600 m
  and you want the published optimum (~400 m) reflected in your sensitivity runs.
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

Harvest-system templates now include two ADV1N12 presets:

* ``thinning_adv1n12_forwarder`` – sets the forwarder model to ``adv1n12-shortwood`` with a default
  350 m extraction distance (mirroring the Advantage curves) and uses the Valmet 646 machine-rate
  entry (owning 18.85 $/SMH + operating 45.73 $/SMH in 1999 CAD, automatically inflated to the
  CLI target year). Selecting this system via ``--harvest-system-id`` or dataset blocks pre-fills
  the forwarder CLI inputs and `--show-costs` reports the CPI-adjusted Appendix 1 cost split.
* ``thinning_adv1n12_fulltree`` – wires the lop-and-scatter Timberjack 240 skidder preset (see
  the grapple-skidder section) so planners can contrast the shortwood vs. full-tree options without
  retyping the Advantage extraction distances.

Roadside Processor Productivity Models
--------------------------------------

Landing processor and loader coverage cheat sheet
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following tables summarise which preset to grab for common BC case-study scenarios. Use them as
a quick index before diving into the per-model notes.

.. list-table:: Landing processor presets (region + utilisation snapshot)
   :header-rows: 1
   :widths: 18 30 20 32

   * - Model flag
     - Region / primary deployment
     - Key inputs & utilisation
     - Notes
   * - ``adv5n6``
     - Coastal BC – Madill 3800 + Waratah HTH624 (loader-forwarded cold decks vs. grapple-fed hot decks).
     - Stem source + processing mode select PMH/SMH and CPI-scaled $/m³ (≈0.73 utilisation baked in).
     - Use when replaying ADV Vol. 5 No. 6 landings; hot decks mirror yarder waits, low-volume mode captures small swing camps.
   * - ``tn166``
     - Interior BC – Denis D3000 telescopic boom stroke processor (grapple-yarded vs. right-of-way vs. mixed shift).
     - Scenario flag picks utilisation (≈0.78–0.87) and CPI-normalised costs.
     - Handy for stroke-processor partial cuts or right-of-way clean-up.
   * - ``tr87`` / ``tr106`` / ``tn103``
     - Legacy BC roadside CTL / partial cut (TJ90 twin processors, Steyr KP40 variants, Cat DL221 stroke).
     - Scenario selector prints PMH, SMH, and CPI-normalised costs; no extra numeric inputs.
     - Pair coastal TR-87/TN-103 for Vancouver Island/Haida Gwaii studies and TR-106 for Cariboo shelterwoods.
   * - ``berry2019``
     - Kinleith, NZ (purpose-built processor baseline). Useful surrogate when BC dimensions match Berry’s 1–3 m³ stems.
     - Needs piece size, tree-form, crew multiplier, delay multiplier (default 0.91); carrier option auto-adjusts utilisation.
     - Serves as general landing processor baseline when local BC data is unavailable but piece-size inputs are known.
   * - ``labelle2016``/``2017``/``2018``/``2019_*``
     - Eastern Canadian / Bavarian hardwoods (DBH or recovered volume regressions, PMH₀ only).
     - Require DBH or recovered volume plus species/treatment/variant; always supply a utilisation multiplier for BC use.
     - Treat outputs as delay-free references for export markets or hardwood-heavy BC trials; not calibrated for conifer landings.
   * - ``visser2015``
     - NZ cable landings (Cat 330DL + Waratah) focused on log-sort complexity.
     - Requires piece size (1–3 m³) and log-sort count; utilisation multiplier defaults to 0.91.
     - Quick way to quantify productivity loss when chasing >5 log sorts at coastal BC cable yards.
   * - ``hypro775``
     - Tractor-mounted processor (Castro Pérez 2020; Zurita 2021) for thin-wood landings.
     - No extra inputs; default utilisation ≈0.73 with noise/ergonomic warnings.
     - Use for small private-land salvage or community forest pilots where capital limits rule out large processors.
   * - ``bertone2025`` / ``spinelli2010``
     - European excavator processors at cable landings (Italian Alps) with heavy yarder waits.
     - Need DBH/height/log count/piece size (Bertone) or tree volume + machine power + slope + stand info (Spinelli); utilisations baked in.
     - Helpful for steep-slope BC pilots with winch-assist yarders or when benchmarking against European CTL standards.
   * - ``borz2023`` / ``nakagawa2010``
     - Landing harvester-as-processor (Romania) and excavator-based processor (Hokkaido thinning).
     - Borz needs no inputs (optionally piece size); Nakagawa accepts DBH or per-tree volume plus a delay multiplier.
     - Use to bound harvester bucking scenarios or shovel-processor deployments when only tree dimensions are known.

.. list-table:: Loader / hoe-forwarder presets (BC defaults)
   :header-rows: 1
   :widths: 18 30 20 32

   * - Model flag
     - Region / primary deployment
     - Key inputs & utilisation
     - Notes
   * - ``tn261``
     - Interior BC loader-forwarder (Hoe-chucking) reference.
     - Requires piece size, forwarding distance, slope %, bunched flag, and delay multiplier (utilisation default = delay-free).
     - Baseline for hoe-chucking between road and landing; pair with TN285 trail spacing notes.
   * - ``adv5n1``
     - Coastal BC Madill 3800 shovel-forwarder (ADV5N1 Figure 9).
     - Inputs: forwarding distance, slope class (0–10 % vs. 11–30 %), payload, optional utilisation override (default ≈0.93).
     - Captures shovel-fed loader operations for roadside decking or short forwarding legs.
   * - ``adv2n26``
     - Clambunk/hoe-forwarding combo (Trans-Gesco TG88 + JD 892D-LC) from ADV2N26.
     - Needs travel empty distance, stems per cycle, stem volume, utilisation (default 0.87) plus optional in-cycle delays.
     - CLI prints soil-disturbance stats (20.4 % trail occupancy) so planners can track disturbance budgets.
   * - ``barko450``
     - TN-46 Barko 450 heel-boom loader (ground-skid vs. cable block).
     - Scenario flag selects utilisation (0.79 default) and CPI-inflated machine rate; optional `--loader-utilisation` rescales cost per m³.
     - Use for live-heel truck loading at coastal BC landings; cost role flows through `inspect-machine`.
   * - ``kizha2020``
     - Biomass/bucket loader reference (hot vs. cold loading) from Maine study.
     - Mode flag sets utilisation (55 % hot vs. 7 % cold) and costs; no other inputs.
     - Handy for demonstrating hot-deck decoupling costs or biomass operations; not BC-calibrated but informative.

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
  * ``--processor-skid-area-m2`` – optional landing skid-area flag. When provided, the CLI evaluates Berry’s
    Figure 11 regression (≈2,600–3,700 m² range) to predict delay seconds per stem and, if you have not supplied
    ``--processor-delay-multiplier``, auto-scales utilisation to reflect the larger/smaller landing. The command
    also prints the predicted m³/PMH hint and warns when your skid area lies outside the study range.
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
* ``--processor-model adv7n3`` – FPInnovations Advantage Vol. 7 No. 3 (Canfor Mackenzie summer
  skyline settings). Set ``--processor-adv7n3-machine`` to ``hyundai_210`` or ``john_deere_892`` to
  pull the observed shift/detailed productivity plus the processor-only vs. loader-only vs. combined
  $/m³ costs (2004 CAD and CPI-adjusted 2024 CAD). CLI output also prints the loader task breakdown,
  non-processing time penalties when the processor works without a loader, and the average travel
  distances so you can decide when a loader is mandatory on short-wood cable decks.

  Harvest-system presets `cable_running`, `cable_running_adv5n28_clearcut`, and
  `cable_running_adv5n28_shelterwood` now default to this model (Hyundai 210LC for the base/shelterwood
  runs, John Deere 892 for the clearcut conversion). Invoke ``--harvest-system-id <id>`` (or point to a
  dataset block using those systems) and the CLI auto-selects the right ADV7N3 machine, prints the
  Advantage citation, and emits the CPI-adjusted processor + loader costs without retyping any flags.
* ``--processor-model hypro775`` – HYPRO 775 tractor-mounted double-grip processor preset sourced from Castro
  Pérez (2020) and Zurita Vintimilla (2021). No additional predictors are needed; the helper reports mean cycle time
  (~45 s), gross/net trees per hour, delay-free m³/PMH (~21.4), fuel use (≈21 L/h or 0.78 L/m³), and ergonomic notes
  (≈85 dB(A), heavy-work cardiovascular load). Use this when modelling tractor-mounted landing processors in
  small-diameter thinnings or low-investment deployments.
* ``--processor-model bertone2025`` – Bertone & Manzone (2025) excavator-processor case study serving a cable yarder landing in the
  Italian Alps. Provide ``--processor-dbh-cm``, ``--processor-tree-height-m``, ``--processor-logs-per-tree`` (2–5), and
  ``--processor-piece-size-m3`` for the tree volume; the helper evaluates the published cycle-time regression and reports delay-free vs.
  observed productivity (≈25.9 vs. 14.8 m³/h), fuel (~16.5 L/SMH), and €-denominated owning costs with the 48 % yarder-wait penalty.
* ``--processor-model spinelli2010`` – Spinelli, Hartsough & Magagnotti’s Italian CTL productivity standards
  (Forest Products Journal 60(3):226–235). Choose between harvest (in-stand) and landing-processing modes via
  ``--processor-spinelli-operation`` and supply the tree volume (``--processor-piece-size-m3``), carrier power
  (``--processor-machine-power-kw``), slope (``--processor-slope-percent``), stand type, carrier/head/species flags,
  and (for harvest) the removals/residuals per hectare. The helper applies the published accessory (14.7/29.6 %)
  and delay (50/21/44 %) ratios automatically and prints the per-element cycle times so you can see how slope,
  carrier choice, and species mix influence delay-free PMH outputs.
* ``--processor-model borz2023`` – Borz et al. (2023) single-grip harvester bucking at a Romanian landing. No extra
  inputs are needed beyond the optional ``--processor-piece-size-m3`` for reference; the helper reports the observed
  averages (≈21.4 m³/PMH, 18.8 m³/SMH, 0.047 PMH/m³, 0.78 L/m³ fuel, 10–11 EUR/m³ cost, 95 % recovery) so planners can
  benchmark “harvester-as-processor” landing operations against manual or excavator-based options.
* ``--processor-model nakagawa2010`` – Nakagawa et al. (2010) excavator-based processor (Timberjack 746B carrier with Komatsu PC138US) working at a Hokkaido landing. Supply at least one predictor:
  * ``--processor-dbh-cm`` – applies the published delay-free regression 0.363·DBH\ :sup:`1.116` (DBH in cm).
  * ``--processor-piece-size-m3`` – applies the alternative regression 20.46·V\ :sup:`0.482` (tree volume in m³).
  * ``--processor-delay-multiplier`` – optional utilisation factor so you can fold landing waits into the PMH₀ baseline (defaults to the global processor multiplier; set to ``1.0`` to stay delay-free).
  CLI output states which regression ran, prints the delay-free m³/PMH alongside your utilisation-adjusted result, and cites the Japanese thinning context so you can benchmark excavator-based landing processors handling ≈0.25 m³ stems.
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
* `fhops dataset adv2n21-summary --treatment partial_cut_2` – surfaces the ADV2N21 Timberjack 1270/1010
  partial-cut costs (1997 CAD $/m³), CPPA terrain classes, and pre/post stand metrics for each patch/partial/
  clearcut block. Handy when you need to cite the +11 %…+78 % cost penalties for patch cuts or quantify
  the wildlife-corridor snow constraints before tuning forwarder defaults.
* ``--processor-automatic-bucking`` – Optional switch for *Berry*/*Labelle* helpers that applies the
  +12.4 % delay-free productivity multiplier from Labelle & Huß (2018, Silva Fennica 52(3):9947) and
  prints the associated €3.3/m³ revenue delta (2018 EUR) for traceability. The flag is ignored for the
  table-driven FPInnovations presets because those studies didn’t use the on-board bucking optimizer.

CLI output reports the base delay-free productivity, the applied multipliers, and the utilisation-adjusted
m³/PMH so costing workflows can decide which value to pass downstream. Remember that the Labelle models
were calibrated outside BC—treat them as hardwood export presets and rely on the Berry helper for mixed
or conifer-dominated BC blocks.

Burned-Timber Salvage Guidance (ADV1N5)
---------------------------------------

`fhops.dataset adv1n5` does not exist because the study is qualitative, but the skyline/forwarder presets
inherit the following cautions from ADV1N5 (Alberta 2000 salvaging workshop + case studies). Use these
checklists whenever you point `cable_running*`, `ground_fb_*`, or custom salvage systems at burned timber:

* **Log preparation** – buck out catfaces, scars, rotten butts, and heavily charred sections; raise the
  acceptable minimum top diameter; sort log decks by burn severity so dirty sorts can be chipped or wasted
  separately.
* **Debarking** – double-ring (counter-rotating) debarkers or a Cambio + Nicholson tandem remove charcoal
  reliably; alternate cutter/winter tips, slow the infeed ≥10 %, and recycle logs for multiple passes when
  residue remains.
* **Charcoal dust** – spray logs pre-debarker when temperatures allow, otherwise install vac/baffle systems,
  pressurize MCC rooms, and mandate PPE + aggressive greasing schedules to keep dust from destroying rings,
  bearings, and control panels.
* **Priorities** – harvest small-diameter or severely burned stands first (moisture loss + insect attack),
  and route environmentally sensitive slopes/gullies to grapple yarders (e.g., the Madill 122 case delivered
  300–400 m³/10 h once stems were bunched parallel to the slope).
* **Processing capacity** – deploy portable mills at satellite yards or in-woods chip plants for small stems
  when permanent mills cannot expand fast enough; burn or isolate slab/char waste so pulp furnish stays clean. Use
  ``--salvage-processing-mode`` (``standard_mill`` | ``portable_mill`` | ``in_woods_chipping``) when calling
  ``ground_salvage_grapple`` or ``cable_salvage_grapple`` to print the appropriate reminder in the CLI output, and
  store the selected mode in ``blocks.csv`` via the ``salvage_processing_mode`` column so downstream scenario tooling
  and telemetry inherit the same warning set automatically.

Document any of these mitigations in scenario metadata (telemetry note, `--harvest-system-id` description, etc.)
when you model salvage corridors so downstream QA knows why costs/utilisation differ from green-timber runs. The
new ``ground_salvage_grapple`` and ``cable_salvage_grapple`` harvest systems simply bundle the same checklist so you
can select them via ``--harvest-system-id`` without rewriting the warnings.

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

* ``ground_fb_skid`` – feller-buncher → grapple-skidder sequences now pin the ADV6N7 Caterpillar 535B preset
  (85 m extraction distance, loader-supported decking mode, 0.4 support ratio, 7.69 m³ payload, 0.12 min delays,
  0.85 utilisation) and the loader job still defaults to the TN-261 helper with 1.05 m³ logs, 115 m forwarding
  distance, 8 % adverse slope, bunching enabled, and a 0.95 delay multiplier.
* ``ground_fb_loader_liveheel`` – same chain as ``ground_fb_skid`` but the loader job switches to the Barko 450 preset
  with ``--loader-barko-scenario ground_skid_block`` so coastal/interior live-heel conversions inherit the TN-46
  utilisation warning (96 % availability, 79 % utilisation, 17 % truck waits) automatically while the grapple-skidder
  leg still leverages the ADV6N7 defaults.
* ``ground_salvage_grapple`` – pairs the ADV6N7 grapple-skidder preset with the ADV1N5 salvage guidance (buck out
  catfaces, raise minimum tops, double-ring debarkers, charcoal-dust controls). Use this when modelling burned-timber
  corridors that follow the salvage checklist in the section below.
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

* ``adv1n12-fulltree`` / ``adv1n12-two-phase`` – Delay-free extraction curves from Advantage Vol. 1
  No. 12 (see ``data/productivity/forwarder_skidder_adv1n12.json``). Supply
  ``--skidder-extraction-distance`` (m) and the CLI evaluates the exponential (integrated lop-and-
  scatter crew) or logarithmic (decoupled second-phase skidder) regression. Use these when spacing
  roads 100–350 m apart in commercial thinnings and you want the published productivity-distance
  relationships without retyping the equations.
* ``adv6n7`` – Caterpillar 535B grapple skidder regression (Advantage Vol. 6 No. 7). Provide
  ``--skidder-extraction-distance`` plus optional ``--skidder-adv6n7-*`` flags (decking mode, payload,
  utilisation, delay, support ratio). Defaults mirror the Englewood case study (7.69 m³ turns, 0.85
  utilisation, 0.12 min delay, loader support ratio 0.4). The CLI prints CPI-adjusted skidding cost and
  combined skid+deck cost so you can compare directly with loader-forwarding baselines.
* ``adv1n35`` – Owren 400 hydrostatic yarder regression (Advantage Vol. 1 No. 35). Provide
  ``--grapple-yard-distance-m`` plus the new knobs ``--grapple-lateral-distance-m`` and
  ``--grapple-stems-per-cycle`` (defaults 11 m and ≈2.6–2.8 stems/turn). Optional
  ``--grapple-in-cycle-delay-minutes`` lets you override the observed 0.69 min delay allowance. The CLI
  reports the assumed values and productivity so you can mirror the 200–350 m two-span corridors
  featured in the study when exploring interior skyline layouts.
* ``adv1n40`` – Madill 071 running/scab skyline regression (Advantage Vol. 1 No. 40). Supply
  ``--grapple-yard-distance-m`` (default 103 m) and optional ``--grapple-in-cycle-delay-minutes`` (default
  1.10 min). Turn volume defaults to 2.9 m³ unless overridden. Designed for downhill group-selection
  blocks in ICHvk1; the helper prints the CPI-adjusted $/m³ yarding cost from the publication.

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

The new ADV1N12 options ignore the trail/decking multipliers (the regressions already embed those
effects). When the CLI detects an ADV1N12 model it switches the output table to a condensed format
that simply lists the model, extraction distance, and predicted m³/PMH for the selected regression.

Select ``--harvest-system-id thinning_adv1n12_fulltree`` to auto-populate the ``adv1n12-fulltree``
model, a representative 225 m extraction distance, and the Timberjack 240 machine-rate entry
(12.33 $/SMH owning + 63.28 $/SMH operating in 1999 CAD, CPI-adjusted inside ``--show-costs``).

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
* ``tn157`` – Observed productivity/costs from TN-157 (Cypress 7280B swing yarder + Hitachi UH14 backspar).
  Select a case with ``--tn157-case`` (``combined`` default, or ``1``–``7`` to pull an individual study).
  The helper reports the observed turn volume, yarding distance, m³/PMH, and both 1991 CAD and CPI-inflated $/m³
  so costing workflows can drop the Cypress preset in immediately. Adding ``--show-costs`` now references the
  `grapple_yarder_cypress7280` machine-rate entry (FERIC TN-157 Appendix II) so the CLI prints the BC swing-yarder
  owning/operating split inline; ``inspect-machine --machine-role grapple_yarder_cypress7280`` surfaces the same table
  for planning docs.
* ``tn147`` – Observed productivity/costs from TN-147 (seven Madill 009 highlead case studies around Lake Cowichan).
  Pick a case with ``--tn147-case`` (``combined`` default) to pull the corresponding logs/turn, turn volume, and
  1989 CAD cost per log/m³; the CLI inflates the costs to 2024 CAD alongside the original values and, when you add
  ``--show-costs``, it now references the TN-147 machine-rate entry ``grapple_yarder_madill009`` so the owning/operating
  split matches the Madill 009 helper automatically.
* ``tr122-extended`` / ``tr122-shelterwood`` / ``tr122-clearcut`` – Observed Washington SLH 78 running-skyline
  productivity from TR-122 (Roberts Creek alternative silviculture project). These presets don’t require new inputs:
  the CLI reports the published cycle volume, m³/PMH, and the yarder/loader/labour cost breakdowns (1996 CAD plus
  CPI-inflated 2024 CAD equivalents) so you can reference the extended-rotation vs. shelterwood vs. clearcut costs.
* ``adv5n28-clearcut`` / ``adv5n28-shelterwood`` – Long-distance skyline conversions from ADV5N28 (Madill 071 +
  Acme 200 Pow’-R Block carriage substituting helicopter plans near Lillooet). These presets pull the observed turn
  volume, 375–725 m downhill yarding distances, m³/PMH, and the 2002 CAD costs for both the actual study and the
  projected skyline-vs-helicopter scenarios so you can quantify the savings relative to the $60/m³ heli baseline. When
  you add ``--show-costs`` (or call ``inspect-machine --machine-role grapple_yarder_adv5n28``) the CLI now references
  the ADV5N28 Madill 071 owning/operating split (289.77 $/SMH total from the Appendix II cost table) instead of the
  generic swing-yarder placeholder, keeping the skyline costing consistent with the study.

Every helper prints the assumed turn volume, yarding distance (when available), and resulting m³/PMH. Dataset-driven
presets (TN-147/TN-157/TR-122) also surface the observed case name and CPI-adjusted costs so you can drop them directly
into costing workflows without reopening the PDFs. The
``cable_running`` harvest system autopopulates these inputs when you pass
``--harvest-system-id cable_running`` (or reference a dataset block using that system), selecting the
``tr75-bunched`` model with representative payload/distance values and printing a confirmation when
the defaults are applied. Use ``cable_running_adv5n28_clearcut`` or
``cable_running_adv5n28_shelterwood`` when modelling the ADV5N28 long-span conversions—those presets
swap in the new helper automatically and reuse the same skyline defaults, so you can flip helicopter
blocks to skyline without retyping payload/cost assumptions.

Short-span presets ``cable_micro_ecologger``, ``cable_micro_gabriel``, ``cable_micro_christie``,
``cable_micro_teletransporteur``, and ``cable_micro_timbermaster`` now drive the TN173 skyline
models (crew size, pieces/turn, and the correct machine-rate role) automatically, so selecting one of
those systems drops the matching Eastern Canada helper into the CLI without retyping parameters. The
``cable_micro_hi_skid`` preset does the same for the FNG73 Hi-Skid truck—selecting that harvest
system funnels ``--model hi-skid`` defaults into the skyline CLI, and you can append
``--hi-skid-include-haul`` when you want the reported productivity to fold in the 30 min haul/unload
leg per 12 m³ load.

Use ``cable_salvage_grapple`` when those skyline corridors are salvaging burned timber: it mirrors the
``cable_running`` payload defaults (TN-157 combined preset + ADV7N3 deck costs) but tags the scenario as a salvage
operation so the ADV1N5 cautions (parallel bunching, grapple yarding rough ground, charcoal controls) are baked into
the harvest-system notes and telemetry.

Grapple harvest-system presets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: Grapple harvest-system summary
   :widths: 25 20 25 30
   :header-rows: 1

   * - Harvest system ID(s)
     - Linked model(s)
     - Default inputs
     - Cost role / notes
   * - ``cable_running`` / ``cable_running_tn157_combined``
     - ``tn157`` + ``mcneel-running`` skyline swap
     - 3.8 m³ turns, 83 m yarding distance, ≈3 pcs/turn, Douglas-fir 52.5 cm manual falling
     - `grapple_yarder_cypress7280` when ``--show-costs`` is enabled; baseline Cypress swing-yard case from TN-157.
   * - ``cable_highlead_tn147``
     - ``tn147`` (Madill 009 highlead)
     - 5.5 m³ turns, 138 m average reach, ≈2.1 pcs/turn, manual falling defaults tuned to TN-147
     - `grapple_yarder_madill009` CPI-aware rate; CLI output also prints the 1989 $/m³ cost column from TN-147.
  * - ``cable_running_tr122_extended`` / ``_shelterwood`` / ``_clearcut``
    - ``tr122-extended`` | ``tr122-shelterwood`` | ``tr122-clearcut``
    - 2.04/2.18/1.45 m³ turns, 104 m / 97 m / 106 m reach, observed pieces-per-cycle (2.2/3.2/2.6)
    - Uses the generic ``grapple_yarder`` cost role; the shelterwood preset now also applies the SR109 shelterwood penalty (volume ×0.495, cost ×1.38) via the partial-cut profile, while the extended/clearcut entries remain unchanged. CLI prints the TR-122 yarder/loader labour breakdown so you still see the published $/m³ numbers.
   * - ``cable_running_sr54``
     - ``sr54`` (Washington 118A running skyline regression)
     - 3.1 m³ turns, 82 m reach, ≈2.9 pcs/turn fed by the feller-buncher preset
     - Falls back to the generic ``grapple_yarder`` rate; rely on SR-54’s CPI-adjusted output or override the machine role if you have a local rental.
   * - ``cable_running_tr75_bunched`` / ``_handfelled``
     - ``tr75-bunched`` (System 1) / ``tr75-handfelled`` (System 2)
     - 1.29 m³ @ 71 m and 1.28 m³ @ 76.6 m, 2.18 vs. 1.41 pcs/turn (mechanical vs. hand-felled)
     - Generic ``grapple_yarder`` cost role; CLI still reports the 1987 $/m³ numbers from TR-75.
   * - ``cable_running_adv5n28_clearcut`` / ``_shelterwood``
     - ``adv5n28-clearcut`` | ``adv5n28-shelterwood``
     - 2.2 m³ @ 480 m and 1.8 m³ @ 330 m plus skyline/helicopter comparison rows
     - `grapple_yarder_adv5n28` cost role; banner also shows projected skyline vs. helicopter savings.
   * - ``cable_running_fncy12``
     - ``fncy12-tmy45`` standing-in for the Thunderbird TMY45 + Mini-Mak II intermediate-support study
     - 3.6 logs/turn, 176 m shift productivity, Cat D8/Timberjack support ratios baked into telemetry
     - `grapple_yarder_tmy45` CPI-aware rate (Cat D8 + Timberjack standby surcharges included); CLI warns whenever lateral pulls exceed the TN-258 tension envelope.
   * - ``cable_salvage_grapple``
     - ``tn157`` (Cypress) defaults + ADV1N5 salvage cues
     - Same payload/distance as ``cable_running`` with salvage-mode telemetry tags
     - Uses `grapple_yarder_cypress7280`; CLI/telemetry also carry the salvage processing mode.

Manual falling overrides follow the study provenance: TN-147/TN-157/ADV5N28 systems default to Douglas-fir 52.5 cm,
the Roberts Creek TR-122 presets drop to 40 cm, and TR-75 hand-felled keeps a 45 cm reference. Mechanically bunched
options (SR-54, TR-75 System 1) switch the felling job to ``feller-buncher`` so no manual falling cost is injected unless
you explicitly request it. All of the new IDs appear in the medium/large synthetic tier mixes so the helper defaults
flow into generated scenarios (and their machine cost banners) automatically.

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
  Pair these presets with ``inspect-machine --machine-role grapple_yarder_skyleadc40`` (FERIC TN-201 cost entry) when
  modelling Skylead corridors. FNCY12/TN-258 Thunderbird spans should reference
  ``grapple_yarder_tmy45``—its operating column now bundles the LeDoux (1984) yarder cost *plus* the
  FNCY12-derived support-machine surcharges (0.3335 SMH Cat D8 backspar + 0.2415 SMH Timberjack 450 trail support per
  productive yarder hour, see :ref:`tn258_support_method`) so ``--show-costs`` reflects the extra gear those corridors
  require. Whenever lateral pulls exceed ~30 m or skyline tension approaches the 140 kN ceiling documented in TN-258,
  ``estimate-skyline-productivity`` now prints a TN-258 warning and logs the skyline/guyline ratios (data lives in
  ``data/reference/fpinnovations/fncy12_tmy45_mini_mak.json``) so analysts can flag hang-up risks alongside the costing
  output.
* ``fncy12-tmy45`` – Thunderbird TMY45 + Mini-Mak II intermediate-support skyline (FNCY-12 / TN-258). The helper reports
  the observed shift output (default = steady-state months) divided by the 10 h shift to give m³/PMH and records the Cat D8 /
  Timberjack support ratios derived from FNCY12 Tables 2–3 (see :ref:`tn258_support_method` for the full derivation). Use
  ``--fncy12-variant`` to swap between ``overall``, ``steady_state``, or ``steady_state_no_fire`` averages, and keep
  ``--lateral-distance-m`` at or below 30 m if you want to stay inside the measured tension envelope—lateral pulls beyond
  that trigger the TN-258 warning automatically and mark the telemetry row so downstream costing knows hang-ups are likely. The
  dataset’s ``support_monthly_summary`` enumerates July (learning/no supports) versus the August–October support months with yarder
  SMH and the inferred Cat D8/Timberjack SMH, giving analysts a reproducible “supports vs. no supports” split even though TN-258
  never published stopwatch utilisation.
* ``ledoux-skagit-shotgun`` / ``ledoux-skagit-highlead`` / ``ledoux-washington-208e`` / ``ledoux-tmy45`` – LeDoux (1984) residue yarding regressions (Willamette & Mt. Hood studies). Supply slope distance plus ``--merchantable-logs-per-turn``, ``--merchantable-volume-m3``, ``--residue-pieces-per-turn``, and ``--residue-volume-m3``. Outputs report total payload, cycle minutes, and CPI-adjusted 1984 USD cost references (see ``inspect-machine --machine-role grapple_yarder_skagit_shotgun|_highlead|_washington_208e|_tmy45_residue``). These models represent US residue trials—treat as comparative benchmarks rather than BC defaults.
* ``micro-master`` – Model 9 Micro Master yarder regression (FERIC TN-54, 1982). Defaults assume 3.2 pieces per turn (0.46 m³/piece) and the observed 5.96 min cycle at the 70 m spans logged on Vancouver Island. Supply ``--slope-distance-m`` (and optionally ``--pieces-per-cycle``, ``--piece-volume-m3``, or ``--payload-m3``) to see the computed payload, cycle minutes, and productivity; useful for compact skyline/thinning setups where Madill/Cypress presets are overkill.
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
  cable_standing`` applies 3.8 logs/turn, 0.45 m³/log, and −15 % chord slope defaults for coastal chokers. The trials only
  observed chord slopes between −22 % (downhill) and +3 % (slight uphill), so the helper now warns/flags telemetry when
  you stray outside that envelope.
* ``aubuchon-kellogg`` – Kellogg (1976) tower-yarder regression (Oregon) with lead-angle and choker-count predictors.
  Provide ``--lead-angle-deg`` and ``--chokers`` with the usual log/volume inputs; payloads are converted to cubic feet
  internally to match the source, and the CLI warns that it’s not BC data. Lead angles were limited to ±90° and the study
  only used 1–2 chokers per turn, so the helper now prints/telemeters calibration warnings whenever those values drift.

Helicopter longline work still lives under ``fhops.dataset estimate-productivity --machine-role helicopter_longline``.
Those helpers now read from ``data/productivity/helicopter_fpinnovations.json`` (ADV3/4/5/6 series) so each model has a
reference preset plus a matching machine-rate role:

* ``--helicopter-model`` accepts ``lama``, ``kmax``, ``bell214b``, ``ka32a`` (Kamov KA-32A pole logging), or
  ``s64e_aircrane``. When ``--helicopter-preset`` is omitted, the CLI applies the default preset for that model
  (marked with ★ in ``fhops.dataset helicopter-fpinnovations``); specify a preset ID (e.g.,
  ``s64e_grapple_retention_adv5n13``) to seed the flight distance, payload, load-factor, weight→volume, and delay minutes
  directly. The CLI and telemetry banner call out whichever preset supplied the defaults so downstream costing can audit
  the assumption.
* ``fhops.dataset helicopter-fpinnovations`` lists every preset, the observed m³/shift, turn times, and CPI metadata. Add
  ``--operation-id <preset>`` to view the full cycle breakdown and scan notes without reopening the PDFs.
* ``--show-costs`` now hooks into the CPI-aware helicopter machine-rate entries
  (``helicopter_lama``/``_kmax``/``_bell214b``/``_ka32a``/``_s64e_aircrane``) so heavy/medium/light lift cost banners
  cite the FPInnovations Appendix-II splits directly. ``inspect-machine --machine-role helicopter_s64e_aircrane`` (etc.)
  surfaces the same rates outside the productivity helper.

Selecting ``--harvest-system-id helicopter`` still applies the Bell 214B defaults, but the new preset plumbing means
Mission-style Aircrane or KA-32A pole-logging runs can be reproduced without hand-entering the published flight
distance/payload values.

Every skyline model prints the assumed payload and m³/PMH0 result; the McNeel and Aubuchon helpers also show
delay-free cycle minutes so you can see the impact of deflection, carriage height, lead angle, or extra chokers.
Telemetry rows capture all skyline predictors (horizontal/vertical distance, pieces, piece volume, carriage height,
chord slope, lead angle, chokers, running-yarder variant) so harvest-system overrides are traceable.
Append ``--show-costs`` to print the CPI-adjusted machine-rate summary for any preset that has a matching entry in
the Skyline cost matrix below.

TR-127 predictor ranges
~~~~~~~~~~~~~~~~~~~~~~~

Use the table below when selecting the block-specific TR-127 presets. Blocks differ in their required inputs and the
calibrated ranges of those inputs (from Appendix VII of TR-127). Values outside these ranges still compute but the CLI
emits calibration warnings and telemetry flags the deviation.

.. list-table:: TR-127 block summary
   :widths: 10 20 35 35
   :header-rows: 1

   * - Block
     - Scenario
     - Required predictors
     - Calibrated range(s)
   * - 1
     - Cedar partial cut (two lateral pulls)
     - ``latd`` (primary lateral), ``latd2`` (secondary lateral)
     - ``latd`` 0–8 m; ``latd2`` 0–8 m
   * - 2
     - Spruce clearcut
     - ``sd`` (slope distance)
     - ``sd`` 225–770 m
   * - 3
     - Steep partial cut
     - ``latd`` (lateral distance)
     - ``latd`` 0–65 m
   * - 4
     - Small lateral, coastal block
     - ``latd`` (lateral distance)
     - ``latd`` 0–40 m
   * - 5
     - Mixed partial cut (IFN block)
     - ``sd`` (slope distance), ``latd`` (lateral), ``logs`` (logs/turn)
     - ``sd`` 70–650 m; ``latd`` 0–80 m; ``logs`` 1–10
   * - 6
     - Long-span partial cut (north block)
     - ``sd`` (slope distance), ``latd`` (lateral), ``logs`` (logs/turn)
     - ``sd`` 265–716 m; ``latd`` 0–75 m; ``logs`` 1–7

Skyline cost matrix
-------------------

When you need CPI-adjusted hourly costs, run ``fhops.dataset inspect-machine --machine-role <role>`` (or reference
``data/machine_rates.json``) using the role associated with your preset. The table below summarizes which machine-rate
entry lines up with each skyline helper. Presets without BC cost coverage are flagged so you know to supply your own
rates.

.. list-table:: Skyline preset → machine-rate mapping
   :widths: 26 24 20 30
   :header-rows: 1

   * - Preset(s)
     - Source/system
     - Machine-rate role
     - Notes
   * - ``tr125-single-span`` / ``tr125-multi-span`` / ``tr127-block1``–``block6``
     - FPInnovations TR-125/127 Skylead C40 corridors
     - ``grapple_yarder_skyleadc40``
     - 1991 CAD rate (FERIC TN-201). Reuse this CPI-aware entry for both single- and multi-span corridors until dedicated TR-127 costs surface.
   * - ``fncy12-tmy45``
     - Thunderbird TMY45 + Mini-Mak II intermediate supports (FNCY12/TN258)
     - ``grapple_yarder_tmy45``
     - 1992 CAD LeDoux-derived rate with Cat D8/Timberjack standby baked in (0.3335/0.2415 SMH; see :ref:`tn258_support_method`). Telemetry logs the support ratios automatically.
   * - ``mcneel-running``
     - McNeel (2000) Madill 046 running skyline
     - ``grapple_yarder_cypress7280``
     - Uses the TN-157 Cypress swing-yard rate (1991 CAD) for long-span running skyline conversions.
   * - ``tn173-ecologger`` / ``tn173-gabriel`` / ``tn173-christie`` / ``tn173-teletransporteur`` / ``tn173-timbermaster-1984`` / ``tn173-timbermaster-1985``
     - TN-173 compact skyline fleet (Eastern Canada)
     - ``skyline_ecologger_tn173`` / ``skyline_gabriel_tn173`` / ``skyline_christie_tn173`` / ``skyline_teletransporteur_tn173`` / ``skyline_timbermaster_tn173``
     - Each preset has a dedicated 1991 CAD entry mirroring the original FERIC case study; CPI helper inflates to 2024.
   * - ``hi-skid``
     - FNG73 Hi-Skid short-yarding truck
     - ``skyline_hi_skid``
     - 1999 CAD attachment + operator (ADV2N62 wage). ``inspect-machine`` reports the CPI-adjusted rate.
   * - ``tn147``
     - TN-147 Madill 009 highlead skyline (coastal BC)
     - ``grapple_yarder_madill009``
     - 1991 CAD owning/operating split captured from the FERIC report; used whenever the TN147 helper runs.
   * - ``tn157``
     - TN-157 Cypress 7280B swing yarder + UH14 trail spar
     - ``grapple_yarder_cypress7280``
     - CPI-aware rate includes the trail-spar allowances; also reused by `mcneel-running` when modelling Cypress conversions.
   * - ``adv5n28-clearcut`` / ``adv5n28-shelterwood``
     - ADV5N28 Madill 071 skyline conversions (helicopter replacement)
     - ``grapple_yarder_adv5n28``
     - 2002 CAD Advantage owning/operating split with CPI adjustments; telemetry logs the skyline-vs-helicopter savings.
   * - ``ledoux-skagit-shotgun`` / ``ledoux-skagit-highlead`` / ``ledoux-washington-208e`` / ``ledoux-tmy45``
     - LeDoux (1984) residue skyline trials (Skagit BU-94, Washington 208E, Thunderbird TMY-45)
     - ``grapple_yarder_skagit_shotgun`` / ``grapple_yarder_skagit_highlead`` / ``grapple_yarder_washington_208e`` / ``grapple_yarder_tmy45_residue``
     - 1984 USD owning/operating splits converted via the CPI helper for the residue presets.
   * - Presets without dedicated BC rates (``lee-uphill``, ``lee-downhill``, ``aubuchon-*``, ``micro-master``)
     - South Korea / US Pacific Northwest studies outside the FPInnovations catalog
     - —
     - Supply your own rate (or reuse ``grapple_yarder`` generic) when running costing workflows; these remain non-BC references.

.. _tn258_support_method:

TN-258 / FNCY12 support utilisation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Thunderbird TMY45 intermediate-support study (FNCY12 + TN-258) is the only FPInnovations source that
publishes both the month-by-month yarder SMH and the crew/man-day split needed to back-calculate support-machine
utilisation. We take the 2.5 man-day delta between the Thunderbird and Skylead crews (Table 3), scale it by the
23 % of the harvest area that required intermediate supports (Table 2), then split the resulting labour tax
between the Cat D8 backspar and Timberjack 450 trail-support duties using the TN-157 backspar-share statistics
(≈58 % backspar, ≈42 % trail support). The helper script ``scripts/fncy12_support_split.py`` reproduces the math
from the structured dataset at ``data/reference/fpinnovations/fncy12_tmy45_mini_mak.json`` so costing workflows
can be audited end-to-end.

.. list-table:: Support ratios per productive yarder SMH
   :widths: 28 18 18 36
   :header-rows: 1

   * - Preset / helper
     - Cat D8 backspar
     - Timberjack 450 trail support
     - Notes / source
   * - ``cable_running_fncy12`` / ``fncy12-tmy45`` / ``grapple_yarder_tmy45``
     - 0.3335
     - 0.2415
     - Derived from FNCY12 Tables 2–3 plus TN-157 backspar-share stats; see ``data/reference/fpinnovations/fncy12_tmy45_mini_mak.json`` or rerun ``scripts/fncy12_support_split.py`` for the full calculation.

If future FPInnovations payroll or utilisation logs surface (e.g., Jay-Vee/Bell Pole internal records) we can
swap in the published minutes, but until then these ratios represent the best-available data and replace the
older TN-157 proxy (0.25/0.14) throughout the skyline cost banner, telemetry, and harvest-system overrides.

Partial-cut profile registry
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``fhops.dataset estimate-skyline`` now understands ``--partial-cut-profile <id>`` (and the skyline harvest systems
listed earlier set the appropriate ID for you). Profiles live in ``data/reference/partial_cut_profiles.json`` and
bundle the observed volume/cost multipliers from FPInnovations partial-cut trials so productivity, costing banners,
and telemetry all flag the penalty without reopening the PDFs.

.. list-table:: Available partial-cut profiles
   :widths: 18 44 18 18
   :header-rows: 1

   * - Profile ID
     - Source / description
     - Volume multiplier
     - Cost multiplier
   * - ``sr109_patch_cut`` / ``sr109_green_tree`` / ``sr109_shelterwood``
     - SR-109 MASS patch, green-tree, and shelterwood forwarding trials (excavator + tracked skidder relays)
     - 0.846 / 0.715 / 0.495
     - 1.10 / 1.10 / 1.38
   * - ``adv11n17_trial1`` / ``trial2`` / ``trial3``
     - Advantage 11 No. 17 partial-cut trials (motor-manual CTL, cable skidder full-tree, mechanised full-tree)
     - 0.775 / 0.833 / 0.925
     - 1.52 / 1.20 / 1.21
   * - ``adv1n22_group_selection``
     - Advantage 1 No. 22 group-selection opening (Barkerville Corridor small-opening program)
     - 0.918
     - 1.06
   * - ``tn199_partial_entry``
     - Quadra Island JD450G crawler winching through dispersed retention (12–15 % removal per entry)
     - 0.177
     - 2.14
   * - ``adv9n4_interface_thinning``
     - Alex Fraser Research Forest interface fuel-reduction thinning (tractor/skidder/ATV skidding + manual piling/burning)
     - 0.012
     - 27.0

Profiles with neutral multipliers (e.g., ``adv11n17_trial4``) act as baselines and are omitted for brevity. Update the JSON
file and re-run the CLI when new FPInnovations partial-cut datasets are digitised—the skyline helper picks up additions
automatically.

Road & Subgrade Construction References
---------------------------------------

Roadbuilding presets are still in flight, but the foundational FPInnovations dataset is now captured in
``data/reference/fpinnovations/tr28_subgrade_machines.json`` (FERIC TR-28 “Productivity and Cost of Four Subgrade
Construction Machines”). Each machine entry includes movement costs, phase-level cycle rates (logging, stumping, clearing,
excavation), utilization, per-station cost, and roughness indicators so the upcoming road-cost helper can quote realistic
BC numbers without reopening the PDF.

- **Cat 235 hydraulic backhoe** – 3.15 stations/shift (≈96 m), 5.56 CAD/m subgrade cost, 0.63 min working cycle, and
  separate mineral vs. overburden excavation rates (174 vs. 127 m³/h) for cut/fill planning.
- **Cat D8H bulldozer** – 2.61 stations/shift (≈80 m), 6.37 CAD/m, and higher walking speed (10.5 km/h) that will feed the
  cut-and-fill vs. push distance toggles; logging/stumping cost per stem already stored for landing-clearing presets.
- **American 750C line shovel** – 3.07 stations/shift, 6.13 CAD/m with lower utilization (79 %) and steeper movement costs
  (two trucks + 4 h lowbed) to cover dipper-shovel mobilization cases.
- **Poclain HC300 hydraulic shovel** – 1.78 stations/shift, 10.8 CAD/m, high excavation time (47 h) and the worst
  roughness indicator (4.02 m²/100 m), making it the default cautionary example for wet-site subgrade finishing.

Use these entries when drafting the road-cost helper schema (owning/operating split, movement surcharge, quality index) and
tie the soil-protection warnings back to TR-28’s roughness indicators plus ADV4N7/FNRB3 once those documents are staged.
Until the helper ships, cite this section in planning docs whenever roadbuilding data is required so we avoid redundant
TR-28 rescans.

For a quick terminal summary, run ``fhops dataset tr28-subgrade``. The command reads the structured JSON, lets you
filter by role (e.g., bulldozer vs. backhoe), sort by unit cost/stations/roughness, and prints the CPI-base metadata so road
cost planning sessions can pull the TR-28 numbers without reopening the PDF.

Need a CPI-adjusted estimate for a specific spur? Run ``fhops.dataset estimate-road-cost --machine <slug> --road-length-m <m>``.
Pick any machine slug from the `tr28-subgrade` table (for example ``caterpillar_235_hydraulic_backhoe``) and the CLI will
apply the 1976 CAD unit cost to your requested length, inflate it to the current StatCan CPI target, and (optionally) add the
published mobilisation cost (toggle with ``--exclude-mobilisation``). Output lists base-year + 2024 CAD totals alongside the
implied number of stations (30.48 m each) and estimated shifts so you can sanity-check the assumptions before wiring the numbers
into a planning sheet. When a scenario carries a ``road_construction`` table (id, TR-28 slug, length, mobilisation flag, soil profile
IDs), ``fhops.dataset estimate-cost --dataset …`` will pull those defaults automatically (use ``--road-job-id`` if multiple entries
exist) and print the structured FNRB3/ADV4N7 soil profiles defined in ``data/reference/soil_protection_profiles.json`` so planners
see exactly which compaction or ground-pressure constraints were assumed. Skyline/cable harvest-system templates now push those
road defaults for you: any block that references a preset listed in ``fhops.scheduling.systems.SYSTEM_ROAD_DEFAULTS`` causes the
scenario (and the synthetic dataset bundles) to emit the matching ``road_construction`` row, so ``estimate-cost`` and telemetry
immediately reflect the paired TR-28 machine, length, mobilisation flag, and soil-profile IDs without touching the CSVs.

ADV4N7 and ADV15N3 inputs now drive automatic support penalties when those soil profiles are present. The default skyline road
entries include ``adv4n7_compaction`` so ``fhops.dataset estimate-cost`` multiplies the TR-28 unit cost by **1.15** (“some” risk:
reduce loads and limit passes to ≤3) and logs the source in telemetry. Select ``--road-compaction-risk low|some|high`` when you
need to override the default, or remove the soil profile entirely if the block is on dry/frozen ground. Road jobs that reference
``caterpillar_d8h_bulldozer`` now pull the ADV15N3 tractor-efficiency study: whenever compaction risk is ``some`` or ``high`` the CLI
applies the Cat D7R low-speed penalty (≈1.16× fuel / SMH) and prints a “[Support penalty applied]” banner citing ADV4N7 + ADV15N3.
Use ``--road-tractor-drive`` if you want to model the hydrostatic (John Deere 950J) or diesel-electric (Cat D7E) drives from ADV15N3;
the helper applies the published fuel-intensity delta even when soils are firm and still honours the low-speed penalty whenever the
ADV4N7 risk is “some” or “high”. Telemetry captures the compaction/tractor multipliers so downstream costing can see exactly why a
scenario’s road add-on changed.

Handfalling Cost Reference
--------------------------

Manual falling productivity/costs now live in ``data/reference/fpinnovations/tn98_handfalling.json`` (FERIC TN-98, Peterson 1987).
Use ``fhops dataset tn98-handfalling --species douglas_fir --dbh-cm 32.5`` to pull the regression-based cutting time, interpolated
limbing delay, and cost-per-tree / cost-per-m³ for a given DBH class (defaults to the study’s “all species” regression).
Add ``--show-table`` when you want to review the observed per-diameter rows before copying numbers into skyline costing sheets.
``fhops.dataset estimate-skyline-productivity`` now accepts ``--manual-falling`` with optional ``--manual-falling-species`` and
``--manual-falling-dbh-cm`` so TN-98 falling costs show up beside the skyline output. Harvest systems that include a hand-faller
job auto-enable those settings (e.g., ``cable_micro_*`` presets default to hemlock @ 32.5 cm, ``cable_running`` presets default to
Douglas-fir @ 52.5 cm) and print a reminder when the defaults kick in.

Use ``fhops dataset tn82-ft180`` to compare the FMC FT-180 vs. John Deere 550 tracked skidders from TN-82 (clearcut vs. winter
right-of-way). The command prints m³/PMH and per-shift stats for each site, making it easy to benchmark steep-slope ground
alternatives alongside the skyline helpers.

Use ``fhops dataset adv6n25-helicopters`` to review the ADV6N25 light-lift operation (Eurocopter Lama + K-1200 K-Max). The
CLI prints productivity/cost rows for each helicopter and, with ``--show-alternatives``, the “in-woods manufacturing” and
“single-pass K-Max” cost scenarios discussed in the report.

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
