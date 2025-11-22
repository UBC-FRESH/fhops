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

### 1999 – Log-truck / Hi-Skid operator wage (ADV2N62, FNG73 Hi-Skid)

Source: `notes/reference/fpinnovations/ADV2N62.txt` (June 15 1999 IWA wage bulletin referenced across Advantage Vol. 2 No. 62 and the FNG73 Field Note).

- Log-truck or yarder-driver classification: **$24.01/h** base wage (southern interior, 1999).
- Standard fringe: **+38 %** (pension, health, vacation, union dues) ⇒ **$33.13/SMH** fully burdened labour.
- Used directly for the FNG73 Hi-Skid short-yard truck preset (`skyline_hi_skid` machine-rate entry) alongside an 8 L/h diesel allowance at $0.65/L and a 16 $/SMH maintenance bucket. Ownership column assumes a CAD 60 k attachment amortised over 5 years (1 200 SMH/yr, 10 % salvage, 8 % interest/insurance), keeping the **1999 CAD** base year explicit so CPI inflators can roll it forward.
- When updating the Hi-Skid rate, reuse this wage/fringe combo unless a newer IWA schedule is cited; otherwise, inflate the 1999 labour component using StatCan M&E CPI to 2024 CAD before layering on scenario-specific adjustments.

### Outstanding wish list

- Locate a **pre-1990 BC IWA wage card** for Thunderbird TMY-45 style crews (FNCY12/TN258) so the new `grapple_yarder_tmy45` rate (currently LeDoux 1984 USD costs scaled to a 5.5-person crew) can be validated or replaced with authentic payroll numbers.
- Capture **residue vs. merchantable utilisation penalties** from BC sources (e.g., TR112 addenda, regional residue studies) to refine labour split when yarding waste wood.
- Document a **CPI/FX trail** for each era (1979, 1989, 1994, 1997, 1999, 2002, 2004) so machine-rate inflation steps are reproducible without ad-hoc notes.
