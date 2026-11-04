Salvage Shelf-Life and Wood Degradation
=======================================

FHOPS has salvage harvest systems and an optional ``salvage_processing_mode``
block field, but the machine chain alone does not model the biological clock.
Dead wood loses recoverable volume and product options as it ages. This page
documents the first bounded, source-backed salvage shelf-life surface.

The surface is deliberately read-only:

* a shared curve library under ``fhops.salvage``;
* one published retention curve and one advisory product-window table;
* one report command that joins a storage/age table to scenario blocks.

It does **not** change a schedule, objective, constraint, heuristic, or solver.

Sources and boundaries
----------------------

Retention curve
~~~~~~~~~~~~~~~

The packaged curve ``pnw_fire_killed_mixed_conifer`` reproduces the net volume
retention factors in Prestemon and Holmes (2008), section 4.2.6:

* 1.00 at year 0;
* 0.99 after 1 year;
* 0.89 after 2 years;
* 0.58 after 3 years;
* 0.22 after 4 years;
* 0.00 after 5 years.

The source is a weighted-average series for mixed-conifer fire-killed timber in
southwest Oregon. It is a **reference curve**, not a BC-specific,
species-specific, or roadside-storage-specific operational curve. FHOPS does
not add, fit, or extrapolate coefficients. Ages between published years use
linear interpolation; ages beyond the last point use the last published value.

Product windows
~~~~~~~~~~~~~~~

The product windows reproduce the Canadian boreal shelf-life statements in
Barrette et al. (2015):

* lumber is generally most suitable 1-2 years after death;
* pulp salvage is usually not recommended after 3-4 years;
* past that period, bioenergy may be the better outlet.

These windows overlap and are advisory. They are not a mill-acceptance rule or a
species-specific guarantee.

Quick start
-----------

The storage table is a CSV with one row per block::

    block_id,years_since_disturbance
    B01,1
    B02,4

Run the report against a standard FHOPS scenario:

.. code-block:: bash

   fhops report salvage-shelf-life \
     examples/tiny7/scenario.yaml \
     examples/salvage_shelf_life/storage.csv \
     --value-per-m3 10 \
     --out-dir tmp/salvage

The command prints the per-block table plus the curve source and boundary. With
``--out-dir`` it also writes:

* ``salvage_shelf_life.csv`` — deterministic per-block results;
* ``salvage_shelf_life.md`` — the same table with provenance and limits.

Original volume comes from ``Block.work_required`` (m³). The command does not
infer volume from area or yield curves. A block does not need a
``salvage_processing_mode`` to be included, but blocks without one are named in
a caveat because they are not validated salvage blocks.

Output columns
--------------

``block_id``
    Scenario block id.

``years_since_disturbance``
    Age supplied by the caller, in years since fire or tree death.

``salvage_processing_mode``
    The block field when present (``standard_mill``, ``portable_mill``, or
    ``in_woods_chipping``); blank otherwise.

``is_salvage_block``
    ``yes`` when the block declares a salvage processing mode.

``retention_fraction``
    Curve value at the supplied age.

``original_volume_m3``
    ``Block.work_required``.

``retained_volume_m3``
    ``original_volume_m3 × retention_fraction``.

``value_per_m3``
    The caller-supplied price, or blank.

``retained_value``
    ``retained_volume_m3 × value_per_m3`` when a price is supplied. This is a
    volume-retention proxy at a constant unit value, not a grade recovery or
    price forecast.

``eligible_products``
    Semicolon-separated advisory product windows containing the age.

``curve_id``
    The applied curve.

``curve_source`` / ``curve_url`` / ``curve_boundary``
    Citation, public URL, and applicability boundary for the applied curve. The
    boundary is repeated in the CSV so the file is self-describing.

``product_window_source``
    Citation for the advisory product windows.

``report_limits``
    The read-only and non-operational boundary statement. ``retained_value`` is a
    volume-retention proxy at a constant caller price, not a price forecast or
    grade-recovery model.

Adding another curve
--------------------

The data contract is ``data/reference/degradation/salvage_decay.v1.json``. A
new curve needs a stable ``curve_id``, a stated ``age_unit`` and
``retention_definition``, strictly increasing published points, and a source
with a public URL and an applicability boundary. Do not add fitted or
extrapolated points. A BC or species-specific curve should land only when a
public or project-approved source supplies the values.

Python API
----------

.. code-block:: python

   from fhops.salvage import load_decay_library, build_salvage_report

   library = load_decay_library()
   curve = library.curve("pnw_fire_killed_mixed_conifer")
   print(curve.retention_at(3.0))          # 0.58
   print(library.eligible_products(3.5))  # ('pulp', 'bioenergy')

   report = build_salvage_report(
       "examples/tiny7/scenario.yaml",
       "examples/salvage_shelf_life/storage.csv",
       value_per_m3=10.0,
   )
   print(report.frame)

Limits
------

* The first curve is a reference curve, not an operational BC curve.
* Product windows are advisory and overlap.
* The report is a volume-retention surface, not a value model. The optional
  value is a caller-supplied constant price applied to retained volume.
* No objective, constraint, heuristic, or solver is changed.
* Roadside storage duration and standing dead wood age share the same age axis
  here only because the published curve is expressed as time since fire/death.
  A dedicated storage curve would be a separate, sourced addition.
