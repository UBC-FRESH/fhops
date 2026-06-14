Source Bibliography and Document Access
=======================================

FHOPS was built from a large working library of forestry operations studies,
FPInnovations/FERIC reports, SoftwareX submission examples, author-instruction
snapshots, and intermediate extraction files. The public repository keeps the
bibliographic and provenance trail, but it no longer republishes the full-text
document collection.

This split is intentional and is not meant to make verification difficult. Some
of the tens to hundreds of documents reviewed while building FHOPS may be covered
by publisher, institutional, partner, or FPInnovations copyright terms that do
not allow redistribution through a public GitHub repository. If redistribution
rights were clear for the whole corpus, the documents would simply remain beside
the code. Because they are not, the full-text working library is held in an
access-controlled private GitHub repository and linked into authorized checkouts
as the ``reference-documents`` submodule.

Public bibliography
-------------------

The public reference inventory remains available in Markdown:

* `notes/reference_log.md <https://github.com/UBC-FRESH/fhops/blob/main/notes/reference_log.md>`__
  tracks FPInnovations/FERIC and non-FPInnovations sources, extraction status,
  short summaries, and productivity/cost leads.
* `notes/reference/ <https://github.com/UBC-FRESH/fhops/tree/main/notes/reference>`__
  contains focused public notes such as wage tables, CPI/FX conversion notes,
  skyline residue notes, and micro-yarder source summaries.
* Runtime datasets derived from permissible tabular values live under
  ``data/reference/`` and ``data/productivity/`` so installed FHOPS packages can
  run without requiring the private document vault.

Private full-text vault
-----------------------

Authorized collaborators can populate the private working library with:

.. code-block:: bash

   git submodule update --init reference-documents

The submodule points to the private repository
``UBC-FRESH/fhops-reference-docs``. Access is controlled by GitHub permissions;
users without access should use the public bibliography above to retrieve cited
documents from the original publishers, DOI landing pages, institutional
repositories, or FPInnovations/FERIC catalogues.

The private vault is a convenience copy for collaborators who already have access
to the materials. It does not grant permission to redistribute those files, and
it is excluded from FHOPS wheels, source distributions, and public documentation
builds.
