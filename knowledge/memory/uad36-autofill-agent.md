---
name: uad36-autofill-agent
description: "The autonomous form-filling feature: how it works and what is left"
metadata:
  type: project
---

The user wants the report to fill itself **visibly**: the frontend must look like an
autonomous appraiser working section by section (dropdowns, tick boxes, typing, rows,
photos) while the backend writes in parallel. Built 2026-09-17/18:
`engine/app/autofill.py` + `POST/GET /api/cases/{id}/autofill` + `fill()` in EDIT_JS
(uad/report/flow.py) + "Fill the report" in the shell.

Design rules that must hold:
- **The animation is never the source of truth.** The server writes everything first;
  the page replays the same step list and is reloaded from the server at the end.
- The plan walks the **source document**, not the editor's controls: every value keyed by
  the address of the element it sits in, so a value in `SITE_UTILITY[2]` lands in
  `SITE_UTILITY[2]`. Also: comparables to create first, RELATIONSHIP links (attributes,
  no text -- a walk over values alone drops them and defects stop printing), photographs.
- When the server finishes, the shell swaps in a fresh render and **hands the rest of the
  run to the new frame** -- that is what makes rows/grid cells/photos visible.

Verified 2026-09-18: a blank case filled from each D-1 scenario reproduces the source
document value-for-value, prints the same report, and raises no finding the sample does
not. SF1 1,018 steps / 0 failed / 0 fatal / 0 warning / 0 schema.

Left: T-244, editor controls for the 103 fields the coverage audit still finds no control
for. Intake from the user's own folder (order sheet + MLS + comps + images) is T-242.

See [[uad36-pdf-fidelity-gap]], [[uad36-spec-driven-architecture]].
