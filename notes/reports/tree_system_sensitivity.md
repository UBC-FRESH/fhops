# Ground-Based System Sensitivity Check

Date: 2026-10-29

Status: reference-model validation; synthetic research-forest demos.

## Purpose

The multi-machine ground system now has calibrated feller/skidder/loader rates,
an optional TN-103 roadside processor, shift windows, trucks, landing inventory,
DEM terrain, and single-corridor road routing. This check asks whether the
current demo is governed by plausible bottlenecks or by arbitrary defaults.

It is not a field validation. The stand inventories, terrain, road, and viewer
are synthetic/scratch data in `build/tree_scale_data/`.

## Method

Two mature-stand demos were used:

| Case | Trees | Volume | Stand |
|---|---:|---:|---|
| Gavin | 4,496 | 3,615 m³ | `AFRF_GAVIN_485` |
| Malcolm Knapp | 3,468 | 6,095 m³ | `MKRF_MATURE_868` |

Baseline:

- one feller-buncher, two skidders, one processor, one loader
- calibrated Han/Barko rates
- TN-103 processor at 35.0 m³/SMH
- 21 days × 2 shifts × 10 h
- 3 trucks × 30 m³, 3,600 s cycle
- landing capacity 120 m³
- synthetic DEM and single road corridor
- one block, one landing

The reproducible driver is `scripts/tree_system_sensitivity.py`. Generated
results are in `notes/reports/tree_system_sensitivity/`.

## Baseline

| Case | Makespan | Processor busy | Feller busy | Loader busy | Truck loads | Landing peak | Final inventory |
|---|---:|---:|---:|---:|---:|---:|---:|
| Gavin | 132.1 h | 109.5 h | 51.8 h | 44.0 h | 120 | 58.6 m³ | 15.3 m³ |
| Malcolm Knapp | 225.9 h | 182.5 h | 48.2 h | 74.1 h | 203 | 61.0 m³ | 4.5 m³ |

The processor is the governing machine. The feller and loader are substantially
less utilized.

## Processor rate

| Processor rate (m³/SMH) | Gavin makespan | Malcolm Knapp makespan |
|---:|---:|---:|
| 20 | 230.6 h | 389.4 h |
| 35 | 132.1 h | 225.9 h |
| 50 | 92.7 h | 157.1 h |
| 70 | 67.6 h | 113.6 h |

The TN-103 feller-bunched default is 35.0 m³/SMH. The TN-103 combined observed
case is 20.4 m³/SMH; ADV5N6 cold loader-forwarded processing reports 49.0
m³/SMH. The demo is therefore highly sensitive to which processor regime is
justified.

A rate of 70 m³/SMH is a **surrogate** for two processors, not a true
two-processor queue. Multiple processors are not yet modelled.

## Trucks and landing inventory

| Truck count | Gavin makespan | Malcolm Knapp makespan |
|---:|---:|---:|
| 1 | 134.3 h | 227.6 h |
| 2 | 132.1 h | 225.9 h |
| 3 | 132.1 h | 225.9 h |
| 4 | 132.1 h | 225.9 h |
| 6 | 132.1 h | 225.9 h |

Trucking now blocks the loader when landing inventory would exceed capacity.
One truck is insufficient: makespan rises to **151.8 h / 253.2 h** and landing
inventory peaks at about 120 m³. Two or more trucks return to the baseline
**132.1 h / 225.9 h** with 58.6 m³ / 61.0 m³ peak inventory.

Landing capacity 60 m³ is feasible but tighter: 58.6 m³ peak on Gavin and
57.7 m³ on Malcolm Knapp. Truck capacity and cycle time remain second-order at
the current landing capacity.

## Shift windows

| Pattern | Gavin makespan | Malcolm Knapp makespan |
|---|---:|---:|
| 1 × 8 h | 320.4 h | fails to fit a final task |
| 2 × 8 h | 160.4 h | 276.6 h |
| 1 × 10 h | 266.1 h | 441.9 h |
| 2 × 10 h | 132.1 h | 225.9 h |
| 2 × 12 h | 112.6 h | 187.5 h |

Shift length is a first-order variable. The current task model does not split a
task across a shift boundary; a task that cannot fit waits for the next window,
and the run fails if no window remains. The Malcolm Knapp 1 × 8 h failure is
therefore an expected model behavior, not a machine failure.

## Truck capacity and cycle time

| Truck configuration | Gavin makespan | Malcolm Knapp makespan |
|---|---:|---:|
| 20 m³, 3,600 s | 132.1 h | 225.7 h |
| 30 m³, 1,800 s | 131.6 h | 225.4 h |
| 30 m³, 5,400 s | 132.6 h | 226.4 h |
| 40 m³, 3,600 s | 132.1 h | 225.7 h |

The truck fleet is not the bottleneck under the current downstream tracker.

## Findings

1. **Processor rate dominates the result.** The demo is not a machine-system
   validation until the processor regime is chosen and cited.
2. **Trucking is now constrained.** One truck is a bottleneck; two or more
   trucks remove the landing constraint under the baseline landing capacity.
3. **Shift structure matters more than truck count.** A 2 × 12 h pattern cuts
   makespan substantially; 1 × 8 h is infeasible for Malcolm Knapp.
4. **One processor is a strong assumption.** Two processors are not modelled;
   the 70 m³/SMH row is only a surrogate.
5. **Landing capacity 120 m³ is adequate; 60 m³ is feasible but tight** for
   Malcolm Knapp.

## Recommended next steps

1. Replace the TN-103 placeholder with a justified processor regime for each
   research forest, or model multiple processors explicitly.
2. Add a realistic truck arrival/dispatch policy and truck routing before using
   truck-count results operationally.
3. Allow tasks to split across shifts, then add breakdowns and delays.
4. Rerun this grid after calibration.

No operational or regulatory claim is made from these synthetic runs.

## Multiple-processor follow-up

The sensitivity grid above used one processor. Multiple processors are now supported
(`--processor` repeatable). The research-forest demo uses P1/P2, which reduces the
makespans to **65.5 h** (Gavin) and **111.3 h** (Malcolm Knapp). The 70 m³/SMH
surrogate row above should no longer be used to represent two processors.
