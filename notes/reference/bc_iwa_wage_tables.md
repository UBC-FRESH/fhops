BC IWA Wage/Benefit References
==============================

Use these sources when translating historic BC skyline cost studies into the generic machine-rate catalog or when back-calculating labour/benefit assumptions for new presets. Each entry cites the document already in `notes/reference/` together with the effective date, positions, and fringe allowances.

## 1994 – IWA-Canada rates (TN-261 loader-forwarder study)

Source: `notes/reference/tn261.txt` (FERIC TN-261, Appendix 2, June 1994 wage table).

- Hand faller: **$270.76/day** (regular rate for first 8 h, overtime 1.5× after 8 h).
- Bucker: **$23.50/h**.
- Landing bucker: **$19.61/h**.
- Loader/forwarder operators in the same appendix use **$22.88/h** + **35 % fringe** when costing machines.

Notes: Table explicitly states the overtime treatment (prorated at 1.5× beyond 8 h per shift) and that labour burden = 35 % for IWA benefits.

## 1996–1997 – Coastal BC skyline crews (TR-119/TR-125)

Sources:
- `notes/reference/fpinnovations/TR119.txt` (June 15 1996 IWA wages +35 % benefits used for strip/shelterwood skyline costing).
- `notes/reference/fpinnovations/TR125.txt` (June 15 1997 IWA wages +38 % benefits for Skylead C40 crews).

Both reports reiterate the standard FERIC costing convention:
- Use current IWA hourly rates per position.
- Apply **35–38 % fringe** (varies by year) and prorated overtime for machine-servicing (≈0.7 h at OT).
- Crew composition: yarder engineer, hooktender, rigging crew, fallers/buckers, processor, landing support.

## 2002 – Advantage skyline conversion (ADV5N28)

Source: `notes/reference/fpinnovations/ADV5N28.txt` (Appendix II, Table 4, 2002 IWA wage base).

- Falling labour derived from **2002 IWA coastal wage scale** (+40 % fringe, overtime after 8 h).
- Yarder crew wages embedded in Appendix II cost table; machine operators include $178.40/h labour + 40 % benefits.

## 2004 – Southern Interior Master Agreement (ADV5N45 / ADV7N3)

Sources:
- `notes/reference/fpinnovations/ADV5N45.txt` (Dec 2004, Appendix II).
- `notes/reference/fpinnovations/ADV7N3.txt` (Aug 2004, Appendix A/B).

Key points:
- Wage rates taken from the **2004 IWA Southern Interior Master Agreement**.
- Overtime handling: time-and-a-half after 8 h, double-time after 11 h (per footnotes g/h).
- Use when CPI-adjusting processor/loader/yarder labour for mid-2000s Advantage studies.

## Additional references

- `notes/reference/fpinnovations/TN147_highlead.json` / `tn157_cypress7280b.json`: both embed late-1980s IWA wages (+35–38 % fringe).
- `notes/reference/fpinnovations/ADV2N62.txt`: June 15 1999 IWA rates (southern interior) for loader-forwarder studies.
- `notes/reference/fpinnovations/ADV1N40_madill071.json`: 1998 interior IWA wages for Madill 071 running skyline.

### Outstanding wish list

- Locate a **pre-1990 BC IWA wage card** for Thunderbird TMY-45 style crews (FNCY12/TN258) to replace the current LeDoux (US) proxy.
- Capture **residue vs. merchantable utilisation penalties** from BC sources (e.g., TR112 addenda, regional residue studies) to refine labour split when yarding waste wood.
- Document a **CPI/FX trail** for each era (1979, 1989, 1994, 1997, 2002, 2004) so machine-rate inflation steps are reproducible without ad-hoc notes.
