---
name: uad36-render-tricks
description: Non-obvious Chromium/PDF and spec facts needed for pixel-exact URAR output
metadata: 
  node_type: memory
  type: reference
  originSessionId: 883733c5-77c7-4979-9f45-5e7455d729c1
  modified: 2026-09-16T11:04:50.633Z
---

Facts found the hard way while matching D-1 (2026-09-15/16):

- **Compare by glyph baseline origin, not bbox.** Two builds of Myriad Pro report
  different bbox heights for the same glyph in the same place; `engine/tests/span_diff.py`
  compares `rawdict` char origins (dx, dy) and first→last advance (dw). Tolerance 0.25pt.
- **Chromium snaps text to device pixels and rounds borders to them.** Fix: lay each page
  out inside `.hi{width:3×;transform:scale(.3333)} > .hz{zoom:3}` — at 3× one point is
  4 device px, so 0.5/1/2pt rules are exact and baselines land on 1/12pt.
  (4× gives finer text but prints 0.5pt rules as 0.38pt.)
- **That wrapper shrinks a multi-page print to 2/3** unless each `.page` has `contain:strict`.
- **D-1 is set with InDesign optical kerning** — deterministic per (face, size, pair):
  4,337 pairs over 530k observations, median sd 0.03 units. `uad/spec/learn_kerning.py`
  reads them from the sample PDFs + C-1; `uad/report/kerned_fonts.py` bakes them into a
  kern feature, one font per point size (`UAD <size>` families), plus liga (ff/fi/fl).
  Never kern pairs containing a space; the **space advance itself is size-dependent**
  (Regular 212 at 9pt, 202 at 32pt) and is written into each per-size font.
- **MyriadPro-Black is not on this machine** (Acrobat ships Light/Regular/Semibold/Bold).
  The Summary address and SUMMARY heading use it. Substitute = Bold outlines with Black's
  advances from the samples' /Widths (`engine/spec/d1_font_widths.json`) + text-stroke.
  Ask the user for MyriadPro-Black.otf to close this.
- D-1 checkboxes are Wingdings2 12pt ""/"", 5.3pt apart, run ending at x-3.
- A CSS rule that sets font-size gets a size-matched family injected — exclude rules that
  already name a family (the Wingdings one) or the checkboxes vanish.
- Footer reference IDs: values left-aligned so the longest ends at 576pt; labels right-
  aligned 9.7pt before the value column.
- B-1 holds generated text: Final Value Condition Statement (p372-3), CostToRepairType →
  DDD cost column/Total Cost/summary line (p84-5), commentary field → category
  (engine/spec/commentary_categories.json). Defect category comes from RELATIONSHIP
  arcrole DEFECT_ContainsDefectOf_<TYPE>; no relationship = Site; Summary DDD shows only
  action ≠ None.

See [[uad36-pdf-fidelity-gap]], [[uad36-spec-parsing-facts]].
