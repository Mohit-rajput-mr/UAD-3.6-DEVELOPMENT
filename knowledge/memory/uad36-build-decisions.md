---
name: uad36-build-decisions
description: Core product decisions for the UAD 3.6 URAR report generator in C:\UAD 3.6 DEVELOPMENT
metadata: 
  node_type: memory
  type: project
  originSessionId: 55f99e9c-80f8-42ee-9cd0-a94f6af1badd
  modified: 2026-09-14T18:28:26.841Z
---

The user is building an internal AI appraiser that ingests supporting documents
(PDFs, photos, sketch, floorplan, comps, MLS geodata) and emits a UAD 3.6
deliverable ZIP containing `appraisal.pdf`, `mismo.xml` and an `Images/` folder.

Decisions made 2026-09-14:

- **Market data**: the user supplies MLS/comps exports; the engine derives
  adjustments from that dataset. No live MLS feed is available.
- **Output/review UX**: the report must render as a fully editable browser
  preview — every section revisable by the appraiser — with a "Download ZIP"
  action that packages the deliverable *from the edited state*. So one HTML
  report definition drives both the on-screen editor and the PDF.
- **Scope**: all property types (SF, condo, co-op, manufactured, 2–4 unit).
- The appraiser will supply license, insurance and signature images to be
  embedded in every report.

**Why:** these shape the architecture and aren't recoverable from the code.
**How to apply:** keep the report definition single-sourced between preview and
PDF; never invent market figures — derive them from supplied data.

See [[uad36-spec-assets]].
