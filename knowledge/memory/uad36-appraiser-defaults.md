---
name: uad36-appraiser-defaults
description: Owner's standing report defaults — designation MAI, credentials filled from profiles/appraiser.json, assignment exhibits = licence + E&O, 18 North adjustment rates
metadata:
  type: user
---

Standing defaults the owner set on 2026-09-29, for every report:

- **Designation: always MAI** (`APPRAISER_DESIGNATION` and its `ORD_` copy).
- **Appraiser credentials ARE filled** (supersedes the older "no licence number" rule — TOTAL will not clear field validation without them). They live in `profiles/appraiser.json`. On a new device, **ask the user whose credentials sign reports there** before the first case; never put one appraiser's licence on another's report.
- **Assignment Information exhibits = the appraiser's licence + the E&O declarations page**, never the engagement letter. Files go in `profiles/documents/` (`licence.png`, `eo_insurance.png`). Images pasted into a chat are NOT saved to disk — ask the user for the files.
- **Adjustments on the 18 North parameters** (`total-bridge/bridge/adjust.py`): $75/sf GLA, $10/sf site (>1,000 sf), $250/yr age (>5 yr), $10k bedroom, $5k half bath, $10k finished basement, $10k garage space, $10k outdoor living, 2% of list for market exposure on a listing or a pending sale carried at list. Rates not in the profile (cooling, condition, location) are the appraiser's call — list them, do not invent.
- **Every value sourced; researched values listed on the handback**; the value opinion derived from the adjusted comparables with the weighting arithmetic in the reconciliation.

**Why:** the owner corrected each of these on a real case.
**How to apply:** they are inputs to every case file, set before the first fill — not per-case choices.
