> Public project-note copy. See the matching instance planning note.

# Gavin MDWR data-source check — 2026-11-22

## Correction

Earlier notes described frost-prone classification, the UWR boundary and the
Appendix 9 class map as unavailable. That was too strong. The check had been
limited to the local workspace and a narrow search. Public provincial sources
exist and have now been downloaded or reviewed.

## UWR boundary

- Source: BC Geographic Warehouse WFS layer
  `WHSE_WILDLIFE_MANAGEMENT.WCP_UNGULATE_WINTER_RANGE_SP`.
- Clip to the Gavin block fragments:
  **U-5-002 / dwl_9 (Beaver Valley North)**.
- Area inside Gavin: **2,726.4 ha**, across **656 blocks**.
- The 2004 U-5-002 order PDF is a one-page order. Schedule A is the spatial
  layer; the map is not embedded in the PDF. The old `ribftp.env.gov.bc.ca`
  FTP host no longer resolves.
- Derived clips and source metadata:
  `data/derived/gavin_mdwr/`.
- The current group estate totals 2,797.5 ha, about 71 ha more than the
  authoritative UWR clip. That difference still needs reconciliation.

## Stand-structure habitat classes

- Source: BC Geographic Warehouse WFS layer
  `REG_LAND_AND_NATURAL_RESOURCE.WLD_MULE_DEER_STND_STRC_CAR_SP`.
- Clip to Gavin / UWR: **2,726.4 ha** total.
  - High: **697.9 ha**
  - Moderate: **1,013.2 ha**
  - Low: **1,015.3 ha**
- These are the legal order's Stand Structure Habitat Class polygons referred
  to by GWM 7, not the adjusted Appendix 9 compartment boundaries.

## Frost hazard

- GWM 10 defines frost-prone sites as those with a summer frost hazard class
  of **medium, high or very high** (Steen et al. 1990).
- FRDA Report 157 is public:
  `https://www.for.gov.bc.ca/hfd/pubs/Docs/Frr/Frr157.pdf`.
- Table 3 is a preliminary frost hazard class guide using BEC subzone/variant,
  mesoslope position and slope gradient. Table 4 defines mesoslope positions.
- The dominant Gavin variants are Group 3 (SBSdw1 and ICHmk3). The mixed
  `ICHmk3/SBSdw` fragments need the SBS variant resolved; SBSdw2 is Group 4.
  In Group 3, medium and high hazard occur on lower/toe/depression/level
  positions; very high does not occur in the table.
- A 5 m DEM and BEC are available in the instance. The classification is
  therefore derivable, but it is not yet implemented.
- It remains a **preliminary/screening** class. The report requires
  site-specific modifiers, and a mesoslope classifier must be documented.

## Appendix 9

- MWP #3 Appendix 9 pages are available as scanned images
  (`mwp3_app9-161.png`, `mwp3_app9-162.png`).
- The official stand-structure class polygons are available digitally from
  BCGW.
- The adjusted BV01–BV09 compartment boundaries are not available as a
  separate GIS layer. This is a management-plan alignment gap, not the legal
  class-data gap.

## Consequence

- The UWR boundary and stand-structure classes are **not missing-data
  blockers**.
- Frost-prone classification is an implementation task, not a data-acquisition
  blocker.
- The adjusted Appendix 9 compartment boundaries remain the only unresolved
  spatial layer.
- No public result changes. The block screen remains public and the group
  cohort remains a diagnostic.
