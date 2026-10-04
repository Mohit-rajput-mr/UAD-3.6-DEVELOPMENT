---
name: uad36-spec-driven-architecture
description: The UAD 3.6 report is generated from the spec files, not hand-written - where each authority lives
metadata:
  type: project
---

In `C:\UAD 3.6 DEVELOPMENT` every structural decision is derived from a
specification file, never typed by hand. The authorities:

| Concern | Authority | Extracted to |
|---|---|---|
| Which fields, which section, which order | Appendix A-1 `Report Location` (1,399 FIDs) | `engine/spec/delivery_spec.json` |
| Comparable grid rows/groups | B-1 Comparable Grids supplement (153 rows, 17 groups) | `engine/spec/comparable_grids.json` |
| Left/right column per label, subsections | Appendix E Part 2 (pp33-81) | `engine/spec/layout.json` via `extract_layout.py` |
| Type sizes, rules, greys, cell types | Appendix E Part 1 | `engine/uad/report/style_spec.py` (page-cited) |
| Element order in XML | the XSD's own `<xs:sequence>` | `engine/spec/xsd_order.json` |
| Validation rules | Appendix H-1 (728 rules) | `engine/spec/compliance_rules.json` |

Four independent gates must pass before a deliverable ships: XSD schema,
UAD compliance rules, `package.verify()` for B-1 file structure, and the 60 MB
cap. `package.verify()` exists because schema + compliance both passed while
the archive shipped 37 images the XML never referenced (B-1 p73).

**Why:** hand-writing any of these produced ~14% of the real structure.
**How to apply:** before coding structure, look for the file that defines it.
See [[uad36-zero-guess-mandate]].
