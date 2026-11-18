# MKRF variable-retention policy screen

Status: **public policy seed, not a fully re-optimized plan or an approved
management plan.**

## Policy

The screen uses **dispersed retention** on the MKRF full estate:

- retention basis: **percent of pre-harvest basal area**;
- selection: **Douglas-fir first, largest DBH first**;
- first-entry treatments: `CC`, `VR10`, `VR20`, `VR30`;
- policy floor: **400 m² retained basal area per 10-year period**;
- retained trees remain for one rotation on the **full managed block**;
- the first harvest transitions to a composite plantation + retained-DF
  track; the next final harvest counts that DF volume and value;
- no residual area is moved to unmanaged.

## Result

| Metric | Value |
| --- | ---: |
| Blocks | 1,763 |
| Scheduled blocks | 1,219 |
| Total production | 3.091M m³ |
| Gross log value | CAD 655.2M |
| Net revenue | CAD 369.2M |
| Harvest cost | CAD 170.0M |
| Managed area | 4,120.7 ha |
| Unmanaged area | 690.2 ha |
| Retained BA | 12,798 m² |
| Retained volume | 193,970 m³ |
| Retained log value | CAD 41.70M |
| Targets | **44 met / 2 below / 1 above** |

All ten 400 m² retention targets are met. The two remaining misses are
even-flow yield checks; one even-flow check is above the band.

## Bucked residual assortment

| Class | Volume | Value |
| --- | ---: | ---: |
| Sawlog butt | 24,858 m³ | CAD 7.13M |
| Sawlog upper | 168,490 m³ | CAD 34.51M |
| Pulp | 621 m³ | CAD 0.06M |
| **Total** | **193,970 m³** | **CAD 41.70M** |

The residual cohort is dominated by sawlog upper, with a smaller high-value
butt component.

## Age sensitivity

| Profile | Gross | Net | Retained BA | Targets |
| --- | ---: | ---: | ---: | --- |
| Current/as-of age | CAD 655.2M | CAD 369.2M | 12,798 m² | 44/2/1 |
| Forced rotation+50 | CAD 657.7M | CAD 370.6M | 13,538 m² | 44/2/1 |

A re-optimized R+50 run reached **45/1/1** at CAD 652.6M gross and CAD 367.7M
net, with 13,985 m² retained BA.

## Method

- VRI supplies block TPH, basal area, species shares and age.
- The rotation DBH shape uses the pinned MKRF 684 tree list.
- The rotation+50 shape uses FAIB PSP CWHdm live Douglas-fir, age 140–180
  (2,817 records on 13 sites), blended by profile age.
- The retained cohort is selected from the right tail of the DF DBH
  distribution until the BA target is met.
- The composite track is additive for the retained overstory and plantation;
  it is not a two-cohort competition/mortality model.
- The first harvest uses aggregate product curves; the residual log-class
  ledger is bucked into sawlog butt/upper/pulp.

## Limits

- This is a **policy seed** schedule, not a fully re-optimized target search.
- The matrix coastal grades D/F/H/I/J/U/X/Y are still aggregate-scaled; the
  sawlog butt/upper/pulp ledger is not yet mapped to those grades.
- The older PSP anchor is a regional estimate from 13 sites.
- The 400 m² floor is a scenario policy, not a legal requirement.
- Composite retained-overstory growth is an additive approximation.
- This is a public WS4 screen, not an approved AAC, budget or legal plan.

## Files

- `mkrf-vr-policy/` — public tactical handoff, schedule, retention ledger,
  production, targets and provenance.
- `MKRF_VR_POLICY.pdf` — this brief.
- `MKRF_EARLY_MANAGEMENT_PLAN.pdf` — MKRF planning brief.
- `MKRF_RETENTION_AUDIT.pdf` — retention-value audit.
