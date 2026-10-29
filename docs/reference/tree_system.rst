Ground-Based System Simulation
==============================

``fhops.ground_system`` layers a deterministic grapple-skidder and loader queue
on top of the existing single-machine tree simulation. It is a reference
execution model for one block, one feller-buncher, one or more skidders, and one
loader. It does not replace the block/day MILP or claim field-calibrated system
productivity.

Command
-------

.. code-block:: bash

   fhops tree system scenario.yaml \
     --block B01 \
     --feller H1 \
     --skidder H2 \
     --skidder H3 \
     --processor H5 \
     --processor H6 \
     --loader H4 \
     --out build/system

The scenario must contain the named machines with compatible roles:

- feller: ``feller_buncher``, ``harvester``, or ``hand_faller``;
- skidder: ``grapple_skidder`` or ``skidder``;
- processor: ``roadside_processor`` or ``processor``; repeat
  ``--processor`` to simulate a parallel processing deck;
- loader: ``loader``.

The feller-buncher is processed with
:func:`fhops.spatial_machine.simulate_block`; its processed-tree events are
grouped into bunches of approximately ``--bunch-volume`` cubic metres. Skidders
are dispatched greedily to the earliest available bunch and always return to
the landing. If ``--processor`` is supplied, the roadside processor processes
each skidder load at the landing before it reaches the loader. The loader
processes processor output in arrival order. Without ``--processor``, loads go
directly to the loader.

Cycle-time controls are exposed on the CLI:

- ``--feller-reach`` and ``--feller-speed``;
- ``--skidder-capacity``, ``--skidder-empty-speed``,
  ``--skidder-loaded-speed``, ``--skidder-load-fixed``,
  ``--skidder-load-per-log``, ``--skidder-unload-fixed``, and
  ``--skidder-unload-per-log``;
- ``--loader-process-fixed`` and ``--loader-process-per-log``.

The default ``--rate-model calibrated`` uses:

- the Han et al. (2018) whole-tree grapple-skidder regression with the GNSS
  cable-skidder speed profile (SK) used as a travel override;
- the Barko 450 TN-46 ground-skid loader result. The loader's recorded
  ``avg_volume_per_shift_m3`` is converted to seconds per cubic metre with an
  assumed 8-hour shift.

``--rate-model reference`` uses the fixed ``MachineSpec`` cycle times instead.
The calibrated rates are provenance-bearing reference values, not universal or
field-validated machine rates. The default skidder capacity is 40 m³ so
tree-length loads from the mature demo are not silently refused; set it to the
actual machine payload for operational work.

``--landing-x`` and ``--landing-y`` set the landing in the scenario CRS. When
omitted, the mean tree position is used.

Optional terrain routing:

.. code-block:: bash

   fhops tree system scenario.yaml      --block B01 --feller H1 --skidder H2 --loader H3      --dem dem.tif --road road.geojson      --max-skidder-grade 30 --terrain-step 10

``--dem`` samples elevation along each skidder route and refuses routes above
``--max-skidder-grade``. ``--road`` reads a GeoJSON LineString/MultiLineString
and follows one connected road corridor between the landing and the bunch. This
is a single-corridor access model, not a road-network solver. DEM and road
coordinates must use the same CRS as the inventory. Install the optional
dependencies with ``pip install "fhops[lidar]"``.

Shift and trucking controls:

.. code-block:: bash

   fhops tree system scenario.yaml      --block B01 --feller H1 --skidder H2 --loader H3      --shift-days 7 --shifts-per-day 2 --hours-per-shift 10      --truck-capacity 30 --truck-cycle 3600 --truck-count 3      --truck-load-time 300 --landing-capacity 120

``--shift-days`` enables discrete operating windows. Tasks that do not fit in
the remaining window are delayed to the next window; a task is not split across
a shift boundary, and the run fails if no window can hold it. When
``--shift-days`` is omitted, time is continuous.

``--truck-capacity`` enables a downstream log-truck tracker. Loader output adds
to landing inventory; full trucks are dispatched when volume is available.
Truck events and landing inventory are written to the JSON and summary. Landing
overflow is reported as a warning and does **not** block the loader in this
reference model.

Outputs
-------

- ``system_events.csv`` — machine timeline with travel, load, unload, processor,
  and loader segments.
- ``system_events.json`` — the same event stream plus tree processing records,
  truck events, machine types, landing, shift windows, and duration; suitable
  for an external viewer.
- ``tree_processing.csv`` — one row per processed tree.
- ``system_summary.json`` — tree count, processed volume, makespan, machine
  utilisation, shift/truck summaries, landing inventory, warnings, and caveats.

Determinism and invariants
--------------------------

Given the same scenario, inventory, machine parameters, and bunch volume, the
system ID and event timeline are deterministic. The model records each
processed tree once, uses only the feller-buncher's processed events, and
reports unreachable trees separately. Skidder capacity is checked against each
bunch; a load larger than capacity raises an error rather than silently
overloading the machine.

Limits
------

- One block, one landing, one feller-buncher, one optional processor, one loader.
- DEM and single-corridor road routing are optional; they are not a full road
  network or landing-search model.
- Skidder and loader cycle times are configurable defaults, not calibrated
  regressions.
- Shift windows are fixed and tasks are not split across them.
- Trucking is a downstream inventory tracker; it does not block the loader.
- No breakdowns or multi-block routing.
- Tree inventories must be reviewed separately; this module does not validate
  stem-model calibration.
- The JSON timeline is data only; FHOPS does not ship a renderer.
