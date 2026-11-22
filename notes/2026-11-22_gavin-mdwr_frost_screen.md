> Public project-note copy. See the matching instance planning note.

# Gavin MDWR preliminary frost screen — 2026-11-22

Status: **screening diagnostic, not a legal determination**

## Question

GWM 10 defines frost-prone sites as those with a summer frost hazard class of
**medium, high or very high** (Steen et al. 1990). The opening-size limits are:

- transition: 0.1–0.3 ha on frost-prone sites;
- deep: 0.1–0.4 ha on frost-prone sites.

The existing legal group layout has a 0.7 ha maximum and no frost classification.
This screen asks how many assigned openings would exceed the frost cap.

## Method

### Frost hazard class

- Applied FRDA Report 157, Table 3 (preliminary frost hazard class guide) and
  Table 4 (mesoslope position definitions).
- BEC groups: `SBSdw1` and `ICHmk3` are Group 3. The mixed `ICHmk3/SBSdw`
  label is also treated as Group 3 for a conservative screen; no `SBSdw2`
  label occurs in the fragment table.
- Derived slope and aspect from the 5 m Gavin DEM.
- Derived a standardized topographic position index (TPI) at a 500 m radius:
  `(elevation - local mean) / local standard deviation`.
- Classified mesoslope as follows:

| Condition | Class |
| --- | --- |
| slope < 5%, TPI z ≥ -1.0 | level |
| slope < 5%, TPI z < -1.0 | depression |
| slope ≥ 5%, TPI z < -1.0 and slope < 15% | toe |
| slope ≥ 5%, TPI z < -0.4 | lower |
| slope ≥ 5%, TPI z > 1.0 | crest |
| slope ≥ 5%, TPI z > 0.4 | upper |
| otherwise | mid |

- Applied the Group 3 rules from Table 3: level/toe/depression = High;
  lower with slope > 15% = Moderate; crest = Very low; otherwise Low.
- Frost-prone = Moderate, High or Very high.

### Group assignment

- Group polygons were rasterized to the DEM. Each group received the mean
  slope, mean TPI z and warm-aspect fraction of its pixels.
- 20,168 groups were sampled from polygon pixels; 5,609 very small groups were
  sampled at the centroid. Of the assigned openings, 130 were centroid-sampled.
- Warm aspect is slope > 10% and aspect 136–270°.
- Opening caps:

| Condition | Cap |
| --- | ---: |
| frost-prone, transition or mixed BEC | 0.3 ha |
| frost-prone, deep ICH | 0.4 ha |
| warm aspect, not frost-prone | 0.4 ha |
| other, transition | 0.7 ha |
| other, deep | 1.0 ha |

- The current layout maximum is 0.7 ha, so the 1.0 ha deep-zone allowance does
  not bind.
- UWR inclusion was tested by exact vector intersection with the BCGW
  U-5-002 / dwl_9 clip.

## Results

### Frost class

| Class | All groups | All area (ha) | Assigned groups | Assigned area (ha) |
| --- | ---: | ---: | ---: | ---: |
| High | 2,464 | 186.66 | 181 | 79.99 |
| Moderate | 2,251 | 174.31 | 359 | 106.39 |
| Low | 20,297 | 2,312.35 | 3,270 | 1,186.51 |
| Very low | 765 | 124.17 | 144 | 59.00 |
| **Frost-prone** | **4,715** | **360.97** | **540** | **186.38** |

### Cap violations

| Measure | All groups | Assigned |
| --- | ---: | ---: |
| Opening-cap violations | 703 / 343.84 ha | **327 / 161.29 ha** |
| Frost-cap violations | 535 / 255.27 ha | **291 / 142.15 ha** |
| Non-frost warm-cap violations | 168 / 88.57 ha | **36 / 19.13 ha** |

The 291 assigned frost-cap violations are **9.9% of the 1,431.89 ha scheduled
area**. They are concentrated in lower slopes and level ground:

| Frost class | Assigned groups | Assigned area (ha) | Violations | Violation area (ha) |
| --- | ---: | ---: | ---: | ---: |
| High | 181 | 79.99 | 111 | 68.00 |
| Moderate | 359 | 106.39 | 180 | 74.15 |
| Low | 3,270 | 1,186.51 | 31 | 16.50 |
| Very low | 144 | 59.00 | 5 | 2.64 |

The High and Moderate rows account for all 291 frost-cap violations. The
Low/Very low rows are the 36 warm-aspect cap violations, not frost cases.

### UWR inclusion

- 181 assigned openings are not fully inside the authoritative UWR clip.
  Their total group area is 64.64 ha; **42.58 ha lies outside** the UWR.
- Across the full layout, 861 groups are not fully inside; **73.13 ha lies
  outside**. This matches the approximately 73 ha difference between the
  2,799.26 ha group geometry and the 2,726.42 ha UWR clip.
- The existing group layout therefore includes openings that cannot be treated
  as legal-order openings until the boundary discrepancy is resolved.

### Combined effect

- 499 assigned openings (221.64 ha, **15.5% of scheduled area**) either exceed
  an opening cap or are not fully inside the UWR.
- 9 assigned openings do both.

### Sensitivity

The TPI thresholds and window are screening choices. Re-running the screen with
alternative values gives:

| Scenario | Assigned frost-prone area (ha) | Assigned frost violations (ha) |
| --- | ---: | ---: |
| Base (500 m, z -1.0/-0.4/0.4/1.0) | 186.38 | 142.15 |
| 250 m window | 180.28 | 135.11 |
| 750 m window | 192.55 | 151.86 |
| Looser frost thresholds | 318.75 | 243.57 |
| Tighter frost thresholds | 119.61 | 93.47 |

Even the tightest variant leaves **93.47 ha** of assigned frost-cap violations.
The conclusion does not depend on the exact TPI threshold.

## Limits

- This is a **preliminary screening class**, not a field-verified frost hazard
  map. FRDA 157 requires site-specific modifiers for operational use.
- Table 3 is a guide for clearcuts; applying it to group-selection openings is
  an assumption.
- The TPI-based mesoslope classification is a reproducible proxy, not the
  air-photo/field procedure in FRDA 157.
- The mixed `ICHmk3/SBSdw` label is treated as Group 3; if part is SBSdw2, the
  Group 4 rules would change some lower-slope classes.
- Group values are means over small openings; 130 assigned groups were
  centroid-sampled.
- UWR inclusion uses the BCGW approved layer, but the ~73 ha model/boundary
  difference still needs an independent legal review.
- No legal-order compliance claim is made.

## Consequence

The existing group layout cannot be treated as a legal-order layout:

- it has 291 assigned frost-cap violations covering 142.15 ha;
- it has 181 assigned openings with 42.58 ha outside the approved UWR;
- the frost and UWR issues overlap only on 9 openings, so they are mostly
  separate defects.

The next step is to rebuild the openings inside the UWR clip with the frost and
warm caps, then rerun the cohort state and regrown phase schedule. The public
block screen remains the policy result; the group result remains a diagnostic.

## Outputs

- `planning/2026-11-22_gavin-mdwr_frost_screen.csv` — per-group screen.
- `planning/2026-11-22_gavin-mdwr_frost_screen_summary.json` — base summary.
- `planning/2026-11-22_gavin-mdwr_frost_screen_sensitivity.csv` — threshold
  variants.
