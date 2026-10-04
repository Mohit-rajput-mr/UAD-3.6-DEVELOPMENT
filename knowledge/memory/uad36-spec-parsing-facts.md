---
name: uad36-spec-parsing-facts
description: "Non-obvious facts about parsing the UAD 3.6 spec files, each found the hard way"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 55f99e9c-80f8-42ee-9cd0-a94f6af1badd
  modified: 2026-09-15T16:05:31.159Z
---

Facts about the UAD 3.6 specification artifacts that are not visible until a
parser gets them wrong. Each cost a debugging cycle.

**A-1 `Report Location` packs many locations into one cell.** One delivery row
lists *every* place its data point displays, run together:
`"1.001: Summary - {No Subsection} - Opinion of Market Value 26.007:
Reconciliation - ..."`. Taking only the first field ID drops ~75% of the page
(995 field IDs instead of 1,459).

**A-1 `Conditionality Details` names the instance discriminator** for 520 rows,
as `IF PartyRoleType = "Borrower"`. This is the reliable way to tell one PARTY,
COMMENTARY or ADDITIONAL_IDENTIFIER from another. Inferring from the
`Additional Context` column instead gives wrong answers where a context lists
several values.

**A-1 `UAD Data Point Format Details` is `±I.D`** — digits before the point,
digits after. `+9.2` prints `$121.25` and `$2.00`; `+9.0` prints `$491,000`;
`+2.3` prints `4.060`. Deciding precision from the value is wrong.

**The A-1 enumerations sheet** names its value column `Supported Enumerations`
and its display column `Output Report Display Text (Not to be Included in the
XML File)`. Display cells may carry a stray fragment after a newline (`"No\nR"`,
`"Condominium\no"`) — the first line is the value. `<<Does Not Display>>` means
print nothing.

**H-1's xPath is relative** (`../VALUATION_ANALYSIS/...`) and its `Property
Affected` column scopes the rule to a `@ValuationUseType`. A rule needs all
three of path, property role and logic; using one alone makes it fire on every
address in the file.

**The H-1 workbook has an `Adjustments Cardinality` tab** that UAD1758 refers to
but does not contain.

**MISMO plurals are irregular**: `PARTIES/PARTY`, `VALUATION_COMMENTARIES/
VALUATION_COMMENTARY`. A `child + "S"` test misses them.

**`id()` on an lxml element is not stable** — proxies are recreated per access.
Group elements by `tree.getpath(el)`.

**The D-1 samples' specification wrapper is not a fixed length**: two pages for
most, **three for Condo2**. Detect the report's first page by its footer
(`Fannie Mae | Freddie Mac`) rather than assuming an offset.

**Chromium turns a CFF/OpenType web font into unnamed Type3** glyphs in its
PDF. Convert to TrueType outlines (metrics unchanged) to get a real Type0
embed. See [[uad36-spec-driven-architecture]].
