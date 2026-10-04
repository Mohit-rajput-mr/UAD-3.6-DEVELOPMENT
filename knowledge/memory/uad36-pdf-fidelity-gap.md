---
name: uad36-pdf-fidelity-gap
description: "PDF fidelity work vs Appendix D-1 — engine design, tools, and status as of 2026-09-16"
metadata: 
  node_type: memory
  type: project
  originSessionId: 883733c5-77c7-4979-9f45-5e7455d729c1
  modified: 2026-09-16T11:33:55.059Z
---

User's bar: appraisal.pdf must be the SAME as the Appendix D-1 samples ("pixel perfect
from a-z"), values black, nothing overflowing. Myriad Pro Black is **dropped** at the
user's instruction (2026-09-16) — the Bold substitute with Black's published widths
stays; do not raise the font again.

Engine (all spec-derived):
- `uad/spec/extract_c1_form.py` → `spec/c1_form.json`: the form itself from C-1.
- `uad/report/form.py` fills it; `flow.py` measures/paginates/verifies overflow.
- `uad/report/rules.py` executes B-1 display rules; `spec/section_rules.json` holds each
  section's rule (Disaster Mitigation, Rental, Cost Approach etc. hide correctly).
- Certifications / Scope of Work fixed text: each paragraph is opened by a margin slot in
  C-1 whose field carries the rule; agency-specific wording (FHA/USDA/VA) filtered by
  GovernmentAgencyAppraisalType.
- Grid: `comparables.html` at measured geometry (label 106, subject 108.5, desc 66 + adj
  42.5), right-aligned values, adjustment cell merged when the row is not adjustable,
  photos under addresses on the first block, row visible if always / a comparable says
  something / (if_applicable and the subject says something) — "None"/"No"/"false" count
  as silence.

Tools: `engine/tests/span_diff.py` (glyph-baseline dx/dy/dw, exact ≤0.25pt),
`engine/tests/pixel_diff.py` (ink overlay), `engine/tests/render_form.py <key> [pages]`.

Status 2026-09-16: page 1 exact runs 406/844 (48%) across the 12 samples, SF1 71/97.
Page counts: MH2 20 vs 20, SF3 21 vs 23, SF1 17 vs 21, 2-4 scenario2 23 vs 26,
2-4 unit 19 vs 29 (that one is short — check its exhibits/rental grid).
Not yet done: calibration of pages 2+, rental/GRM grid styling, sketch full-page image,
exhibit captions, grid subject fields missing where the B-1 supplement has no subject FID
(e.g. Contract Price) — enrich from c1_form grid pages.

See [[uad36-render-tricks]], [[uad36-spec-driven-architecture]].
