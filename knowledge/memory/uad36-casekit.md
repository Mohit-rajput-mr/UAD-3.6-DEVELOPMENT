---
name: uad36-casekit
description: A single-family case in WinTOTAL is one command — read folder, write case.json, `bridge case`, `bridge certify`; the proven order and the traps it encodes
metadata:
  type: project
---

Since 2026-09-30 a single-family URAR is filled by `total-bridge/bridge/casekit.py`
from one `case.json` the agent writes after reading the case folder:

    python -m bridge.cli sheets  --folder "<case folder>" --out "<scratch>"   # VIEW every sheet
    python -m bridge.cli case    --json case.json --dry-run                   # plan vs open report
    python -m bridge.cli case    --json case.json                             # fill, then certify
    python -m bridge.cli certify --report "<report>"                          # FV, schema x2, UAD

Proven on a real report (worked example: `knowledge/cases/worked_example_sf/case.json`,
FV 0 / schema 0 / UAD 0). Full runbook: `knowledge/PLAYBOOK.md`.

The traps it encodes (each in `knowledge/errors/CATALOG.md`): comparable columns via
CompManagers.AddComp and exhibit rows via a focused table's guidance button (E-046);
view photos before placing (E-047); pending comps carry no sale price/terms/date and a
driveway needs its surface (E-048); "stored^shown" pick lists store the left half (E-049);
exposure days need their checkbox, an unlisted subject needs its empty listing row removed
(E-050); TOTAL's UAD rules run only at FV 0 (E-051); nets re-summed after re-showing rows
(E-038); supervisor/SRPA levels EMPTY, not "None" (E-034); settle on `assignment`, never
`order-1`, before any export (UAD-1542).

**Why:** the first manual pass took ~150 tool calls and repeated known mistakes.
**How to apply:** never hand-write writes a case file can express; if the kit lacks
something, add it to the kit (with a test) rather than working around it in a case script.
