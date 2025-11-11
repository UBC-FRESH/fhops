# KPI Summary Snapshot

| Metric | Value |
| ------ | ----- |
| Total production | {{ total_production }} |
| Completed blocks | {{ completed_blocks }} |
| Makespan (day / shift) | {{ makespan_day }} / {{ makespan_shift }} |
| Mobilisation cost | {{ mobilisation_cost }} |
| Utilisation (mean shift) | {{ utilisation_ratio_mean_shift }} |
| Utilisation (mean day) | {{ utilisation_ratio_mean_day }} |
| Downtime hours | {{ downtime_hours_total }} |
| Weather severity total | {{ weather_severity_total }} |

## Mobilisation by Machine

{{ mobilisation_cost_by_machine }}

## Utilisation by Machine

{{ utilisation_ratio_by_machine }}

## Downtime by Machine

{{ downtime_hours_by_machine }}

## Weather Severity by Machine

{{ weather_severity_by_machine }}
