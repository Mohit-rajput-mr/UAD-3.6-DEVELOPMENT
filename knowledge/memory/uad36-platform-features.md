---
name: uad36-platform-features
description: "Required platform features for the UAD 3.6 report software — Review Master, media insertion, dynamic pagination, property-type templates"
metadata: 
  node_type: memory
  type: project
  originSessionId: 55f99e9c-80f8-42ee-9cd0-a94f6af1badd
  modified: 2026-09-16T18:33:59.189Z
---

Required features of the UAD 3.6 platform, stated by the user 2026-09-15:

- **Review Master** — a dedicated compliance review view listing *every* UAD
  compliance finding (H-1 Message IDs, severity, the field each points at), not
  just inline hints.
- **Media insertion** — the form itself must accept images: subject photos,
  comparable photos, MLS sheets, sketch/floor plan, and an "other" bucket. Each
  gallery carries a **+ button** to add more beyond the default slots.
- **Dynamic pagination** — page count and page breaks recompute from the actual
  content and from the property type; nothing is a fixed page count.
- **Property-type templates** — auto-load a starting template per type (single
  family, 2–4 unit, condo, co-op, manufactured) so the appraiser works on a
  pre-shaped report rather than an empty form.
- **Editor rules added 2026-09-16:** the Summary page is never editable (it
  redisplays other sections, per B-1 ch. 01); the left rail must jump to a
  section and follow the scroll; every gray photo placeholder takes a picture
  in place; exhibits are added through a small "+ Add Exhibit" button that
  opens a side panel beside the report, which then re-lays out.
- Competitive target: compete with ACI and WinTotal as a form-filling product
  that ships the UAD 3.6 deliverables.
- Positioning: "one of the most accurate UAD 3.6 report providers" — the bar is
  zero formatting or compliance defects in the delivered ZIP.

**Why:** these are product requirements that do not follow from the spec files;
the spec says what is legal, not what the software must offer.
**How to apply:** templates are derived from the twelve official Appendix D-1
sample XML files rather than hand-authored, so a template is always a real,
XSD-valid, H-1-clean case. See [[uad36-build-decisions]] and
[[uad36-zero-guess-mandate]].
