# P11 validation evidence

Synthetic thesis-shaped parity cases (not the confidential company data).

| loads | mip_status | mip_objective | mip_runtime_s | sa_status | sa_objective | sa_runtime_s | gap_pct | mip_violations | sa_violations |
|---|---|---|---|---|---|---|---|---|---|
| 9 | feasible | 1350.0000000000014 | 60.11928025726229 | feasible | 1350.0 | 16.103068014606833 | -1.010549668636586e-13 | 0.0 | 0 |
| 10 | infeasible | nan | 60.19443976599723 | feasible | 1500.0 | 15.565102872438729 | nan | nan | 0 |
| 11 | infeasible | nan | 60.18386082723737 | feasible | 1620.0 | 15.815511715598404 | nan | nan | 0 |
| 12 | infeasible | nan | 60.13532017171383 | feasible | 1770.0 | 15.385427244007587 | nan | nan | 0 |

Large synthetic scale case.

| case | flow_status | flow_objective | flow_runtime_s | loads | sa_status | sa_objective | sa_violation_minutes | sa_runtime_s |
|---|---|---|---|---|---|---|---|---|
| hauling_scale day 1 | feasible | 27428.399999999998 | 30.116031373851 | 92 | feasible | 34535.8 | 0.0 | 5.842131529003382 |


Notes:

- `mip_status=infeasible` for 10-12 loads means the 60 s exact solve returned no incumbent, not a
  proof that no feasible schedule exists. The SA schedules validate with zero violations, and a
  manual fixed-plan check confirmed the 10-load SA plan is feasible under the Phase II constraints.
- The 9-load case reaches exact objective parity (1350.00). The exact MIP's tractability limit on
  this synthetic case is earlier than the thesis's 13-load limit; symmetry breaking and a MIP start
  from the SA plan are the recorded follow-ups. The SA solver is the scalable path.
- The scale case is `examples/hauling_scale/` day 1 (92 loads). Phase I returns a feasible incumbent
  at 30 s; SA reaches zero violation. The exact MIP is not run at this size.
