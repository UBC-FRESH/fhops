> Public project-note copy. See the matching instance planning note.

# Gavin Lake MDWR official habitat-class map acquisition

Date: 2026-11-18

Status: **official fine-scale habitat polygons acquired and digitized; public
model still uses the BEC proxy until the adjusted Appendix 9 compartment map and
legal order are reviewed**

## Source

The public BC Ministry of Environment map is:

- *Long-Term Habitat Objectives: Beaver Valley North (Prouton Lakes)*
- dated 6 December 2001
- Appendix 11 of the regional long-term habitat objectives set
- source:
  `https://www.env.gov.bc.ca/cariboo/env_stewardship/ecosystems/mdwr_strat/maps/beavervly_lto.pdf`
- SHA-256:
  `1889b3c668f66435e56d9778bb8c10b586a996f0244799e5c2d402ade1c7d2e3`

The 2007 AFRF Management and Working Plan #3 says the Beaver Valley MDWR
habitat classes are depicted in **Appendix 9**, with the class distribution
"adjusted slightly to coincide with our total chance harvest blocks." Table 30
sets the pass intensities:

| Habitat class | Harvest per pass | Cutting cycle | Cohorts | Oldest-cohort maximum age |
| --- | ---: | ---: | ---: | ---: |
| High | 33% | 40 years | 3 | 120 years |
| Moderate | 25% | 40 years | 4 | 160 years |
| Low | 20% | 40 years | 5 | 200 years |

Source: 2007 AFRF MWP #3, section 7.4.2 and Table 30.

The Appendix 9 map in the MWP is a **compartment-level adjusted**
representation. The BC map used here is the finer long-term-objective polygon
layer; it is not being represented as the adjusted Appendix 9 compartment
boundaries.

## Method

- Extract the teal (High), green (Moderate) and pale-green (Low) filled
  polygons from the PDF vector content.
- Georeference from the printed 4 km UTM grid:
  - x: PDF 210.71875–1931.261719 points ↔ UTM 560000–592000 m;
  - y: PDF 270.378906–1908.121094 points ↔ UTM 5836000–5808000 m;
  - UTM zone 10N, reprojected to EPSG:3005 for the block overlay.
- Intersect with the 1,443 MDWR block polygons.
- Assign each block the class with the largest intersected area.
- If the official polygons cover less than 50% of a block, fall back to the
  documented BEC proxy for that block and mark the basis.

The georeference is a printed-grid fit, not a survey control. The class
assignment is suitable for a screening run, not a legal boundary
determination.

## Result

| Class | BEC proxy area | BEC blocks | Official fine-map area | Official blocks |
| --- | ---: | ---: | ---: | ---: |
| High | 14.27 ha | 19 | 682.3 ha | 251 |
| Moderate | 213.06 ha | 136 | 1,115.4 ha | 585 |
| Low | 2,571.98 ha | 1,288 | 898.4 ha | 512 |
| Unclassified | — | — | 103.3 ha | 95 |

After applying the 50% coverage floor and BEC fallback, the model classes are:

| Model class | Area | Blocks |
| --- | ---: | ---: |
| High | 600.0 ha | 239 |
| Moderate | 1,082.1 ha | 582 |
| Low | 1,117.2 ha | 622 |

The official polygons cover **2,367.7 ha of 2,799.3 ha (84.6%)** of the MDWR
block area. The unclassified remainder is non-productive/non-forest, map
whitespace, or boundary/georeference edge. It is not assigned a fabricated
class.

This is a material change from the BEC proxy: the proxy calls 92% of the MDWR
low habitat, while the official fine map puts 24% high, 40% moderate and 32%
low before the fallback. After fallback the model classes are 21% high, 39%
moderate and 40% low. The official-class matrix and corrected 40-year re-entry
screen are now built; see the resolution below.

## Files

- `planning/2026-11-18_gavin_mdwr_official_habitat.csv` — block-level class
  areas, coverage, official class, model class and basis.
- `planning/2026-11-18_gavin_mdwr_official_habitat.geojson` — clipped official
  class polygons in EPSG:3005.
- `planning/2026-11-18_gavin_mdwr_official_habitat.json` — source hash,
  georeference constants, class areas and caveat.
- `scripts/build_mdwr_official_habitat.py` — reproducible extractor.

## What this does not settle

- The Appendix 9 compartment map has not been digitized or reconciled against
  these fine polygons.
- The 2007 legal order and current ungulate winter range boundary still need a
  separate review.
- The public screen now uses the official fine-map classes with corrected
  age-preserving 40-year re-entry; the adjusted Appendix 9 compartment map and
  legal order still need review.
- The fine-map georeference is a screening fit from the printed grid; retained
  boundary uncertainty should be carried into any compliance discussion.

## Re-entry audit finding

The official-class matrix was built at
`ws4/runtime/mdwr_group_selection_official` and simulated for 300 years. It was
not published, because the check exposed a pre-existing re-entry problem in the
MDWR clone matrix.

The matrix builder resets the fragment age to zero on every group-selection
pass. The pass product curves are stand-age curves that start at age 79. A
40-year re-entry event therefore lands at offset 40, where the curve is still
zero, and resets the age again. In a block isolation test (block 266):

- BEC `GS20`: first pass at offset 23 gives 15.4 m³; offsets 63, 103, 143,
  183, 223 and 263 each give 0.0 m³;
- official `GS33`: first pass at offset 23 gives 25.4 m³; all later passes
  give 0.0 m³.

The aggregate official run gives 3.7727M m³ versus 3.7352M m³ for the BEC
matrix, but the difference is only the first-entry pulse; after period 9 the
two runs are identical. The target status is unchanged at 10 met / 43 below /
8 above.

Consequence: the current public `gavin-mdwr` total must be treated as a
**first-entry / full-area partial-cut screen**, not as a validated 40-year
re-entry result, until the age-reset semantics are fixed. The official-class
replacement is deliberately not published.


## Resolution

The simulator now treats a negative treatment offset as a **keep-age sentinel**:
the fragment keeps its current age across a partial cut instead of resetting to
zero. The MDWR matrix builder uses that sentinel for both initial and cycle
group-selection treatments.

The corrected official-class run (`gavin-mdwr-40-simcheck-official-reentry`)
produces **5.626M m³ over 300 years**, mean 187,519 m³ per period, min 81,358
m³, max 377,744 m³, period-30 stock 1,493,175 m³, and target status
**15 met / 33 below / 13 above**. The prior first-entry BEC screen was 3.735M m³
and 10/43/8.

The public `gavin-mdwr` folder and brief have been rebuilt from the corrected
official-class run. The adjusted Appendix 9 compartment map, 2007 legal order
and current UWR boundary remain unresolved, so this is still a screening
product, not a compliance determination.
