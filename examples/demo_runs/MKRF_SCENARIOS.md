# MKRF scenario analysis set

The FHOPS console now has three full-estate MKRF scenario runs from the WS4
`scenario-*-44` family. They share the same 1,763-block / 4,810.85 ha geometry and differ in
the WS4 schedule and public account outcomes.

| Run | Source | Blocks scheduled | Production | Net revenue | Harvest cost | Targets |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `mkrf-full-estate` | `scenario-base-44` | 1,221 | 3,148,735 m³ | CAD 376.8M | CAD 173.2M | 29 met / 7 below / 1 above |
| `mkrf-low-estate` | `scenario-low-44` | 1,212 | 3,170,458 m³ | CAD 380.2M | CAD 174.4M | 33 met / 3 below / 1 above |
| `mkrf-high-estate` | `scenario-high-44` | 1,211 | 2,794,062 m³ | CAD 334.5M | CAD 153.7M | 32 met / 3 below / 2 above |

These are public WS4 model accounts, not a budget forecast. The comparison is available through
the FHOPS **Compare** panel; the maps use the shared MKRF block geometry.

## P00 operational comparison

| Scenario | P00 blocks | P00 volume | Makespan | Remaining | Vancouver trucks |
| --- | ---: | ---: | ---: | ---: | ---: |
| base | 115 | 390,965 m³ | 329 days | 0 | 12 |
| low | 86 | 367,238 m³ | 296 days | 0 | 12 |
| high | 78 | 299,973 m³ | 247 days | 0 | 10 |

All three P00 handoffs complete every selected block with zero sequencing violations under a
1,500 m³/day screening rate. The truck counts are public-geography fleet screens, not road-network
schedules.
