> Public project-note copy. See the matching instance planning note.

# Gavin MDWR clipped and capped group layout — 2026-11-22

Status: **derived layout repair, not a cohort or policy result**

## Purpose

The existing legal group layout had three defects:

- 181 assigned openings with 42.58 ha outside the approved UWR;
- 291 assigned frost-cap exceedances covering 142.15 ha;
- 36 warm-aspect cap exceedances covering 19.13 ha.

This step clips the existing layout to the approved UWR and splits oversized
polygons on a 10 m grid so that every resulting group is at or below its cap.
It preserves source entry offsets. It does **not** rebalance pass fractions or
rerun the cohort/phase model.

## Method

- Source: `2026-11-20_gavin-mdwr_groups_all_legal.geojson` and the
  `2026-11-22_gavin-mdwr_frost_screen.csv` caps.
- Clip each source group to the BCGW U-5-002 / dwl_9 UWR boundary.
- Drop source groups fully outside the UWR.
- For groups above their cap, build a 10 m cell grid, partition cells into
  balanced contiguous pieces, and intersect each piece with the clipped group.
- Caps: 0.3 ha frost-prone transition/mixed; 0.4 ha frost-prone deep ICH;
  0.4 ha warm aspect; 0.7 ha other. The 0.7 ha other cap is kept conservative
  in the deep zone instead of using the legal 1.0 ha maximum.
- Assigned pieces below 0.1 ha are merged where the cap allows, otherwise
  dropped.
- New group IDs are source ID × 100 + piece number. `source_group_id` is
  retained for audit.

## Result

| Measure | Source | Repaired |
| --- | ---: | ---: |
| Groups | 25,777 | **27,110** |
| Total group area | 2,799.26 ha | **2,722.37 ha** |
| Assigned openings | 3,954 | **4,671** |
| Assigned area | 1,432.80 ha | **1,386.43 ha** |
| Assigned frost-prone | 540 / 186.38 ha | **933 / 177.94 ha** |
| Maximum opening | 0.70 ha | **0.70 ha** |
| Cap violations | 327 assigned | **0** |
| Minimum-opening violations | 0 | **0** |
| Groups outside UWR | 181 assigned | **0** |

- 614 source groups were fully outside the UWR and dropped.
- 1,097 source groups were split into more than one piece.
- 121 small assigned pieces were dropped after clipping, totaling about
  3.78 ha.
- The repaired layout covers **2,722.37 ha of the 2,726.42 ha UWR clip
  (99.85%)**. The 4.05 ha difference is the dropped small pieces and edge
  residue; it was not redistributed.
- Assigned area fell by 46.36 ha: 42.58 ha outside the UWR and 3.78 ha of
  dropped small pieces.

## Limits

- This is a **clip-and-split repair** of the existing schematic 10 m layout, not
  a fresh spatial redesign.
- Pass fractions were not recalculated or topped up after clipping. Some blocks
  may be under their target assigned area.
- Splitting preserves the source entry offset but does not re-optimise the
  spatial arrangement.
- The frost class is inherited from the preliminary group screen; mixed
  `ICHmk3/SBSdw` remains treated as transition/conservative.
- No cohort growth, matrix response, phase schedule, windthrow, or target
  framework is rerun here.
- The public group result remains **0.679M m³ / 26-of-30**; the public block
  screen remains the policy result.

## Outputs

- `planning/2026-11-22_gavin-mdwr_groups_frost_uwr.csv`
- `planning/2026-11-22_gavin-mdwr_groups_frost_uwr.geojson`
- `planning/2026-11-22_gavin-mdwr_groups_frost_uwr_summary.json`

## Next

Run the cohort state on the repaired groups, verify assigned area against each
block’s pass target, then rerun the regrown phase schedule. Do not replace the
public block screen with the repaired group layout until those checks pass.
