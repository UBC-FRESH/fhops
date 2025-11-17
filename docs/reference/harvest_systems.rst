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

Harvest-system templates can now supply these overrides automatically: pass
``--harvest-system-id <system_id>`` (default registry or your scenario’s definitions) or
``--dataset <scenario-path> --block-id <block>`` to pull the block’s harvest system and apply its
``productivity_overrides`` for the grapple skidder job. The command prints when such defaults are
applied so you can verify which template influenced the result.

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
``skyline_yarder`` or ``helicopter_longline`` jobs. Available regressions:

* ``lee-uphill`` / ``lee-downhill`` – HAM300 case study (Lee et al. 2018, South Korea). Uphill model
  only needs ``--slope-distance-m`` and optional ``--payload-m3``; downhill adds
  ``--lateral-distance-m`` and ``--large-end-diameter-cm``. The CLI prints warnings because these are
  non-BC datasets intended for short spans (<130 m).
* ``tr125-single-span`` / ``tr125-multi-span`` – Standing-skyline regressions from FPInnovations TR-125
  (Skylead C40 with Mini-Maki carriage). Supply ``--slope-distance-m`` and ``--lateral-distance-m``;
  payload defaults to 1.6 m³ (≈3.4 logs × 0.47 m³/log) but can be overridden via ``--payload-m3``.
* ``tr127-block1`` … ``tr127-block6`` – Block-specific regressions from FPInnovations TR-127 (northwestern
  BC). The command prompts for ``--num-logs`` when Blocks 5–6 require it and shows the computed
  cycle minutes alongside productivity.
* ``mcneel-running`` – **New** running-skyline helper based on McNeel (2000) Madill 046 longline yarders.
  Provide the horizontal span (``--horizontal-distance-m`` or reuse ``--slope-distance-m``), deflection
  (``--vertical-distance-m``), and lateral yarding distance. Pieces per cycle and piece volume default to the
  paper’s Yarder A/B averages (2.8 pieces × 2.5 m³ or 3.0 × 1.6 m³), but you can override them with
  ``--pieces-per-cycle`` / ``--piece-volume-m3``. Pick ``--running-yarder-variant yarder_a`` or ``yarder_b`` to
  mirror the observed payload/cycle-time differences.
* ``aubuchon-standing`` – **New** standing-skyline helper derived from the Hensel et al. (1979) Wyssen system
  regression compiled in Aubuchon (1982). Supply ``--logs-per-turn``, ``--average-log-volume-m3``, and
  ``--crew-size`` along with slope/lateral distance. The CLI reports turn minutes and payload so analysts can
  calibrate against local choking practices.

Every skyline model emits the assumed payload and m³/PMH0 result; the McNeel helper also reports cycle
minutes derived from the Table 4 regression so analysts can see how deflection or payload tweaks affect
turn time. Telemetry rows now carry ``horizontal_distance_m``, ``vertical_distance_m``,
``pieces_per_cycle``, ``piece_volume_m3``, and the running-yarder variant whenever ``mcneel-running`` is used,
along with the log/crew inputs when the Aubuchon model is selected.

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
