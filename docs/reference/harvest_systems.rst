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
