.. _operational-milp-formulation:

Operational MILP Formulation
============================

This page documents the canonical FHOPS operational MILP formulation used by the
Pyomo implementation in ``fhops.model.milp.operational``.

The formulation is maintained from a shared source module so the SoftwareX
manuscript and Sphinx docs stay synchronized. The objective, the constraint blocks,
the optional initial state, and the domains carry stable labels (**OBJ**, **OBJ2**,
**E1**--**E13**, **INIT**, **D1**) that the equation-to-code mapping table at the end
of the page and companion manuscripts cite. The Markdown source,
``docs/softwarex/manuscript/sections/includes/fhops_operational_formulation.md``, is
versioned with the code; cite it at a release tag (for example
``https://github.com/UBC-FRESH/fhops/blob/v1.0.1/docs/softwarex/manuscript/sections/includes/fhops_operational_formulation.md``)
for the formulation of that release.

.. include:: ../includes/softwarex/fhops_operational_formulation.rst
