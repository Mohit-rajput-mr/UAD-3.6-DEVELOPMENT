---
name: uad36-zero-guess-mandate
description: Standing working rules for the UAD 3.6 build - read fully, never hand-write logic an authoritative file already defines
metadata:
  type: feedback
---

For `C:\UAD 3.6 DEVELOPMENT` the user issued a Zero-Guess, Full-Coverage
Mandate after a build failed. The binding rules:

1. Inventory every archive first, expanding nested zips.
2. Report **parsed** and **read** as separate numbers, per document, with real
   page counts. A low read-percentage is a *stop condition*, not a disclosure.
3. Never hand-write structural logic when an authoritative spreadsheet/schema
   defines it. Search the inventory first. If genuinely none exists, label it
   "no authoritative source found - needs confirmation".
4. If logic was guessed before the source was found, publish a field-by-field
   diff of what the guess got wrong before rebuilding.
5. Appendix D-1's per-scenario zips are ground-truth test fixtures, to be
   diffed against, not eyeballed.
6. Show the completion checklist with real numbers before calling anything done.
7. Never silently partial-complete; state constraints up front with a plan.

**Why:** the prior run parsed spreadsheets but read ~0.5% of 1,407 pages of
prose, and hand-typed the comparable grid from a screenshot (4 groups/32 rows)
when Appendix B-1's supplement defined it exactly (17 groups/153 rows).

**How to apply:** measure before planning - full prose is only ~624K tokens, so
there is no real constraint against reading everything. See
[[uad36-spec-assets]] and [[uad36-build-decisions]].
