Skyline Residue Utilisation Notes
=================================

Purpose: keep a single place that documents how existing FHOPS sources handle slash/residue turns so the LeDoux presets can raise the right warnings and so we know which BC references still need transcription.

## Sources Reviewed

- `notes/reference/ledoux-manual-extraction.txt` – Table 3 residue terms and Table 4 hourly costs for Skagit BU‑94 (shotgun + highlead), Washington 208E, and Thunderbird TMY‑45 (lines 1‑53).
- `notes/reference/fpinnovations/TR119.txt` – Chamiss Bay partial-cut skyline trial (lines 240‑294).
- `notes/reference/fpinnovations/TR125.txt` – Kitwanga multi-span strip selection study (lines 1491‑1699).

## Quantitative residue penalties (LeDoux 1984)

All four regressions model delay-free cycle time `Y` (minutes) as a linear function of slope distance, merchantable log count/volume, and *residue* log count/volume (`X4`, `X5`). Each extra residue log adds the following minutes to the total cycle, and every extra residue cubic foot adds the noted minutes:

| Yarder | ΔY per residue log (`X4`) | ΔY per residue ft³ (`X5`) | Comment |
| --- | --- | --- | --- |
| Skagit BU‑94 shotgun | +0.200 min | +0.0093 min | Residue turns slow the cycle almost as much as adding one more merchantable log (0.1266 min). |
| Skagit BU‑94 highlead | +0.126 min | +0.0053 min | Lower penalty because the highlead preset already accounts for lighter payload control. |
| Washington 208E | +0.489 min | −0.0027 min | Residue *volume* reduces cycle time slightly once the log count term already captured hookup delay—interpreted as residue logs usually being short pieces that add little volume. |
| Thunderbird TMY‑45 | +0.229 min | +0.0048 min | Slack-pulling Mini‑Mak carriage still pays ~14 s per residue log even before lateral travel. |

Practical takeaways:

- A single residue log can burn 7–29 seconds, so a “slash-heavy” turn (e.g., 3 residue logs) adds 0.4–1.5 minutes to the cycle even if merchantable payload stays constant.
- Because Table 4 shows total hourly cost between USD 268–357 (`notes/reference/ledoux-manual-extraction.txt:41-49`), those extra seconds translate to ≈USD 1.8–5.6 per residue log at 1984 wages (USD 0.089–0.188 per machine-minute). CPI + FX adjustments should therefore surface an explicit warning whenever `residue_pieces_per_turn` exceeds the merchantable count.

## BC partial-cut evidence (TR119/TR125)

- TR119 shows that keeping 65–70 % of basal area standing dropped skyline productivity 30–34 % and raised costs 32–46 % relative to a nearby clearcut because hooktenders spent longer spotting safe corridors and dealing with hangups (`notes/reference/fpinnovations/TR119.txt:240-256`). No dedicated residue cycle table exists, but it confirms that “non-merchantable” content (retained stems, extra rigging) materially slows PMH outputs.
- TR125’s Kitwanga study documents only 38 % volume removal, yet still achieved 99 m³/shift falling and 102 m³/shift yarding by combining narrow 10 m corridors with intermediate supports. The report publishes the single- and multi-span regressions (`notes/reference/fpinnovations/TR125.txt:1491-1550`) but provides no per-turn slash/residue treatment—another reminder that BC publications focus on layout impacts (deflection, corridor spacing) instead of slash utilisation ratios.
- Both reports emphasise residual stand damage tracking (`TR119.txt:257-259`, `TR125.txt:1621-1699`) rather than residue clean-up metrics, so there is no BC analogue to the LeDoux residue coefficients yet.

## Gaps / Next actions

1. **BC-specific residue penalty** – No FPInnovations report quantified slash vs. merchantable payload splits. We still need a Kitimat / Chamiss Bay style time study where residue loads were tracked explicitly.
2. **LeDoux warning hook** – When wiring the `ledoux-*` presets, use the coefficients above to print a delay warning whenever `residue_pieces_per_turn` × coefficient exceeds the merchantable term. Surface the cost delta using the new CPI/FX audit trail.
3. **Future data wishes** – If TN258 or any FNCY volumes expose residue share (% of turn that was cull wood), capture it here so the skyline helper can switch from generic LeDoux penalties to BC numbers.
